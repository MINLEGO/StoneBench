"""Real original-server continuation, three restarts, 83 exact observations per replay."""
import asyncio
import copy
from contextlib import AsyncExitStack
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import time
import unittest
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from input import InputRuntimeIntegration
from integration import TASK_ID, server_urls
from transition_evidence import Evidence


class CheckpointRuntimeIntegration(InputRuntimeIntegration):
    async def expand(self, reader, value):
        if isinstance(value, dict):
            if "artifact_id" in value:
                return [await self.expand(reader, item) for item in reader.rows(value)]
            return {key: await self.expand(reader, item) for key, item in value.items()}
        if isinstance(value, list):
            return [await self.expand(reader, item) for item in value]
        return value

    async def reconnect(self, url, request_id):
        deadline = time.monotonic() + 180
        last = None
        while time.monotonic() < deadline:
            connection = AsyncExitStack()
            await connection.__aenter__()
            try:
                client = await connection.enter_async_context(httpx.AsyncClient(timeout=5))
                streams = await connection.enter_async_context(streamable_http_client(url, http_client=client))
                session = await connection.enter_async_context(ClientSession(streams[0], streams[1], read_timeout_seconds=timedelta(seconds=30)))
                await session.initialize()
                description = await self.call(session, "describe_task")
                restored = description.get("restoration", {})
                if restored.get("request_id") == request_id:
                    self.reconnections.append(connection)
                    self.assert_ok(description)
                    self.assertEqual(restored["comparison"]["status"], "equal", restored)
                    self.assertEqual(restored["comparison"]["useful_ticks_before_comparison"], 0)
                    self.assertEqual(restored["preparation_game_ticks"], 0)
                    self.assertTrue(description["frozen"])
                    self.assertTrue(description["chunks_ready"])
                    return session, description
            except Exception as error:
                last = str(error)
            await connection.aclose()
            await asyncio.sleep(.5)
        self.fail("Checkpoint restart did not finish: " + str(last))

    async def original_sequence(self, session, reader):
        rows = []
        initial = await self.call(session, "__test_checkpoint_snapshot")
        self.assert_ok(initial)
        rows.append({"tick": 0, "event": "initial", "state": initial["checkpoint_state"]})
        for edge, offset in (("input-on", 0), ("input-off", 40)):
            interaction = await self.call(session, "__test_checkpoint_toggle")
            self.assert_ok(interaction)
            self.assertEqual(interaction["ticks_executed"], 0)
            rows.append({"tick": offset, "event": edge,
                         "observation": await self.expand(reader, interaction["final"]),
                         "events": await self.expand(reader, interaction["intratick_events"])})
            advance = await self.call(session, "advance", {"ticks": 40, "trace": True})
            self.assert_ok(advance)
            self.assertEqual(advance["ticks_executed"], 40)
            self.assertTrue(advance["continuity"]["complete"])
            samples = await self.expand(reader, advance["trace"])
            self.assertEqual(len(samples), 40)
            rows.extend({"tick": offset + tick + 1, "event": "tick", "observation": sample}
                        for tick, sample in enumerate(samples))
        self.assertEqual(len(rows), 83)
        return rows

    async def create(self, session):
        settled = await self.call(session, "transition", {"trace": True})
        self.assert_ok(settled)
        self.assertEqual(settled["transition"]["status"], "terminated")
        result = await self.call(session, "create_checkpoint")
        self.assert_ok(result)
        self.assertTrue(result["rest_established"])
        self.assertFalse(result["door_conformity_required"])
        self.assertEqual(result["ticks_executed"], 0)
        return result["checkpoint"]

    async def restored(self, session, identifier, url):
        result = await self.call(session, "restore_checkpoint", {"checkpoint_id": identifier})
        self.assert_ok(result)
        self.assertTrue(result["mutated"])
        self.assertEqual(result["restore"]["status"], "restart_required")
        return await self.reconnect(url, result["restore"]["request_id"])

    async def test_real_mcp_server_contract(self):
        await self._connect()
        self.reconnections = []
        self.evidence = {"replays": [], "negative_controls": [], "prototype_commit": "7bcdf3daaab752eef6d3f14011427c30c62f0e51"}
        try:
            starts = [await self.call(session, "start_attempt", {"task_id": TASK_ID}) for session in self.sessions]
            for start in starts:
                self.assert_ok(start)
            session, second = self.sessions
            root = Path(starts[0]["environment"]["server_directory"])
            reader = Evidence(root)
            no_rest = await self.call(session, "create_checkpoint")
            self.assert_error(no_rest, "validation")
            self.evidence["negative_controls"].append({"no_established_rest": no_rest})
            self.assert_ok(await self.call(session, "__test_checkpoint_fixture"))
            self.assert_ok(await self.call(session, "advance", {"ticks": 19}))
            first = await self.create(session)
            second_id = (await self.call(session, "create_checkpoint"))["checkpoint"]
            self.assertNotEqual(first["checkpoint_id"], second_id["checkpoint_id"])
            self.evidence["checkpoints"] = [first, second_id]
            reference = await self.original_sequence(session, reader)
            self.evidence["reference"] = reference
            encoded = json.dumps(reference, sort_keys=True, separators=(",", ":")).encode()
            reference_hash = hashlib.sha256(encoded).hexdigest()
            self.evidence["reference_sha256"] = reference_hash
            for replay in range(3):
                session, description = await self.restored(session, first["checkpoint_id"], server_urls()[0])
                current = await self.original_sequence(session, reader)
                self.assertEqual(current, reference, "Exact NBT/inventory/absolute-clock/event replay differs")
                listed = await self.call(session, "list_checkpoints")
                self.assert_ok(listed)
                self.assertEqual({item["checkpoint_id"] for item in listed["checkpoints"]}, {first["checkpoint_id"], second_id["checkpoint_id"]})
                self.evidence["replays"].append({"index": replay + 1, "observations": len(current), "exact_equal": True,
                    "sha256": hashlib.sha256(json.dumps(current, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                    "description": description, "checkpoint_manifest_sha256": first["manifest_sha256"]})
            # Alter one saved proof field only; the comparator must identify its exact location.
            initial = reference[0]["state"]
            negative = copy.deepcopy(initial)
            block = negative["state"]["blocks"]["7,80,3"]
            self.assertEqual(block["inventory"][0]["count"], 7)
            count = block["nbt"]["value"]["Items"]["value"][0]["value"]["count"]
            self.assertEqual(count["value"], "7")
            count["value"] = "8"
            compared = await self.call(session, "__test_checkpoint_compare", {"expected": initial, "actual": negative})
            self.assert_ok(compared)
            comparison = compared["comparison"]
            self.assertEqual(comparison["status"], "different")
            self.assertEqual(comparison["first_tick"], 0)
            self.assertEqual(comparison["first_fields"][0]["field"], "$.state.blocks.7,80,3.nbt.value.Items.value[0].value.count.value")
            self.evidence["negative_controls"].append({"seven_to_eight": comparison})
            # The floor fixture is test-only. Check current production input integration separately.
            await self.fixture(second, "repeater-1", "minecraft:lever")
            self.assert_ok(await self.call(second, "prepare_input", {"mode": "repeater"}))
            production_checkpoint = await self.create(second)
            second_reader = Evidence(starts[1]["environment"]["server_directory"])
            production_reference = []
            for _ in range(2):
                report = await self.call(second, "act_input", {"ticks": 40, "trace": True})
                self.assert_ok(report)
                production_reference.append(await self.expand(second_reader, report["trace"]))
            second, description = await self.restored(second, production_checkpoint["checkpoint_id"], server_urls()[1])
            production_replay = []
            for _ in range(2):
                report = await self.call(second, "act_input", {"ticks": 40, "trace": True})
                self.assert_ok(report)
                production_replay.append(await self.expand(second_reader, report["trace"]))
            self.assertEqual(production_reference, production_replay)
            self.evidence["production_input_replay"] = {"ticks": 80, "mode": "repeater", "device": "lever", "exact_equal": True,
                                                       "restoration": description["restoration"]}
            self.evidence["artifact_hashes"] = reader.verified
            self.evidence["success"] = True
        finally:
            output = Path(os.environ.get("STONEBENCH_CHECKPOINT_EVIDENCE", ".runtime/checkpoint-summary.json"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
            for connection in reversed(self.reconnections):
                await connection.aclose()
            await self.stack.aclose()


if __name__ == "__main__":
    unittest.main(defaultTest="CheckpointRuntimeIntegration", verbosity=2)
