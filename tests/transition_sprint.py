"""Real unit/sprint differential: expand immutable artifacts, preserve every state/clock/event field."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import unittest
from input import InputRuntimeIntegration
from transition import TransitionRuntimeIntegration
from integration import TASK_ID
from transition_evidence import Evidence
from construction import point, placement


class SprintEquivalence(InputRuntimeIntegration):
    _connect = TransitionRuntimeIntegration._connect

    async def pages(self, session, ref, limit=7):
        # Simulation and interaction calls still use real MCP. Exhaustive differential readback
        # verifies the immutable on-disk export, avoiding thousands of serialized read RPCs.
        return self.readers[id(session)].rows(ref)

    async def expand(self, session, value):
        if isinstance(value, dict):
            if "artifact_id" in value:
                rows = await self.pages(session, value, 256)
                # Artifact UUIDs identify files, not game state. Readback checks descriptor identity.
                # Resolve only this storage indirection; no state, event, NBT or clock is rewritten.
                resolved = {k: v for k, v in value.items() if k not in ("artifact_id", "sha256", "bytes")}
                resolved["entries"] = [await self.expand(session, row) for row in rows]
                return resolved
            return {k: await self.expand(session, v) for k, v in value.items()}
        if isinstance(value, list):
            return [await self.expand(session, item) for item in value]
        return value

    async def compare(self, name, reports):
        compared = {}
        for s, r in zip(self.sessions, reports):
            if "trace" in r:
                samples = self.readers[id(s)].rows(r["trace"])
                per_tick = [event for sample in samples for event in self.readers[id(s)].rows(sample["events"])]
                operation = self.readers[id(s)].rows(r["intratick_events"])
                self.assertEqual(operation, per_tick, name+": operation stream lost or changed tick events")
                self.assertEqual([e["operation_order"] for e in operation], list(range(len(operation))))
        for key in ("initial", "final", "trace", "diff", "intratick_events", "coverage", "continuity", "transition", "transition_diagnostics"):
            if key in reports[0] or key in reports[1]:
                left, right = [await self.expand(s, r[key]) for s, r in zip(self.sessions, reports)]
                self.assertEqual(left, right, f"{name}: exact {key} differs")
                compared[key] = hashlib.sha256(json.dumps(left, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        for key in ("world_time", "time_of_day", "simulation_ticks", "preparation_ticks", "ticks_executed", "status", "frozen"):
            if key in reports[0] or key in reports[1]:
                self.assertEqual(reports[0][key], reports[1][key], (name, key))
        self.evidence["comparisons"].append({"name": name, "exact_expanded_sha256": compared,
                                             "reports": reports})

    async def paired(self, name, args=None, label=None, error=False):
        reports = [await self.call(s, name, args) for s in self.sessions]
        for r in reports:
            if error:
                self.assert_error(r, "infrastructure", "chunks_unavailable")
            else:
                self.assert_ok(r)
        await self.compare(label or name, reports)
        return reports

    async def fixture_pair(self, name):
        await self.paired("__test_transition_fixture", {"scenario": "clear"})
        await self.paired("advance", {"ticks": 12, "trace": True}, name+" clear")
        await self.paired("__test_transition_fixture", {"scenario": name})

    async def test_real_mcp_server_contract(self):
        await self._connect()
        self.evidence = {"comparisons": [], "input_cycles": [], "policy": "exact absolute clocks and raw memory; artifact references resolved only"}
        try:
            starts = [await self.call(s, "start_attempt", {"task_id": TASK_ID}) for s in self.sessions]
            for r in starts:
                self.assert_ok(r)
                self.assertEqual(r["preparation_ticks"], 120)
                self.assertEqual(r["world_time"], 120)
                self.assertEqual(r["simulation_ticks"], 0)
            self.assertEqual([r["environment"]["tick_execution"] for r in starts], ["unit", "sprint"])
            self.evidence["starts"] = starts
            self.readers = {id(s): Evidence(r["environment"]["server_directory"]) for s, r in zip(self.sessions, starts)}
            for name, duration in (("piston", 7), ("chain", 27)):
                await self.fixture_pair(name)
                await self.paired("advance", {"ticks": 12, "trace": True}, name+" warmup")
                for edge in ("open", "close"):
                    await self.paired("__test_transition_toggle")
                    result = await self.paired("transition", {"trace": True}, name+" "+edge)
                    for r in result:
                        self.assertEqual(r["transition"]["tick"], duration)
                        self.assertEqual(r["transition"]["last_movement_tick"], duration-1)
            for name, duration in (("hopper_cooldown", 32), ("hopper_empty", 1), ("hopper_locked", 1)):
                await self.fixture_pair(name)
                result = await self.paired("transition", {"trace": True}, name)
                for r in result:
                    self.assertEqual(r["transition"]["status"], "indeterminate")
                    self.assertEqual(r["ticks_executed"], duration)
                await self.paired("advance", {"ticks": 8, "trace": True}, name+" runtime followup")
            await self.fixture_pair("clock")
            await self.paired("advance", {"ticks": 1, "trace": True}, "single exact tick")
            before = [await self.call(s, "describe_task") for s in self.sessions]
            await asyncio.sleep(.2)
            after = [await self.call(s, "describe_task") for s in self.sessions]
            self.assertEqual([r["world_time"] for r in before], [r["world_time"] for r in after])
            await self.paired("advance", {"ticks": 48, "trace": True}, "clock advance exact48")
            limit = await self.paired("transition", {"max_ticks": 49, "trace": True}, "clock transition exact49")
            self.assertTrue(all(r["transition"]["status"] == "limit_reached" for r in limit))
            # Clear clock in both worlds, then reuse #8's real native interactions and pulse assertions.
            await self.paired("__test_transition_fixture", {"scenario": "clear"})
            await self.paired("advance", {"ticks": 12})
            # "clear" retains the prototype floor. Remove that real construction before
            # #8's lateral-envelope fixtures; leaving it makes the new input interior.
            await self.paired("modify_blocks", {"blocks": [placement(point(x,y,z), "minecraft:air")
                for x in range(1024,1034) for y in range(79,83) for z in range(1024,1030)], "notify_neighbors": False})
            for device in ("minecraft:lever", "minecraft:stone_button", "minecraft:oak_button"):
                for mode in ("direct", "repeater"):
                    records = [await self.cycle(s, "piston", device, mode) for s in self.sessions]
                    for i, (a, b) in enumerate(zip(records[0]["reports"], records[1]["reports"])):
                        await self.compare(device+" "+mode+" activation"+str(i), [a,b])
                    self.assertEqual(records[0]["events"], records[1]["events"])
                    self.evidence["input_cycles"].append({"device": device, "mode": mode,
                       "on_delay": records[0]["on_delay"], "off_delay": records[0]["off_delay"],
                       "source_pulse": records[0]["source_pulse"], "signal_pulse": records[0]["signal_pulse"]})
            await self.fixture_pair("clock")
            await self.paired("__test_release_chunks", {"after_ticks": 2})
            await self.paired("transition", {"max_ticks": 40, "trace": True}, "partial readiness loss", error=True)
            await self.paired("__test_restore_chunks")
            await self.paired("__test_outside_influence")
            await self.paired("transition", {"trace": True}, "insufficient coverage")
            self.evidence["artifact_integrity"] = {r["environment"]["tick_execution"]: list(self.readers[id(s)].verified.values()) for s,r in zip(self.sessions,starts)}
            ref = self.evidence["comparisons"][1]["reports"][0]["trace"]
            corrupted = dict(ref, sha256="0"*64)
            try:
                self.readers[id(self.sessions[0])].rows(corrupted)
            except ValueError:
                self.evidence["negative_control"] = {"corrupted_hash_rejected": True}
            else:
                self.fail("Corrupt operation/trace artifact descriptor accepted")
            self.evidence["success"] = True
        finally:
            Path(os.environ["STONEBENCH_SPRINT_EVIDENCE"]).write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
            await self.stack.aclose()


if __name__ == "__main__":
    unittest.main(defaultTest="SprintEquivalence", verbosity=2)
