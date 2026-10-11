"""Focused #8/#9 integration: native input effects stay future work; no 160-cycle rerun."""
import json
import os
from pathlib import Path
import unittest
from input import InputRuntimeIntegration
from integration import TASK_ID


class TransitionInputsIntegration(InputRuntimeIntegration):
    async def test_real_mcp_server_contract(self):
        await self._connect()
        self.evidence = {"cycles": [], "transitions": []}
        try:
            for session in self.sessions:
                self.assert_ok(await self.call(session, "start_attempt", {"task_id": TASK_ID}))
            s = self.sessions[0]
            for device in ["minecraft:lever", "minecraft:stone_button", "minecraft:oak_button"]:
                for mode in ["direct", "repeater"]:
                    self.evidence["cycles"].append(await self.cycle(s, "piston", device, mode))
            for mode in ["direct", "repeater"]:
                await self.fixture(s, "torch", "minecraft:stone_button")
                self.assert_ok(await self.call(s, "prepare_input", {"mode": mode}))
                pressed = await self.call(s, "act_input", {"ticks": 1, "trace": True})
                self.assert_ok(pressed)
                pause = await self.call(s, "transition", {"max_ticks": 5, "trace": True})
                self.assert_ok(pause)
                self.assertEqual(pause["transition"]["status"], "limit_reached")
                self.assertIsNone(pause["transition"]["recognition_tick"])
                self.assertTrue(pause["final"]["state"]["block_ticks"])
                finished = await self.call(s, "transition", {"trace": True})
                self.assert_ok(finished)
                self.assertEqual(finished["transition"]["status"], "terminated")
                self.assertGreater(finished["transition"]["external_input_events"], 0)
                self.assertTrue(finished["continuity"]["complete"])
                ticks = await self.pages(s, finished["trace"], 256)
                self.assertTrue(all(row["rest"]["status"] == "running" for row in ticks[:-1]))
                self.assertEqual(ticks[-1]["rest"]["status"], "terminated")
                final = await self.snapshot(s, finished["final"])
                description = await self.call(s, "describe_task")
                driver = tuple(description["input"]["driver"][axis] for axis in ("x", "y", "z"))
                self.assertEqual(final[driver]["parameters"]["powered"], "false")
                self.evidence["transitions"].append({"mode": mode, "pressed": pressed, "pause": pause, "finished": finished})
            # Wrong scheduled type at an adapter device is not an expected external callback.
            await self.fixture(s, "torch", "minecraft:stone_button")
            injected = await self.call(s, "__test_transition_external_tick")
            self.assert_ok(injected)
            pending = await self.call(s, "transition", {"max_ticks": 3, "trace": True})
            self.assert_ok(pending)
            self.assertEqual(pending["transition"]["status"], "limit_reached")
            completed = await self.call(s, "transition", {"trace": True})
            self.assert_ok(completed)
            self.assertEqual(completed["transition"]["status"], "terminated")
            self.assertEqual(completed["transition"]["external_input_events"], 0)
            self.assertGreater(completed["transition"]["internal_events"], 0)
            events = await self.pages(s, completed["intratick_events"], 256)
            self.assertTrue(any(e["kind"] == "scheduled_block_tick" and e["detail"]["block"] == "minecraft:stone" for e in events))
            self.evidence["unexpected_adapter_callback"] = {"injected": injected, "pending": pending, "completed": completed}
        finally:
            output = Path(os.environ.get("STONEBENCH_TRANSITION_INPUT_EVIDENCE", ".runtime/transition-input-summary.json"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
            await self.stack.aclose()


if __name__ == "__main__":
    unittest.main(defaultTest="TransitionInputsIntegration", verbosity=2)
