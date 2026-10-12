import asyncio, copy, json, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd()))
import httpx
from app.campaign.run_attempt import validate_provider
base={'response_id':'gen-offline','raw_provider_usage':{'prompt_tokens':200,'completion_tokens':100,'total_tokens':300},'requested_max_tokens':65536,'finish_reason':'stop','usable_visible_or_tool_output':True}
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
    usable_length=copy.deepcopy(base);usable_length['finish_reason']='length'
    usable=await run(usable_length);assert usable['accepted']
    negative=[]
    for name,provider,cost in [('wrong-provider','Other',.001),('missing-cost','Makora',None)]:
        result=await run(copy.deepcopy(base),provider,cost);assert not result['accepted'];negative.append({'name':name,**result})
    for name,usage in [('missing-usage',None),('inconsistent-total',{'prompt_tokens':200,'completion_tokens':100,'total_tokens':900}),('over-completion',{'prompt_tokens':200,'completion_tokens':70000,'total_tokens':70200})]:
        row=copy.deepcopy(base);row['raw_provider_usage']=usage
        result=await run(row);assert not result['accepted'];negative.append({'name':name,**result})
    empty_length=copy.deepcopy(base);empty_length.update(finish_reason='length',usable_visible_or_tool_output=False)
    result=await run(empty_length);assert not result['accepted'];negative.append({'name':'length-without-visible-or-tool-output',**result})
    print(json.dumps({'network':'mock_transport_only','accepted':okay,'usable_length_accepted':usable,'negative':negative},indent=2))
asyncio.run(check())
