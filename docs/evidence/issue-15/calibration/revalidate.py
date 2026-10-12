"""Replay two existing authorized responses offline; preserve original rejection."""
import asyncio,copy,hashlib,json,os,sys,tarfile
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd()))
import httpx
from app.campaign.plan import CALIBRATION_BUDGET,PROVIDER,plan_hash
from app.harness.inspect_task import PROMPT
from app.campaign.run_attempt import validate_provider,validate_calibration,usable_output

BASE=Path('docs/evidence/issue-15/calibration')
async def main():
    archive=BASE/'original-calibration.tar.xz'
    expected='c19c66dcb9ac0558bb6284c98bf7d6c69e40dfbfd3194a9f255a13c78572503e'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected
    with tarfile.open(archive,'r:xz') as stream:
        def data(name):return json.load(stream.extractfile('campaign/'+name))
        manifest=data('archive-manifest.json')
        for item in manifest['payloads']:
            raw=stream.extractfile(item['path']).read()
            assert len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256']
        original=data('2x2-volume/status.json');run=data('2x2-volume/harness/run.json')
        assert original['calibration_validation']['accepted'] is False
        assert original['plan_sha256']==plan_hash() and run['prompt']==PROMPT
        assert run['budget']==asdict(CALIBRATION_BUDGET)
        assert run['generation_config']['temperature']==0 and run['generation_config']['parallel_tool_calls'] is False
        assert run['generation_config']['max_retries']==0
        contexts=[json.loads(line) for line in stream.extractfile('campaign/2x2-volume/harness/events.jsonl').read().decode().splitlines()
            if json.loads(line)['kind']=='before_generation']
        logname=next(n for n in stream.getnames() if n.startswith('campaign/2x2-volume/inspect-logs/') and n.endswith('.json'))
        events=[e for e in json.load(stream.extractfile(logname))['samples'][0]['events'] if e['event']=='model']
    rows=json.loads((BASE/'response-fixtures.json').read_text())
    assert len(events)==len(rows)==len(run['calls'])==len(contexts)==2
    for event,row in zip(events,rows):
        request=event['call']['request'];response=event['call']['response']
        assert request['extra_body']['provider']==row['requested_provider']==PROVIDER
        assert request['extra_body']['reasoning']==row['requested_reasoning']=={'enabled':True}
        assert request['max_tokens']==row['requested_max_tokens']==65536
        assert request['model']==row['requested_model']=='xiaomi/mimo-v2.6-flash'
        assert response['usage']==row['raw_provider_usage'] and response['openrouter_metadata']==row['routing_metadata']
        assert response['id']==row['response_id'] and row['finish_reason']=='tool_calls' and row['usable_visible_or_tool_output']
        assert usable_output(response['choices'][0]['message'])
    fetched={r['id']:r['data'] for r in json.loads((BASE/'generation-reread.json').read_text())}
    real_client=httpx.AsyncClient
    def response(request):
        assert request.method=='GET'
        return httpx.Response(200,json={'data':fetched[request.url.params['id']]})
    with patch.dict(os.environ,{'OPENROUTER_API_KEY':'offline-sentinel'}),patch('httpx.AsyncClient',
        side_effect=lambda **kwargs:real_client(transport=httpx.MockTransport(response),**kwargs)):
        provider=await validate_provider(rows,"calibration")
    calibration=validate_calibration(provider,run['calls'],True,run['known_tokens_subtotal'],contexts,CALIBRATION_BUDGET)
    assert calibration['accepted']
    comparison=[{'context_estimate_bytes':estimate['context_estimate'],'actual_input_tokens':call['usage']['input_tokens'],
        'margin':CALIBRATION_BUDGET.margin} for estimate,call in zip(contexts,run['calls'])]
    output={'mode':'calibration','plan_sha256':plan_hash(),'original_archive_sha256':expected,
        'original_outcome':'rejected_immutable','derived_outcome':'accepted_offline_revalidation_pending_review',
        'new_inference_calls':0,'original_inference_calls':2,'archive_payloads_verified':len(manifest['payloads']),
        'provider_validation':provider,'calibration_validation':calibration,'provider_records':rows,
        'total_tokens':run['total_tokens'],'input_tokens':sum(c['usage']['input_tokens'] for c in run['calls']),
        'completion_tokens':sum(c['usage']['output_tokens'] for c in run['calls']),
        'reasoning_tokens_already_in_completion':sum(c['usage']['reasoning_tokens'] for c in run['calls']),
        'actual_provider_reported_cost_usd':sum(r['raw_provider_usage']['cost'] for r in rows),
        'context_forecast_vs_usage':comparison,'prompt_and_exact_request_config_checked':True,
        'limitations':'Two small read-only tool responses. No long reasoning stress or door-solving performance proof. FP8 tag inferred from exact request allowlist plus selected provider, not independently returned by metadata.',
        'validator_source_sha256':hashlib.sha256(Path('app/campaign/run_attempt.py').read_bytes()).hexdigest()}
    (BASE/'revalidation.json').write_text(json.dumps(output,indent=2))
    print(json.dumps({k:v for k,v in output.items() if k not in ('provider_records',)},indent=2))
asyncio.run(main())
