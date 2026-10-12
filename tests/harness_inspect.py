"""Native Inspect loop plus real Minecraft/MCP tools, without paid inference."""
import asyncio
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.harness.budget import Budget
from app.harness.inspect_task import stonebench_task
import app.harness.scripted
from inspect_ai import eval_async
from inspect_ai.model import ChatMessageAssistant, ChatCompletionChoice, ModelOutput, ModelUsage, get_model
from inspect_ai.tool import ToolCall
import integration
import verification


class HarnessRuntimeIntegration(verification.VerificationRuntimeIntegration):
    async def test_real_mcp_server_contract(self):
        await self._connect()
        evidence = {"scenarios": []}
        try:
            first = self.sessions[0]
            self.assert_ok(await self.call(first, "start_attempt", {"task_id": integration.TASK_ID, "budget_tokens": 300000}))
            # Early incomplete checkpoint; then a real conforming door and a newer checkpoint.
            self.assert_ok(await self.call(first, "modify_blocks", {"blocks": [{"x": 1024, "y": 79, "z": 1024, "block": "minecraft:stone"}], "notify_neighbors": True}))
            self.assert_ok(await self.call(first, "transition", {"max_ticks": 20, "trace": True}))
            early = await self.call(first, "create_checkpoint")
            self.assert_ok(early)
            chosen = early["checkpoint"]["checkpoint_id"]
            conformant = await self.prepare_powered_checkpoint(first)
            best_id = conformant["checkpoint_id"]
            best = await self.verify(first, best_id, "none")
            self.assertEqual(best["verdict"], "conforms_to_alpha", self.report_context(best))
            self.assert_ok(await self.call(first, "transition", {"max_ticks": 20, "trace": True}))
            latest = await self.call(first, "create_checkpoint")
            self.assert_ok(latest)
            latest_id = latest["checkpoint"]["checkpoint_id"]
            self.assertNotEqual(chosen, best_id)
            self.assertNotEqual(chosen, latest_id)
            before = await self.call(first, "verification_snapshot")
            baseline = self.frozen_snapshot(before)
            url = integration.server_urls()[0]
            root = Path(os.environ.get("STONEBENCH_HARNESS_EVIDENCE", "app/harness/.runtime/evidence"))
            root.mkdir(parents=True, exist_ok=True)

            for scenario in ("selected_older", "invalid_id", "no_submission", "missing_usage", "long_reasoning", "overshoot"):
                task, attempt = stonebench_task(url, Budget(300000, 4000, 4000, 20000, 2000, final_calls=120),
                    root / scenario, initialize=False)
                script = Scenario(scenario, chosen, latest_id, self, attempt)
                model = get_model("stonebench-scripted/controlled", script=script)
                logs = await eval_async(task, model=model, log_dir=str(root / "inspect-logs"), log_format="json",
                                         log_model_api=False, ctl_server=False, max_samples=1, max_tasks=1)
                log = logs[0]
                self.assertEqual(log.status, "success", str(log.error))
                self.assertEqual(len(log.samples), 1)
                usage = log.stats.model_usage
                recorded = attempt.ledger.total_tokens
                if scenario == "missing_usage":
                    self.assertIsNone(recorded)
                elif scenario != "overshoot":
                    self.assertEqual(sum(row.total_tokens for row in usage.values()), recorded)
                self.assertTrue(script.phases, scenario)
                if scenario not in {"long_reasoning", "overshoot"}:
                    self.assertEqual(script.phases[0], "construction", script.phases)
                if scenario != "overshoot":
                    self.assertEqual(script.phases[-1], "finalization", script.phases)
                self.assertEqual(attempt.ledger.phase, "finalization")
                if scenario == "selected_older":
                    self.assertEqual(attempt.selected, chosen)
                    self.assertEqual(attempt.report["checkpoint_id"], chosen)
                    self.assertNotEqual(attempt.report["verification"]["verdict"], "conforms_to_alpha")
                    self.assertEqual(attempt.report["verification"]["checkpoint_id"], chosen)
                    refused = [json.loads(line) for line in (attempt.root / "events.jsonl").read_text().splitlines() if '"tool_refused"' in line]
                    self.assertGreaterEqual(len(refused), 7, refused)
                    self.assertTrue(script.verification_finished)
                else:
                    self.assertIsNone(attempt.selected)
                    self.assertEqual(attempt.report["status"], "no_submission")
                after = await self.call(first, "verification_snapshot")
                self.assertIsNone(verification.first_difference(baseline, self.frozen_snapshot(after)), scenario)
                evidence["scenarios"].append({"scenario": scenario, "selected": attempt.selected, "result": attempt.report,
                    "phases": script.phases, "inspect_usage": {key: value.model_dump() for key, value in usage.items()},
                    "ledger_total": recorded, "known_subtotal": attempt.ledger.known_tokens,
                    "working_difference": None, "calls": attempt.ledger.calls})
            evidence.update(chosen_checkpoint_id=chosen, best_conforming_checkpoint_id=best_id, latest_checkpoint_id=latest_id,
                            best_verdict=best["verdict"])
        finally:
            output = Path(os.environ.get("STONEBENCH_HARNESS_SUMMARY", "app/harness/.runtime/summary.json"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            await self.stack.aclose()


class Scenario:
    def __init__(self, scenario, chosen, latest, test, attempt):
        self.scenario, self.chosen, self.latest = scenario, chosen, latest
        self.test, self.attempt = test, attempt
        self.index = 0
        self.phases = []
        self.request_id = None
        self.verification_finished = False

    async def __call__(self, messages, tools, config):
        notice = next(message.content for message in reversed(messages) if message.role == "user" and isinstance(message.content,str) and message.content.startswith("StoneBench phase/budget:"))
        phase = "finalization" if '"phase": "finalization"' in notice else "construction"
        self.phases.append(phase)
        self.test.assertFalse(config.parallel_tool_calls)
        self.test.assertIn(config.max_tokens, {4000, 24000})
        calls = []
        if self.index == 0:
            calls = [("describe_task", {})]
        elif self.scenario == "selected_older":
            if self.index == 1:
                self.test.assertEqual(phase, "finalization")
                calls = [("modify_blocks", {"blocks": [{"x":1024,"y":79,"z":1024,"block":"minecraft:air"}]}),
                    ("advance", {"ticks":1}), ("transition", {"max_ticks":20}),
                    ("act_input", {"ticks":1}), ("prepare_input", {"mode":"direct"}),
                    ("declare_input", {"device":"minecraft:lever", "position":{"x":1024,"y":80,"z":1024},"orientation":"west","input_block":{"x":1025,"y":80,"z":1024}}),
                    ("restore_checkpoint", {"checkpoint_id":self.latest}), ("create_checkpoint", {}),
                    ("verify_checkpoint", {"checkpoint_id":self.latest})]
            elif self.index >= 2:
                # Script reads its own retained tool evidence, rather than fabricating a verifier result.
                retained = [json.loads(file.read_text(encoding="utf-8")) for file in sorted(self.attempt.root.glob("tool-*.json"))]
                jobs = [item.get("verification",{}) for item in retained if isinstance(item,dict) and item.get("verification")]
                if self.request_id is None:
                    self.request_id = next(job["request_id"] for job in reversed(jobs) if "request_id" in job)
                if any("verdict" in job for job in jobs):
                    self.verification_finished = True
                    calls = [("submit_checkpoint", {"checkpoint_id":self.chosen})]
                else:
                    await asyncio.sleep(2)
                    calls = [("verification_status", {"request_id":self.request_id})]
                    if self.index == 2:
                        calls += [("verification_snapshot", {}), ("restore_checkpoint", {"checkpoint_id":self.latest}),
                                  ("modify_blocks", {}), ("__test_verification_mutate", {})]
        elif self.scenario == "invalid_id" and self.index == 1:
            calls = [("submit_checkpoint", {"checkpoint_id":"00000000-0000-0000-0000-000000000000"})]
        elif self.scenario in {"missing_usage", "long_reasoning"} and self.index == 1:
            calls = [("list_checkpoints", {})]
        usage = ModelUsage(input_tokens=50, output_tokens=50, total_tokens=100)
        if self.index == 0:
            usage = None if self.scenario == "missing_usage" else ModelUsage(input_tokens=258000, output_tokens=2000, total_tokens=260000, reasoning_tokens=1900)
            if self.scenario == "long_reasoning":
                usage = ModelUsage(input_tokens=230000, output_tokens=50000, total_tokens=280000, reasoning_tokens=49000)
            if self.scenario == "overshoot":
                usage = ModelUsage(input_tokens=290000, output_tokens=100000, total_tokens=390000, reasoning_tokens=99900)
        self.index += 1
        return ModelOutput(model="stonebench-scripted/controlled", usage=usage, choices=[ChatCompletionChoice(
            message=ChatMessageAssistant(content="Scripted decision", tool_calls=[ToolCall(id=f"{self.index}-{i}", function=name, arguments=args) for i,(name,args) in enumerate(calls)] or None),
            stop_reason="tool_calls" if calls else "stop")])


if __name__ == "__main__":
    unittest.main()
