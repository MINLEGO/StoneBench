"""Small native-Inspect checks supplement, rather than replace, real MCP suite."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.harness.budget import Budget
from app.harness.inspect_task import Attempt, budgeted_generation
import app.harness.scripted
from inspect_ai import Task, eval_async
from inspect_ai.agent import react
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput, ModelUsage, ChatMessageAssistant, ChatCompletionChoice, get_model, GenerateConfig
from inspect_ai.tool import ToolCall, tool


class NativeInspectTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_loop_usage_and_reserve(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempt = Attempt(Budget(30000, 1000, 1000, 4000, 500), Path(tmp)/"attempt")
            calls=[]
            @tool
            def read():
                async def execute() -> str:
                    """Read a value."""
                    return "known"
                return execute
            def scripted(messages, tools, config):
                phase=attempt.ledger.phase
                calls.append((phase,config.max_tokens))
                usage=ModelUsage(input_tokens=24000,output_tokens=1000,total_tokens=25000,reasoning_tokens=900) if len(calls)==1 else ModelUsage(input_tokens=100,output_tokens=100,total_tokens=200)
                return ModelOutput(model="stonebench-scripted/test",usage=usage, choices=[ChatCompletionChoice(
                    message=ChatMessageAssistant(content="scripted",tool_calls=[ToolCall(id="read",function="read",arguments={})] if len(calls)==1 else None),
                    stop_reason="tool_calls" if len(calls)==1 else "stop")])
            async def keep_running(state):
                return bool(state.output.message.tool_calls) and attempt.ledger.can_continue()
            task=Task(dataset=[Sample(input="Read then conclude")], solver=react(tools=[read()],submit=False,
                model=budgeted_generation(attempt,GenerateConfig()),on_continue=keep_running),token_limit=30000)
            logs=await eval_async(task,model=get_model("stonebench-scripted/native",script=scripted),log_dir=str(Path(tmp)/"logs"),log_model_api=False,ctl_server=False)
            self.assertEqual(logs[0].status,"success",logs[0].error)
            self.assertEqual(calls,[("construction",1000),("finalization",5000)])
            self.assertEqual(attempt.ledger.total_tokens,25200)
            self.assertEqual(sum(usage.total_tokens for usage in logs[0].stats.model_usage.values()),25200)

    async def test_native_limit_records_completed_provider_overshoot(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempt=Attempt(Budget(30000,1000,1000,4000,500),Path(tmp)/"attempt")
            def scripted(messages,tools,config):
                output = ModelOutput.from_content(model="stonebench-scripted/overshoot",content="too much")
                output.usage=ModelUsage(input_tokens=29000,output_tokens=9000,total_tokens=38000,reasoning_tokens=8900)
                return output
            task=Task(dataset=[Sample(input="Overshoot")],solver=react(submit=False,
                model=budgeted_generation(attempt,GenerateConfig())),token_limit=30000)
            log=(await eval_async(task,model=get_model("stonebench-scripted/overshoot",script=scripted),
                log_dir=str(Path(tmp)/"logs"),log_model_api=False,ctl_server=False))[0]
            self.assertEqual(log.status,"success",log.error)
            self.assertEqual(attempt.ledger.total_tokens,38000)
            self.assertEqual(attempt.ledger.phase,"finalization")
            self.assertTrue(attempt.ledger.calls[-1]["budget_exceeded_observed"])
            self.assertEqual(sum(row.total_tokens for row in log.stats.model_usage.values()),38000)

    async def test_failed_provider_call_has_unavailable_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempt = Attempt(Budget(30000, 1000, 1000, 4000, 500), Path(tmp)/"attempt")
            def scripted(messages, tools, config):
                raise RuntimeError("Controlled provider failure before usage")
            task = Task(dataset=[Sample(input="Fail")], solver=react(submit=False,
                model=budgeted_generation(attempt, GenerateConfig())), token_limit=30000)
            log = (await eval_async(task,
                model=get_model("stonebench-scripted/failure", script=scripted),
                log_dir=str(Path(tmp)/"logs"), log_model_api=False, ctl_server=False))[0]
            self.assertEqual(log.status, "error")
            self.assertIsNone(attempt.ledger.total_tokens)
            self.assertEqual(attempt.ledger.phase, "finalization")
            self.assertIsNone(attempt.ledger.calls[-1]["usage"])
    async def test_missing_provider_usage_stays_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempt=Attempt(Budget(30000,1000,1000,4000,500),Path(tmp)/"attempt")
            @tool
            def consult():
                async def execute() -> str:
                    """Consult."""
                    return "ok"
                return execute
            count=0
            def scripted(messages,tools,config):
                nonlocal count
                count+=1
                return ModelOutput(model="stonebench-scripted/missing",usage=None,choices=[ChatCompletionChoice(
                    message=ChatMessageAssistant(content="mock",tool_calls=[ToolCall(id="1",function="consult",arguments={})] if count==1 else None),stop_reason="tool_calls" if count==1 else "stop")])
            async def keep_running(state):
                return bool(state.output.message.tool_calls)
            task=Task(dataset=[Sample(input="Consult")],solver=react(tools=[consult()],submit=False,
                model=budgeted_generation(attempt,GenerateConfig()),on_continue=keep_running),token_limit=30000)
            log=(await eval_async(task,model=get_model("stonebench-scripted/missing",script=scripted),log_dir=str(Path(tmp)/"logs"),log_model_api=False,ctl_server=False))[0]
            self.assertEqual(log.status,"success",log.error)
            self.assertEqual(attempt.ledger.phase,"finalization")
            self.assertIsNone(attempt.ledger.total_tokens)
            self.assertTrue(all(row["usage"] is None for row in attempt.ledger.calls))

    async def _run_with_failures(self, tmp, failures, waits, error=ConnectionError("peer closed connection")):
        attempt = Attempt(Budget(300000, 1000, 1000, 4000, 500), Path(tmp)/"attempt", generation_retry_waits=waits)
        requests = []
        def scripted(messages, tools, config):
            requests.append([message.text for message in messages])
            if len(requests) <= failures:
                raise error
            output = ModelOutput.from_content(model="stonebench-scripted/retry", content="done")
            output.usage = ModelUsage(input_tokens=100, output_tokens=50, total_tokens=150)
            return output
        task = Task(dataset=[Sample(input="Retry")], solver=react(submit=False,
            model=budgeted_generation(attempt, GenerateConfig(max_retries=0))), token_limit=300000)
        log = (await eval_async(task, model=get_model(f"stonebench-scripted/retry-{uuid.uuid4().hex}", script=scripted),
            log_dir=str(Path(tmp)/"logs"), log_model_api=False, ctl_server=False))[0]
        return attempt, requests, log

    async def test_lost_request_is_resent_unchanged_and_accounted(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempt, requests, log = await self._run_with_failures(tmp, 1, (0, 0))
            self.assertEqual(log.status, "success", log.error)
            self.assertEqual(len(requests), 2)
            self.assertEqual(requests[0], requests[1], "the resent request must be identical")
            self.assertEqual(len(attempt.ledger.lost), 1)
            self.assertEqual(attempt.ledger.lost[0]["failure_type"], "ConnectionError")
            self.assertEqual(attempt.ledger.known_tokens, 150)
            self.assertIsNone(attempt.ledger.total_tokens, "a possibly billed request leaves the total unknown")
            self.assertGreater(attempt.ledger.committed_tokens, 150)
            events = [json.loads(line) for line in (attempt.root/"events.jsonl").read_text().splitlines()]
            lost = [event for event in events if event["kind"] == "generation_request_lost"]
            self.assertEqual(len(lost), 1)
            self.assertTrue(lost[0]["started_utc"] < lost[0]["ended_utc"])

    async def test_resends_are_bounded_and_failure_is_still_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempt, requests, log = await self._run_with_failures(tmp, 99, (0, 0))
            self.assertEqual(log.status, "error")
            self.assertEqual(len(requests), 3)
            self.assertEqual(len(attempt.ledger.lost), 2)
            self.assertIsNone(attempt.ledger.calls[-1]["usage"])

    async def test_nontransient_and_default_never_resend(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, requests, log = await self._run_with_failures(tmp, 1, (0, 0), error=RuntimeError("not transient"))
            self.assertEqual((log.status, len(requests)), ("error", 1))
        with tempfile.TemporaryDirectory() as tmp:
            _, requests, log = await self._run_with_failures(tmp, 1, ())
            self.assertEqual((log.status, len(requests)), ("error", 1))


if __name__ == "__main__":
    unittest.main()
