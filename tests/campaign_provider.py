"""Actual Inspect/OpenRouter/OpenAI SDK transport under an offline HTTP fixture."""
import json
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
from inspect_ai.model import GenerateConfig,get_model
from app.campaign.plan import MODEL,PROVIDER
from app.campaign.run_attempt import provider_records,validate_provider
from app.harness.inspect_task import Attempt,budgeted_generation
from app.harness.budget import Budget
from inspect_ai.agent import react
import app.harness.scripted


class ProviderTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_exact_wire_route_reasoning_usage_and_secret_redaction(self):
        sentinel="SENTINEL_SECRET_NEVER_LOGGED_15"
        requests=[]
        def transport(request):
            self.assertEqual(request.url.host,"openrouter.ai")
            self.assertEqual(request.headers["authorization"],"Bearer "+sentinel)
            self.assertEqual(request.headers["X-OpenRouter-Metadata"],"enabled")
            body=json.loads(request.content);requests.append(body)
            self.assertEqual(body["provider"],PROVIDER)
            self.assertEqual(body["reasoning"],{"enabled":True})
            self.assertEqual(body["max_tokens"],65536)
            return httpx2.Response(200,json={"id":"gen-offline-15","object":"chat.completion","created":1,
                "model":"xiaomi/mimo-v2.6-flash","choices":[{"index":0,"finish_reason":"stop", "message":{"role":"assistant","content":"Offline response","reasoning":"Reasoning is retained"}}],
                "usage":{"prompt_tokens":200,"completion_tokens":100,"total_tokens":300,"cost":.000054,
                    "completion_tokens_details":{"reasoning_tokens":90}},
                "openrouter_metadata":{"endpoints":{"available":[{"provider":"Makora","selected":True}]}}})
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"OPENROUTER_API_KEY":sentinel}):
            async with httpx2.AsyncClient(transport=httpx2.MockTransport(transport)) as client:
                model=get_model(MODEL,provider=PROVIDER,max_retries=0,http_client=client,reasoning_enabled=True)
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
