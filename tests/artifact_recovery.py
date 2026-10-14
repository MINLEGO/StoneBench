"""Verify immutable artifact access across an owned server restart."""
import json
import os
from pathlib import Path
import unittest

from construction import placement, point
from integration import TASK_ID, StoneBenchRuntimeIntegration


REGION_MIN = point(1056, 79, 1056)
REGION_MAX = point(1087, 80, 1063)
PAGE_LIMIT = 128


class ArtifactRecoveryIntegration(StoneBenchRuntimeIntegration):
    async def test_real_mcp_server_contract(self):
        phase = os.environ.get("STONEBENCH_TEST_PHASE")
        recovery_path = Path(os.environ["STONEBENCH_RECOVERY_FILE"])
        await self._connect()
        try:
            if phase == "seed":
                self.assertFalse(recovery_path.exists(), "Recovery file must be unique to this harness run")
                document = await self.seed_artifacts()
                recovery_path.parent.mkdir(parents=True, exist_ok=True)
                temporary_path = recovery_path.with_suffix(recovery_path.suffix + ".tmp")
                temporary_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
                temporary_path.replace(recovery_path)
            elif phase == "recovered":
                self.assertTrue(recovery_path.is_file(), "Seed phase did not write its shared recovery file")
                document = json.loads(recovery_path.read_text(encoding="utf-8"))
                await self.verify_recovered_artifacts(document)
            else:
                self.fail(f"Unexpected STONEBENCH_TEST_PHASE: {phase!r}")
        finally:
            await self.stack.aclose()

    async def seed_artifacts(self):
        servers = []
        for index, session in enumerate(self.sessions, 1):
            started = await self.call(session, "start_attempt", {"task_id": TASK_ID})
            self.assert_ok(started)
            attempt_id = started["attempt_id"]
            self.assertTrue(attempt_id)

            region = await self.call(
                session,
                "read_region",
                {"min": REGION_MIN, "max": REGION_MAX},
            )
            self.assert_ok(region)
            region_ref = region["blocks"]
            self.assertEqual(region_ref["count"], 512, region_ref)

            advanced = await self.call(session, "advance", {"ticks": 3, "trace": True})
            self.assert_ok(advanced)
            self.assertEqual(advanced["ticks_executed"], 3, advanced)
            self.assertTrue(advanced["continuity"]["complete"], advanced)
            trace_ref = advanced["trace"]
            self.assertEqual(trace_ref["count"], 3, trace_ref)

            description = await self.call(session, "describe_task")
            self.assert_ok(description)
            clock = self.clock(description)
            self.assertEqual(advanced["world_time"], clock["world_time"], advanced)
            self.assertEqual(advanced["simulation_ticks"], clock["simulation_ticks"], advanced)

            region_pages = await self.read_pages(session, region_ref, attempt_id, clock)
            trace_pages = await self.read_pages(session, trace_ref, attempt_id, clock)
            servers.append(
                {
                    "server_index": index,
                    "attempt_id": attempt_id,
                    "clock": clock,
                    "region": {"reference": region_ref, "pages": region_pages},
                    "trace": {"reference": trace_ref, "pages": trace_pages},
                }
            )
        return {"version": 1, "task_id": TASK_ID, "servers": servers}

    async def verify_recovered_artifacts(self, document):
        self.assertEqual(document.get("version"), 1, document)
        self.assertEqual(document.get("task_id"), TASK_ID, document)
        saved_servers = document.get("servers")
        self.assertIsInstance(saved_servers, list, document)
        self.assertEqual(len(saved_servers), len(self.sessions), document)

        for index, (session, saved) in enumerate(zip(self.sessions, saved_servers), 1):
            self.assertEqual(saved.get("server_index"), index, saved)
            attempt_id = saved["attempt_id"]
            clock = saved["clock"]

            # This happens before any attempt start; page contents and immutable references
            # must remain available from the server's persisted artifact store alone.
            for name in ("region", "trace"):
                artifact = saved[name]
                reference = artifact["reference"]
                self.assertTrue(reference.get("sha256"), reference)
                pages = await self.read_pages(session, reference, attempt_id, clock)
                self.assertEqual(pages, artifact["pages"], f"Recovered {name} pages differ")

            comparison = await self.call(
                session,
                "compare_traces",
                {"left": saved["trace"]["reference"]["artifact_id"],
                 "right": saved["trace"]["reference"]["artifact_id"]},
            )
            self.assert_ok(comparison)
            self.assert_read_only(comparison, attempt_id, clock)
            self.assertEqual(comparison["comparison"]["status"], "equal", comparison)

            region_read = await self.call(
                session,
                "read_region",
                {"min": REGION_MIN, "max": REGION_MAX},
            )
            self.assert_refused_without_mutation(region_read, attempt_id, clock, "read_region")

            description = await self.call(session, "describe_task")
            self.assert_refused_without_mutation(description, attempt_id, clock, "describe_task")

            advanced = await self.call(session, "advance", {"ticks": 1})
            self.assert_refused_without_mutation(advanced, attempt_id, clock, "advance")

            modified = await self.call(
                session,
                "modify_blocks",
                {"blocks": [placement(point(1024, 80, 1024), "minecraft:quartz_block")],
                 "notify_neighbors": False},
            )
            self.assert_refused_without_mutation(modified, attempt_id, clock, "modify_blocks")

            restarted = await self.call(session, "start_attempt", {"task_id": TASK_ID})
            self.assert_refused_without_mutation(restarted, attempt_id, clock, "start_attempt")
            error = restarted.get("error")
            self.assertIsInstance(error, dict, restarted)
            self.assertIn("already_started", error.get("message", ""), restarted)

    async def read_pages(self, session, reference, attempt_id, clock):
        pages = []
        offset = 0
        while True:
            page = await self.call(
                session,
                "read_artifact",
                {"artifact_id": reference["artifact_id"], "offset": offset, "limit": PAGE_LIMIT},
            )
            self.assert_ok(page)
            self.assert_read_only(page, attempt_id, clock)
            self.assertEqual(page["artifact"], reference, page)
            self.assertEqual(page["offset"], offset, page)
            self.assertLessEqual(len(page["entries"]), PAGE_LIMIT, page)
            pages.append(
                {
                    "offset": page["offset"],
                    "entries": page["entries"],
                    "next_offset": page["next_offset"],
                    "complete": page["complete"],
                }
            )
            if page["next_offset"] is None:
                self.assertTrue(page["complete"], page)
                break
            self.assertFalse(page["complete"], page)
            self.assertEqual(page["next_offset"], offset + len(page["entries"]), page)
            offset = page["next_offset"]
        self.assertEqual(sum(len(page["entries"]) for page in pages), reference["count"])
        return pages

    def clock(self, response):
        return {
            "world_time": response["world_time"],
            "simulation_ticks": response["simulation_ticks"],
            "preparation_ticks": response["preparation_ticks"],
        }

    def assert_read_only(self, response, attempt_id, clock):
        self.assertEqual(response["attempt_id"], attempt_id, response)
        self.assertIs(response["mutated"], False, response)
        self.assertIs(response["frozen"], True, response)
        if os.environ.get("STONEBENCH_TEST_PHASE") == "recovered":
            self.assertIs(response["artifact_recovery"], True, response)
            self.assertIs(response["simulation_resumable"], False, response)
            self.assertEqual(response["counters_source"], "last_persisted_operation", response)
        self.assertEqual(self.clock(response), clock, response)

    def assert_refused_without_mutation(self, response, attempt_id, clock, operation):
        self.assertEqual(response["status"], "error", f"{operation} unexpectedly succeeded: {response}")
        self.assertIsInstance(response.get("error"), dict, response)
        self.assert_read_only(response, attempt_id, clock)


if __name__ == "__main__":
    unittest.main(defaultTest="ArtifactRecoveryIntegration", verbosity=2)
