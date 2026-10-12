import asyncio, copy, json, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd()))
import httpx
from app.campaign.run_attempt import validate_provider
base={'response_id':'gen-offline','raw_provider_usage':{'prompt_tokens':200,'completion_tokens':100,'total_tokens':300},'requested_max_tokens':65536}
real_client=httpx.AsyncClient
async def check():
    async def run(row,provider='Makora',cost=.000054):
        def response(request):
            assert request.url.host=='openrouter.ai'
            assert request.headers['authorization']=='Bearer sentinel-not-real'
            return httpx.Response(200,json={'data':{'id':'gen-offline','provider_name':provider,'total_cost':cost}})
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'sentinel-not-real'}), patch('httpx.AsyncClient',side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(response),**kwargs)):
            return await validate_provider([row])
    okay=await run(copy.deepcopy(base));assert okay['accepted']
    negative=[]
    for name,provider,cost in [('wrong-provider','Other',.001),('missing-cost','Makora',None)]:
        result=await run(copy.deepcopy(base),provider,cost);assert not result['accepted'];negative.append({'name':name,**result})
    for name,usage in [('missing-usage',None),('inconsistent-total',{'prompt_tokens':200,'completion_tokens':100,'total_tokens':900}),('over-completion',{'prompt_tokens':200,'completion_tokens':70000,'total_tokens':70200})]:
        row=copy.deepcopy(base);row['raw_provider_usage']=usage
        result=await run(row);assert not result['accepted'];negative.append({'name':name,**result})
    print(json.dumps({'network':'mock_transport_only','accepted':okay,'negative':negative},indent=2))
asyncio.run(check())
