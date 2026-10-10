from contextlib import AsyncExitStack
from importlib.metadata import version
import asyncio
import os
import time
import unittest

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


MCP_VERSION = "1.26.0"
TASK_ID = "2x2-volume"
RULES_REFERENCE = (
    "https://docs.google.com/document/d/"
    "1kDNXIvQ8uAMU5qRFXIk6nLxbVliIjcMu1MjHjLJrRH4/edit"
)
BLOCK_POSITION = {"x": 1024, "y": 80, "z": 1024}
EXPECTED_FRAME = {
    (1024, 80, 1024),
    (1025, 80, 1024),
    (1024, 81, 1024),
    (1025, 81, 1024),
}


def server_urls():
    raw_ports = os.environ.get("STONEBENCH_MCP_PORTS", "18765,18766")
    try:
        ports = [int(value.strip()) for value in raw_ports.split(",")]
    except ValueError as exc:
        raise RuntimeError("STONEBENCH_MCP_PORTS must contain two integer ports") from exc
    if len(ports) != 2 or any(port < 1 or port > 65535 for port in ports):
        raise RuntimeError("STONEBENCH_MCP_PORTS must contain exactly two valid ports")
    return [f"http://127.0.0.1:{port}/mcp" for port in ports]


class StoneBenchRuntimeIntegration(unittest.IsolatedAsyncioTestCase):
    async def _connect(self):
        self.assertEqual(version("mcp"), MCP_VERSION, "Install the pinned MCP SDK from docs/runtime-tests.md")
        self.stack = AsyncExitStack()
        await self.stack.__aenter__()
        self.sessions = []
        for url in server_urls():
            http_client = await self.stack.enter_async_context(
                httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=420.0))
            )
            read_stream, write_stream, _ = await self.stack.enter_async_context(
                streamable_http_client(url, http_client=http_client)
            )
            session = await self.stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            self.sessions.append(session)


    async def call(self, session, name, arguments=None):
        result = await session.call_tool(name, arguments or {})
        payload = result.structuredContent
        self.assertIsInstance(payload, dict, f"{name} did not return MCP structuredContent")
        self.assertIs(result.isError, payload["status"] == "error")
        for key in ("operation_id", "attempt_id", "phase", "status"):
            self.assertIn(key, payload, f"{name} omitted {key}")
        return payload

    def assert_ok(self, payload):
        self.assertEqual(payload["status"], "ok", payload)

    def assert_error(self, payload, kind, code=None):
        self.assertEqual(payload["status"], "error", payload)
        error = payload.get("error")
        self.assertIsInstance(error, dict, payload)
        self.assertEqual(error.get("kind"), kind, payload)
        self.assertTrue(error.get("code"), payload)
        if code is not None:
            self.assertEqual(error["code"], code, payload)

    async def wait_for_chunks(self, session, expected, timeout=120):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            description = await self.call(session, "describe_task")
            if description.get("chunks_ready") is expected:
                return description
            await asyncio.sleep(0.5)
        self.fail(f"Timed out waiting for chunks_ready={expected}")

    async def read_fixture(self, session):
        return await self.call(
            session,
            "read_blocks",
            {"positions": [BLOCK_POSITION]},
        )

    async def assert_air_at_fixture(self, session):
        result = await self.read_fixture(session)
        self.assert_ok(result)
        blocks = result.get("blocks")
        self.assertIsInstance(blocks, list, result)
        self.assertEqual(len(blocks), 1, result)
        self.assertEqual(blocks[0].get("state"), "Block{minecraft:air}", result)

    def assert_description(self, description, known_budget=1):
        task = description.get("task")
        environment = description.get("environment")
        self.assertIsInstance(task, dict, description)
        self.assertIsInstance(environment, dict, description)

        self.assertEqual(task.get("task_id"), TASK_ID, description)
        self.assertEqual(task.get("category"), "regular DOOR", description)
        self.assertEqual(task.get("width"), 2, description)
        self.assertEqual(task.get("height"), 2, description)
        self.assertEqual(task.get("objective"), "minimize_volume", description)
        self.assertEqual(task.get("rules_reference"), RULES_REFERENCE, description)
        self.assertEqual(task["budget_tokens"], known_budget, description)
        self.assertEqual(task.get("minecraft"), "1.21.11", description)

        passage = task.get("passage")
        self.assertIsInstance(passage, dict, description)
        self.assertEqual(passage.get("origin"), BLOCK_POSITION, description)
        self.assertEqual(passage.get("normal"), "+Z", description)
        self.assertEqual(passage.get("vertical_axis"), "+Y", description)
        self.assertEqual(passage.get("horizontal_axis"), "+X", description)
        frame = {
            (position["x"], position["y"], position["z"])
            for position in task.get("expected_frame", [])
        }
        self.assertEqual(frame, EXPECTED_FRAME, description)

        self.assertEqual(environment.get("minecraft"), "1.21.11", description)
        self.assertEqual(environment.get("yarn"), "1.21.11+build.3", description)
        self.assertEqual(environment.get("fabric_loader"), "0.19.5", description)
        self.assertEqual(environment.get("controller"), "0.1.0", description)
        self.assertTrue(str(environment.get("java", "")).startswith("21"), description)
        self.assertEqual(environment.get("tick_rate"), 20, description)
        self.assertEqual(environment.get("generator"), "flat_air", description)
        self.assertEqual(environment.get("random_tick_speed"), 0, description)
        self.assertIs(environment.get("mob_spawning"), False, description)
        self.assertIs(environment.get("advance_weather"), False, description)
        self.assertIs(environment.get("players_allowed"), False, description)

    async def test_real_mcp_server_contract(self):
        await self._connect()
        try:
            await self._exercise_contract()
        finally:
            # AnyIO scopes must be closed in the same task that entered them.
            await self.stack.aclose()

    async def _exercise_contract(self):
        session_a, session_b = self.sessions
        tool_names = set()
        for session in self.sessions:
            tool_names.update(tool.name for tool in (await session.list_tools()).tools)
        self.assertTrue(
            {
                "start_attempt",
                "describe_task",
                "read_blocks",
                "advance",
                "__test_place_block",
                "__test_release_chunks",
                "__test_restore_chunks",
            }.issubset(tool_names),
            tool_names,
        )

        before_start = await self.call(session_a, "advance", {"ticks": 1})
        self.assert_error(before_start, "validation")
        self.assertIsNone(before_start["attempt_id"])
        self.assertEqual(before_start["ticks_executed"], 0)

        start_a = await self.call(
            session_a,
            "start_attempt",
            {"task_id": TASK_ID, "budget_tokens": 1},
        )
        start_b = await self.call(
            session_b,
            "start_attempt",
            {"task_id": TASK_ID},
        )
        self.assert_ok(start_a)
        self.assert_ok(start_b)
        for start in (start_a, start_b):
            self.assertIs(start.get("preparation_initial_loaded"), True, start)
            self.assertIs(start.get("preparation_initial_ready"), False, start)
            preparation_ticks = start.get("preparation_ticks")
            self.assertIsInstance(preparation_ticks, int, start)
            self.assertGreater(preparation_ticks, 0, start)
        attempt_a = start_a["attempt_id"]
        attempt_b = start_b["attempt_id"]
        self.assertNotEqual(attempt_a, attempt_b, "separate server processes must create separate attempts")

        duplicate = await self.call(
            session_a,
            "start_attempt",
            {"task_id": TASK_ID, "budget_tokens": 1},
        )
        self.assert_error(duplicate, "validation", "invalid_arguments")
        self.assertTrue(
            duplicate["error"].get("message", "").startswith("already_started"),
            duplicate,
        )
        self.assertEqual(duplicate["attempt_id"], attempt_a)

        description_a = await self.wait_for_chunks(session_a, True)
        description_b = await self.wait_for_chunks(session_b, True)
        self.assert_description(description_a)
        self.assert_description(description_b, known_budget=None)

        await self.assert_air_at_fixture(session_a)
        await self.assert_air_at_fixture(session_b)

        placed = await self.call(session_a, "__test_place_block")
        self.assert_ok(placed)
        stone = await self.read_fixture(session_a)
        self.assert_ok(stone)
        self.assertEqual(stone["blocks"][0]["state"], "Block{minecraft:stone}", stone)
        await self.assert_air_at_fixture(session_b)

        ticks_before_invalid = (await self.call(session_a, "describe_task"))["simulation_ticks"]
        for ticks in (0, 6001, 1.5, "1", True):
            invalid = await self.call(session_a, "advance", {"ticks": ticks})
            self.assert_error(invalid, "validation")
            self.assertEqual(invalid.get("ticks_executed"), 0, invalid)
        after_invalid = await self.call(session_a, "describe_task")
        self.assertEqual(after_invalid["simulation_ticks"], ticks_before_invalid)

        released = await self.call(
            session_b,
            "__test_release_chunks",
            {"after_ticks": 0},
        )
        self.assert_ok(released)
        unavailable_state = await self.wait_for_chunks(session_b, False)
        unavailable = await self.call(session_b, "advance", {"ticks": 1})
        self.assert_error(unavailable, "infrastructure", "chunks_unavailable")
        self.assertEqual(unavailable.get("ticks_executed"), 0, unavailable)
        self.assertEqual(unavailable.get("simulation_ticks"), unavailable_state["simulation_ticks"])
        self.assertEqual(unavailable.get("world_time"), unavailable_state["world_time"])
        self.assertIs(unavailable.get("frozen"), True, unavailable)

        restored = await self.call(session_b, "__test_restore_chunks")
        self.assert_ok(restored)
        await self.wait_for_chunks(session_b, True)

        before_loss = await self.call(session_b, "describe_task")
        await self.call(
            session_b,
            "__test_release_chunks",
            {"after_ticks": 1},
        )
        interrupted = await self.call(session_b, "advance", {"ticks": 60})
        self.assert_error(interrupted, "infrastructure", "chunks_unavailable")
        executed_before_loss = interrupted.get("ticks_executed")
        self.assertIsInstance(executed_before_loss, int, interrupted)
        self.assertGreaterEqual(executed_before_loss, 1, interrupted)
        self.assertLess(executed_before_loss, 60, interrupted)
        self.assertEqual(
            interrupted.get("simulation_ticks"),
            before_loss["simulation_ticks"] + executed_before_loss,
            interrupted,
        )
        self.assertEqual(
            interrupted.get("world_time"),
            before_loss["world_time"] + executed_before_loss,
            interrupted,
        )
        await asyncio.sleep(1.25)
        after_loss_sleep = await self.call(session_b, "describe_task")
        self.assertEqual(after_loss_sleep["simulation_ticks"], interrupted["simulation_ticks"])
        self.assertEqual(after_loss_sleep["world_time"], interrupted["world_time"])
        self.assertIs(after_loss_sleep.get("frozen"), True, after_loss_sleep)

        restored = await self.call(session_b, "__test_restore_chunks")
        self.assert_ok(restored)
        await self.wait_for_chunks(session_b, True)

        first_advance = await self.call(session_a, "advance", {"ticks": 4})
        self.assert_ok(first_advance)
        self.assertEqual(first_advance.get("ticks_executed"), 4, first_advance)
        self.assertIs(first_advance.get("frozen"), True, first_advance)
        before_sleep = await self.call(session_a, "describe_task")
        await asyncio.sleep(1.25)
        after_sleep = await self.call(session_a, "describe_task")
        self.assertEqual(after_sleep["simulation_ticks"], before_sleep["simulation_ticks"])
        self.assertEqual(after_sleep["world_time"], before_sleep["world_time"])
        self.assertIs(after_sleep.get("frozen"), True, after_sleep)

        before_concurrent = after_sleep["simulation_ticks"]
        concurrent = await asyncio.gather(
            self.call(session_a, "advance", {"ticks": 20}),
            self.call(session_a, "advance", {"ticks": 20}),
        )
        for result in concurrent:
            self.assert_ok(result)
            self.assertEqual(result.get("ticks_executed"), 20, result)
            self.assertIs(result.get("frozen"), True, result)
        after_concurrent = await self.call(session_a, "describe_task")
        self.assertEqual(after_concurrent["simulation_ticks"], before_concurrent + 40)

        before_max = after_concurrent["simulation_ticks"]
        maximum_ticks = 40 if os.environ.get("STONEBENCH_TEST_SMOKE") == "1" else 6000
        print(f"Checking final advance of {maximum_ticks} ticks", flush=True)
        maximum = await self.call(session_a, "advance", {"ticks": maximum_ticks})
        self.assert_ok(maximum)
        self.assertEqual(maximum.get("ticks_executed"), maximum_ticks, maximum)
        self.assertEqual(maximum.get("simulation_ticks"), before_max + maximum_ticks, maximum)
        self.assertIs(maximum.get("frozen"), True, maximum)
        after_max = await self.call(session_a, "describe_task")
        self.assertEqual(after_max["simulation_ticks"], before_max + maximum_ticks)
        self.assertIs(after_max.get("frozen"), True, after_max)


if __name__ == "__main__":
    unittest.main(verbosity=2)
