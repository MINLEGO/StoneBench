"""Real MCP replay of issue #1; the 36000 bound uses genuine 20 TPS unit steps."""
from contextlib import AsyncExitStack
from datetime import timedelta
import json
import os
from pathlib import Path
import time
import unittest

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from integration import TASK_ID, server_urls
from observation import ObservationRuntimeIntegration


class TransitionRuntimeIntegration(ObservationRuntimeIntegration):
    async def _connect(self):
        self.stack = AsyncExitStack()
        await self.stack.__aenter__()
        self.sessions = []
        for url in server_urls():
            client = await self.stack.enter_async_context(httpx.AsyncClient(timeout=httpx.Timeout(30, read=2450)))
            read, write, _ = await self.stack.enter_async_context(streamable_http_client(url, http_client=client))
            session = await self.stack.enter_async_context(ClientSession(read, write, read_timeout_seconds=timedelta(seconds=2450)))
            await session.initialize()
            self.sessions.append(session)

    async def fixture(self, session, name):
        self.assert_ok(await self.call(session, "__test_transition_fixture", {"scenario": "clear"}))
        self.assert_ok(await self.call(session, "advance", {"ticks": 12}))
        report = await self.call(session, "__test_transition_fixture", {"scenario": name})
        self.assert_ok(report)
        return report

    async def transition(self, session, status, ticks, **arguments):
        before = await self.call(session, "describe_task")
        report = await self.call(session, "transition", arguments)
        self.assert_ok(report)
        self.assertEqual(report["transition"]["status"], status, report)
        self.assertEqual(report["transition"]["tick"], ticks, report)
        self.assertEqual(report["ticks_executed"], ticks, report)
        self.assertEqual(report["world_time"] - before["world_time"], ticks)
        self.assertEqual(report["simulation_ticks"] - before["simulation_ticks"], ticks)
        self.assertTrue(report["frozen"])
        if arguments.get("trace"):
            self.assertEqual(report["continuity"]["complete"], report["coverage"]["status"] == "observed", report)
            self.assertEqual(report["trace"]["count"], ticks)
        return report

    async def test_real_mcp_server_contract(self):
        await self._connect()
        self.evidence = {}
        try:
            a, b = self.sessions
            for session in self.sessions:
                self.assert_ok(await self.call(session, "start_attempt", {"task_id": TASK_ID}))
            for bad in [{"max_ticks": 0}, {"max_ticks": 36001}, {"max_ticks": 1.5}, {"trace": "yes"}, {"ticks": 20}]:
                rejected = await self.call(a, "transition", bad)
                self.assert_error(rejected, "validation")
                self.assertEqual(rejected["ticks_executed"], 0)
            self.assert_error(await self.call(a, "advance", {"ticks": 6001}), "validation")
            await self.piston_and_chain(a)
            await self.hoppers(a)
            await self.coverage_and_chunks(b)
            await self.clock(a)
        finally:
            output = Path(os.environ.get("STONEBENCH_TRANSITION_EVIDENCE", ".runtime/transition-summary.json"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
            await self.stack.aclose()

    async def piston_and_chain(self, session):
        for name, duration in [("piston", 7), ("chain", 27)]:
            await self.fixture(session, name)
            self.assert_ok(await self.call(session, "advance", {"ticks": 12}))
            self.assert_ok(await self.call(session, "__test_transition_toggle"))
            report = await self.transition(session, "terminated", duration, trace=True)
            self.assertEqual(report["transition"]["last_movement_tick"], duration - 1)
            self.assertEqual(report["transition"]["recognition_tick"], duration)
            self.assertGreater(report["transition"]["quiet_with_pending_ticks"], 0)
            self.assertGreater(report["transition"]["moving_ticks"], 0)
            ticks = await self.pages(session, report["trace"], 256)
            self.assertTrue(all(row["rest"]["status"] == "running" for row in ticks[:-1]))
            self.assertEqual(ticks[-1]["rest"]["status"], "terminated")
            self.evidence[name] = report
            if name == "piston":
                self.assert_ok(await self.call(session, "__test_transition_toggle"))
                self.evidence["piston_close"] = await self.transition(session, "terminated", 7, trace=True)

    async def hoppers(self, session):
        await self.fixture(session, "hopper_cooldown")
        report = await self.transition(session, "indeterminate", 32, trace=True)
        ticks = await self.pages(session, report["trace"], 256)
        transfers, previous, cooldowns = [], 0, []
        for tick in ticks:
            snapshot = await self.snapshot(session, tick)
            chest = snapshot[(1028, 80, 1026)]
            count = sum(item["count"] for item in chest["inventory"])
            if count != previous:
                transfers.append(tick["tick_index"])
            previous = count
            hopper = snapshot[(1027, 80, 1026)]
            cooldowns.append(hopper["runtime"]["transfer_cooldown"])
            self.assertIn("last_tick_time", hopper["runtime"])
            self.assertEqual(hopper["runtime"]["last_tick_time_type"], "long")
            self.assertFalse(tick["state"]["block_ticks"])
        self.assertEqual(transfers, [8, 16, 24])
        self.assertEqual(cooldowns[-1], 0)
        self.assertTrue(all(t["rest"]["status"] != "terminated" for t in ticks))
        self.evidence["hopper_cooldown"] = {"report": report, "transfer_ticks": transfers, "cooldowns": cooldowns}
        for name in ["hopper_empty", "hopper_locked"]:
            await self.fixture(session, name)
            self.evidence[name] = await self.transition(session, "indeterminate", 1, trace=True)
            follow = await self.call(session, "advance", {"ticks": 8, "trace": True})
            self.assert_ok(follow)
            snapshots = [await self.snapshot(session, t) for t in await self.pages(session, follow["trace"], 256)]
            values = [s[(1027, 80, 1026)]["runtime"]["last_tick_time"] for s in snapshots]
            self.assertEqual(len(set(values)), 8)
            self.assertTrue(all(not s[(1027, 80, 1026)]["inventory"] for s in snapshots))
            self.evidence[name + "_followup"] = {"report": follow, "last_tick_times": values}

    async def coverage_and_chunks(self, session):
        self.assert_ok(await self.call(session, "__test_transition_fixture", {"scenario": "clock"}))
        self.assert_ok(await self.call(session, "advance", {"ticks": 12}))
        self.assert_ok(await self.call(session, "__test_release_chunks", {"after_ticks": 1}))
        failure = await self.call(session, "transition", {"trace": True, "max_ticks": 60})
        self.assert_error(failure, "infrastructure", "chunks_unavailable")
        self.assertNotEqual(failure.get("transition", {}).get("status"), "terminated")
        self.assertGreaterEqual(failure["ticks_executed"], 1)
        self.assertLess(failure["ticks_executed"], 60)
        self.evidence["chunk_loss"] = failure
        self.assert_ok(await self.call(session, "__test_restore_chunks"))
        fault = await self.call(session, "__test_outside_influence")
        self.assert_ok(fault)
        self.assertEqual(fault["coverage"]["status"], "insufficient")
        self.evidence["coverage"] = await self.transition(session, "indeterminate", 1, trace=True)

    async def clock(self, session):
        await self.fixture(session, "clock")
        short = await self.transition(session, "limit_reached", 12, max_ticks=12, trace=True)
        self.evidence["clock_short"] = short
        if os.environ.get("STONEBENCH_TRANSITION_SHORT"):
            self.evidence["clock_full"] = {"not_run": "explicit short diagnostic run; no 36000-tick validation claim"}
            return
        started = time.monotonic()
        report = await self.transition(session, "limit_reached", 36000)
        self.assertEqual(report["transition"]["maximum_ticks"], 36000)
        self.assertEqual(report["transition"]["observed_ticks"], 36000)
        self.assertEqual(report["transition"]["pending_ticks"], 36000)
        self.assertGreater(report["transition"]["quiet_with_pending_ticks"], 10000)
        self.assertIsNone(report["transition"]["recognition_tick"])
        self.evidence["clock_full"] = {"report": report, "wall_seconds": time.monotonic() - started}


if __name__ == "__main__":
    unittest.main(defaultTest="TransitionRuntimeIntegration", verbosity=2)



