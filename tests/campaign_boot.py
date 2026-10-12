"""Production MCP dry startup: no model, credential loader or inference."""
import asyncio,hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inspect_ai.tool import ToolDef,mcp_server_http
from app.harness.inspect_task import payload

async def main():
    root=Path(os.environ['STONEBENCH_SERVER_ROOTS'].split(';')[0])
    url='http://127.0.0.1:'+os.environ['STONEBENCH_MCP_PORTS'].split(',')[0]+'/mcp'
    async with mcp_server_http(url=url,timeout=60) as connection:
        tools={ToolDef(tool).name:tool for tool in await connection.tools()}
        assert not any(name.startswith('__test') for name in tools)
        started=payload(await tools['start_attempt'](task_id='2x2-volume',budget_tokens=2000000))
        description=payload(await tools['describe_task']())
        snapshot=payload(await tools['verification_snapshot']())
        assert started['status']==description['status']==snapshot['status']=='ok'
        assert description['simulation_ticks']==0
        assert snapshot['checkpoint_state']['world_time']==description['preparation_ticks']
        assert snapshot['input'] is None
        assert all(not snapshot['checkpoint_state']['state'][name] for name in ('block_ticks','fluid_ticks','block_events'))
        loader=root/'.fabric/server/fabric-loader-server-0.19.5-minecraft-1.21.11.jar'
        output={'status':'passed','scope':'one production MCP dry startup, not paid task execution',
            'inference_calls':0,'server_root':str(root),'task_id':'2x2-volume','attempt_id':started['attempt_id'],
            'production_tools':len(tools),'useful_ticks':0,'preparation_ticks':description['preparation_ticks'],
            'generated_loader_sha256':hashlib.sha256(loader.read_bytes()).hexdigest(),
            'description':description,'snapshot':snapshot}
        (root/'boot-preflight.json').write_text(json.dumps(output,indent=2))
        print(json.dumps({k:v for k,v in output.items() if k not in ('description','snapshot')},indent=2))

if __name__=='__main__':asyncio.run(main())
