"""Existing real response fixtures; all metadata HTTP is mocked, no inference."""
import copy,json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from app.campaign.run_attempt import validate_provider

FIXTURES=Path(__file__).resolve().parents[1]/"docs/evidence/issue-15/calibration"

class RevalidationTests(unittest.IsolatedAsyncioTestCase):
    async def check_rows(self,rows,fetched=None):
        real_client=httpx.AsyncClient
        def response(request):
            self.assertEqual(request.method,"GET")
            if fetched is None:return httpx.Response(404)
            return httpx.Response(200,json={"data":fetched[request.url.params["id"]]})
        with patch.dict(os.environ,{"OPENROUTER_API_KEY":"offline-sentinel"}),patch("httpx.AsyncClient",
            side_effect=lambda **kwargs:real_client(transport=httpx.MockTransport(response),**kwargs)):
            return await validate_provider(rows)

    async def test_actual_direct_response_and_later_get_agree(self):
        rows=json.loads((FIXTURES/"response-fixtures.json").read_text())
        self.assertTrue((await self.check_rows(copy.deepcopy(rows)))["accepted"])
        fetched={r["id"]:r["data"] for r in json.loads((FIXTURES/"generation-reread.json").read_text())}
        self.assertTrue((await self.check_rows(rows,fetched))["accepted"])
        self.assertTrue(all(r["resolved_provider_evidence"]["provider_source"]=="generation_get" for r in rows))

    async def test_invalid_direct_binding_and_conflicting_get_rejected(self):
        base=json.loads((FIXTURES/"response-fixtures.json").read_text())
        for mutation in ("request","ambiguous","provider","model","cost","identity"):
            rows=copy.deepcopy(base)
            if mutation=="request":rows[0]["requested_provider"]["allow_fallbacks"]=True
            if mutation=="ambiguous":rows[0]["routing_metadata"]["endpoints"]["available"][1]["selected"]=True
            if mutation=="provider":rows[0]["routing_metadata"]["endpoints"]["available"][0]["provider"]="Other"
            if mutation=="model":rows[0]["routing_metadata"]["requested"]="other/model"
            if mutation=="cost":rows[0]["raw_provider_usage"]["cost"]=None
            if mutation=="identity":rows[0]["response_id"]=None
            with self.subTest(mutation=mutation):self.assertFalse((await self.check_rows(rows))["accepted"])
        for mutation,value in (("provider_name","Xiaomi"),("total_cost",.9),("native_tokens_prompt",999),("native_tokens_reasoning",999),("id","other-id")):
            rows=copy.deepcopy(base)
            fetched={r["id"]:r["data"].copy() for r in json.loads((FIXTURES/"generation-reread.json").read_text())}
            fetched[rows[0]["response_id"]][mutation]=value
            with self.subTest(disagreement=mutation):self.assertFalse((await self.check_rows(rows,fetched))["accepted"])

if __name__=="__main__":unittest.main()
