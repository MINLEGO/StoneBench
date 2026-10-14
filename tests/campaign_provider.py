"""Actual Inspect/OpenRouter/OpenAI SDK transport under an offline HTTP fixture."""
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx2
from inspect_ai import Task,eval_async
from inspect_ai.dataset import Sample
from inspect_ai.solver import generate
from inspect_ai.model import ChatCompletionChoice,ChatMessageAssistant,GenerateConfig,ModelOutput,ModelUsage,get_model
from inspect_ai.tool import ToolCall,tool
from app.campaign.plan import MODEL,PROVIDER,PROVIDER_NAME,REASONING_REQUEST

SLUG=MODEL.removeprefix("openrouter/")
from app.campaign.run_attempt import provider_records,validate_provider,usable_output
from app.harness.inspect_task import Attempt,budgeted_generation
from app.harness.budget import Budget
from inspect_ai.agent import react
import app.harness.scripted


@tool
def probe():
    async def execute():
        """Return a large observation."""
        return "x"*12000
    return execute


def probing_script(calls):
    # Asks for the probe once (1000 reported tokens); loses the second request before any response, then answers its resend.
    def script(messages,tools,config):
        calls.append(len(messages))
        if len(calls)==1:
            return ModelOutput(model="stonebench-scripted/probe",usage=ModelUsage(input_tokens=600,output_tokens=400,total_tokens=1000),
                choices=[ChatCompletionChoice(message=ChatMessageAssistant(content="",tool_calls=[ToolCall(id="probe-1",function="probe",arguments={})]),stop_reason="tool_calls")])
        if len(calls)==2:
            raise ConnectionError("connection lost before response")
        return ModelOutput(model="stonebench-scripted/probe",usage=ModelUsage(input_tokens=700,output_tokens=40,total_tokens=740),
            choices=[ChatCompletionChoice(message=ChatMessageAssistant(content="done"),stop_reason="stop")])
    return script


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_length_whitespace_parts_and_valid_tool_offline_transport(self):
        import httpx
        real_metadata_client=httpx.AsyncClient
        cases=[("whitespace",{"content":"   \n\t"},False),
               ("empty-text-parts",{"content":[{"type":"text","text":""},{"type":"text","text":"   "}]},False),
               ("valid-tool",{"content":None,"tool_calls":[{"id":"call-offline","type":"function",
                    "function":{"name":"inspect_checkpoint","arguments":"{}"}}]},True)]
        for name,message,accepted in cases:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"OPENROUTER_API_KEY":"sentinel-offline-only"}):
                def completion(request):
                    return httpx2.Response(200,json={"id":"gen-offline-length","object":"chat.completion","created":1,
                        "model":SLUG,"choices":[{"index":0,"finish_reason":"length",
                            "message":{"role":"assistant",**message}}],
                        "usage":{"prompt_tokens":200,"completion_tokens":100,"total_tokens":300,"cost":.000054}})
                async with httpx2.AsyncClient(transport=httpx2.MockTransport(completion)) as client:
                    logs=await eval_async(Task(dataset=[Sample(input="Offline length fixture")],solver=generate(tool_calls="none")),
                        model=get_model(MODEL,memoize=False,provider=PROVIDER,max_retries=0,http_client=client),
                        log_dir=tmp,log_format="json",log_model_api=True,ctl_server=False,retry_on_error=0,
                        max_tokens=65536,max_retries=0)
                if name=="empty-text-parts":
                    # Pinned Inspect rejects list content before creating a ModelEvent.
                    # Exercise the raw-content normalization separately too.
                    self.assertEqual(logs[0].status,"error")
                    self.assertIn("expected string or bytes-like object",logs[0].error.message)
                    self.assertFalse(usable_output(message))
                    rows=[{"response_id":"gen-offline-length","raw_provider_usage":{"prompt_tokens":200,
                        "completion_tokens":100,"total_tokens":300},"requested_max_tokens":65536,
                        "requested_model":SLUG,"requested_provider":PROVIDER,"requested_reasoning":REASONING_REQUEST,
                        "finish_reason":"length","usable_visible_or_tool_output":usable_output(message)}]
                else:
                    self.assertEqual(logs[0].status,"success",logs[0].error)
                    rows=provider_records(logs[0])
                self.assertEqual(rows[0]["usable_visible_or_tool_output"],accepted)
                def metadata(request):
                    return httpx.Response(200,json={"data":{"id":"gen-offline-length","provider_name":PROVIDER_NAME,"total_cost":.000054}})
                with patch("httpx.AsyncClient",side_effect=lambda **kwargs:real_metadata_client(transport=httpx.MockTransport(metadata),**kwargs)):
                    validation=await validate_provider(rows)
                self.assertEqual(validation["accepted"],accepted)
                if not accepted:self.assertEqual(validation["gaps"],["reasoning_exhausted_completion_without_usable_response"])

    async def test_context_guard_prevents_provider_request(self):
        called=False
        def forbidden(*args):
            nonlocal called
            called=True
            raise AssertionError("Provider request must not be sent")
        with tempfile.TemporaryDirectory() as tmp:
            attempt=Attempt(Budget(30000,1000,1000,4000,500),Path(tmp)/"attempt",max_context_bytes=1)
            task=Task(dataset=[Sample(input="Large context")],solver=react(submit=False,
                model=budgeted_generation(attempt,GenerateConfig())))
            logs=await eval_async(task,model=get_model("stonebench-scripted/guard",script=forbidden),
                log_dir=str(Path(tmp)/"logs"),log_model_api=False,ctl_server=False)
            self.assertEqual(logs[0].status,"error")
            self.assertFalse(called)
            self.assertEqual(attempt.ledger.calls,[])
            self.assertIn("context_guard_stop",(attempt.root/"events.jsonl").read_text())

    async def test_token_window_stops_before_the_provider_and_reports_it(self):
        called=False
        def forbidden(*args):
            nonlocal called
            called=True
            raise AssertionError("Provider request must not be sent")
        with tempfile.TemporaryDirectory() as tmp:
            # The first request already needs more than 1,000 estimated tokens: construction cannot leave room for the final one.
            attempt=Attempt(Budget(30000,1000,1000,4000,500,context_window_tokens=1000),Path(tmp)/"attempt")
            task=Task(dataset=[Sample(input="Small window")],solver=react(submit=False,
                model=budgeted_generation(attempt,GenerateConfig())))
            logs=await eval_async(task,model=get_model("stonebench-scripted/window",script=forbidden,memoize=False),
                log_dir=str(Path(tmp)/"logs"),log_model_api=False,ctl_server=False)
            self.assertEqual(logs[0].status,"error")
            self.assertFalse(called)
            self.assertEqual(attempt.ledger.calls,[])
            events=[json.loads(line) for line in (attempt.root/"events.jsonl").read_text(encoding="utf-8").splitlines()]
            stop=[event for event in events if event["kind"]=="context_window_stop"]
            self.assertEqual(len(stop),1)
            self.assertGreater(stop[0]["context_estimate"]+stop[0]["completion_bound"],1000)

    async def test_lost_request_bound_uses_the_forecast_not_raw_bytes(self):
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            attempt=Attempt(Budget(10000000,1000,1000,4000,500),Path(tmp)/"attempt",generation_retry_waits=(0,))
            task=Task(dataset=[Sample(input="Probe twice")],solver=react(tools=[probe()],submit=False,
                model=budgeted_generation(attempt,GenerateConfig(max_retries=0))))
            logs=await eval_async(task,model=get_model("stonebench-scripted/probe",script=probing_script(calls),memoize=False),
                log_dir=str(Path(tmp)/"logs"),log_model_api=False,ctl_server=False,retry_on_error=0)
            self.assertEqual(logs[0].status,"success",logs[0].error)
            events=[json.loads(line) for line in (attempt.root/"events.jsonl").read_text(encoding="utf-8").splitlines()]
            before=[event for event in events if event["kind"]=="before_generation"]
            lost=[event for event in events if event["kind"]=="generation_request_lost"]
            self.assertEqual(len(before),2)
            self.assertEqual(before[0]["context_estimate"],before[0]["context_bytes"],"first call has no reported total")
            forecast=1000+math.ceil((before[1]["context_bytes"]-before[0]["context_bytes"])/2)
            self.assertEqual(before[1]["context_estimate"],forecast)
            self.assertEqual([event["upper_bound_tokens"] for event in lost],[forecast+1000])

    async def test_hard_guard_counts_raw_bytes_not_the_forecast(self):
        calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            # Forecast for the second request is ~7 KB and its raw context ~15 KB: only raw bytes may stop it.
            attempt=Attempt(Budget(10000000,1000,1000,4000,500),Path(tmp)/"attempt",max_context_bytes=10000)
            task=Task(dataset=[Sample(input="Probe twice")],solver=react(tools=[probe()],submit=False,
                model=budgeted_generation(attempt,GenerateConfig(max_retries=0))))
            logs=await eval_async(task,model=get_model("stonebench-scripted/probe",script=probing_script(calls),memoize=False),
                log_dir=str(Path(tmp)/"logs"),log_model_api=False,ctl_server=False,retry_on_error=0)
            self.assertEqual(logs[0].status,"error")
            self.assertEqual(len(calls),1,"the second request must not be sent")
            events=[json.loads(line) for line in (attempt.root/"events.jsonl").read_text(encoding="utf-8").splitlines()]
            guard=[event for event in events if event["kind"]=="context_guard_stop"]
            self.assertEqual(len(guard),1)
            self.assertGreater(guard[0]["context_bytes"],10000)

    async def test_exact_wire_route_reasoning_usage_and_secret_redaction(self):
        sentinel="SENTINEL_SECRET_NEVER_LOGGED_15"
        requests=[]
        def transport(request):
            self.assertEqual(request.url.host,"openrouter.ai")
            self.assertEqual(request.headers["authorization"],"Bearer "+sentinel)
            self.assertEqual(request.headers["X-OpenRouter-Metadata"],"enabled")
            body=json.loads(request.content);requests.append(body)
            self.assertEqual(body["provider"],PROVIDER)
            self.assertNotIn("reasoning",body)
            self.assertEqual(body.get("max_tokens",body.get("max_completion_tokens")),65536)
            return httpx2.Response(200,json={"id":"gen-offline-15","object":"chat.completion","created":1,
                "model":SLUG,"choices":[{"index":0,"finish_reason":"stop", "message":{"role":"assistant","content":"Offline response","reasoning":"Reasoning is retained"}}],
                "usage":{"prompt_tokens":200,"completion_tokens":100,"total_tokens":300,"cost":.000054,
                    "completion_tokens_details":{"reasoning_tokens":90}},
                "openrouter_metadata":{"endpoints":{"available":[{"provider":PROVIDER_NAME,"selected":True}]}}})
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"OPENROUTER_API_KEY":sentinel}):
            async with httpx2.AsyncClient(transport=httpx2.MockTransport(transport)) as client:
                model=get_model(MODEL,memoize=False,provider=PROVIDER,max_retries=0,http_client=client)
                config=GenerateConfig(max_tokens=65536,max_retries=0,extra_headers={"X-OpenRouter-Metadata":"enabled"})
                task=Task(dataset=[Sample(input="Return one response")],solver=generate())
                logs=await eval_async(task,model=model,log_dir=tmp,log_format="json",log_model_api=True,
                    ctl_server=False,retry_on_error=0,**config.model_dump(exclude_none=True))
                self.assertEqual(logs[0].status,"success",logs[0].error)
                usage=next(iter(logs[0].stats.model_usage.values()))
                self.assertEqual(usage.total_tokens,300)
                self.assertEqual(usage.output_tokens,100)
                self.assertEqual(usage.reasoning_tokens,90)
                rows=provider_records(logs[0])
                self.assertEqual(rows[0]["provider_reported_cost"],.000054)
                self.assertEqual(rows[0]["response_id"],"gen-offline-15")
                self.assertEqual(len(requests),1)
                for path in Path(tmp).rglob("*"):
                    if path.is_file():self.assertNotIn(sentinel.encode(),path.read_bytes())


if __name__=="__main__":unittest.main()
