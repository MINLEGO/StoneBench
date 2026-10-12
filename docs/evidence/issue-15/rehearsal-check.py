import json, hashlib, sys, tarfile
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from app.campaign.plan import TASKS, plan_hash
archive_path=Path('docs/evidence/issue-15/rehearsal.tar.xz')
stream=tarfile.open(archive_path,'r:xz')
root=Path('campaign')
def read_text(path):
    return stream.extractfile(path.as_posix()).read().decode('utf-8')
manifest=json.loads(read_text(root/'campaign.json'))
check=json.loads(Path('docs/evidence/issue-15/archive-check.json').read_text(encoding='utf-8'))
assert check['verified'] and hashlib.sha256(archive_path.read_bytes()).hexdigest()==check['sha256']
payload_manifest=json.loads(read_text(root/'archive-manifest.json'))
for item in payload_manifest['payloads']:
    data=stream.extractfile(item['path']).read()
    assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']
source_delta=[]
for name,expected in manifest['source_sha256'].items():
    archived=stream.extractfile('campaign/source/'+name).read()
    assert hashlib.sha256(archived).hexdigest()==expected
    current=Path('app/controller/build/libs/stonebench-controller-0.1.0.jar') if name=='controller.jar' else Path(name)
    actual=hashlib.sha256(current.read_bytes()).hexdigest() if current.exists() else None
    if actual!=expected:source_delta.append({'path':name,'archived_sha256':expected,'current_sha256':actual})
assert {item['path'] for item in source_delta} == {'app/campaign/launch.py','app/campaign/plan.py',
    'app/campaign/run_attempt.py','docs/campaign.md','tests/campaign.py'}
current_added_sources={'tests/campaign_completion.py':hashlib.sha256(Path('tests/campaign_completion.py').read_bytes()).hexdigest()}

assert len(manifest['tasks'])==8
ids=[];roots=[];catalogues=[];results=[];context=[]
for task_id,row in zip(TASKS,manifest['tasks']):
    assert row['task_id']==task_id and row['exit_code']==0
    attempt=root/task_id
    initial=json.loads(read_text(attempt/'initial.json'))
    reset=json.loads(read_text(attempt/'reset-check.json'))
    status=json.loads(read_text(attempt/'status.json'))
    run=json.loads(read_text(attempt/'harness/run.json'))
    residue=json.loads(read_text(attempt/'residue.json'))
    task=initial['description']['task'];size=int(task_id[0])
    assert task['width']==task['height']==size and len(task['expected_frame'])==size*size
    assert task['passage']=={'origin':{'x':1024,'y':80,'z':1024},'vertical_axis':'+Y','horizontal_axis':'+X','normal':'+Z'}
    assert reset['checked'] and reset['world_time']==reset['preparation_ticks']
    assert not initial['checkpoints']['checkpoints'] and initial['snapshot']['input'] is None
    raw=initial['snapshot']['checkpoint_state']['state']
    assert all(not raw[key] for key in ('block_ticks','fluid_ticks','block_events'))
    assert all(block['block']=='minecraft:air' and not block['inventory'] for block in raw['blocks'].values())
    assert any(block['inventory']==[{'slot':0,'item':'minecraft:diamond','count':7}] for block in residue['checkpoint_state']['state']['blocks'].values())
    assert residue['input'] is not None and residue['checkpoint_state']['world_time']>reset['world_time']
    assert run['model']=='stonebench-scripted/campaign-rehearsal'
    assert not any(tool['name'].startswith('__test') for tool in initial['catalogue'])
    assert status['status']=='success'
    if task_id=='5x5-speed':
        assert status['selected_checkpoint_id'] is None and status['result']['status']=='no_submission'
    else:
        assert status['selected_checkpoint_id']==status['result']['checkpoint_id']==status['result']['verification']['checkpoint_id']
        assert status['result']['verification']['conforms_to_alpha'] is False
        assert status['result']['verification']['measurements']['dynamic_volume']['value'] is None
    ids.append(initial['start']['attempt_id']);roots.append(row['runtime']);catalogues.append(initial['catalogue_sha256'])
    events=[json.loads(line) for line in read_text(attempt/'harness/events.jsonl').splitlines()]
    forecasts=[event for event in events if event['kind']=='before_generation']
    context.extend(event['context_estimate'] for event in forecasts)
    results.append({'task_id':task_id,'exit_code':0,'attempt_id':ids[-1],'runtime':roots[-1],
        'preparation_ticks':reset['preparation_ticks'],'initial_useful_ticks':initial['description']['simulation_ticks'],
        'result':status['result']['status'],'verdict':status['result'].get('verification',{}).get('verdict'),
        'scripted_tokens':status['total_tokens'],'calls':len(status['calls']),
        'minimum_context_byte_estimate':min(event['context_estimate'] for event in forecasts),
        'maximum_context_byte_estimate':max(event['context_estimate'] for event in forecasts)})
assert len(set(ids))==len(set(roots))==8 and len(set(catalogues))==1
output={'status':'passed','paid_inference_calls':0,'scope':'real Minecraft/Inspect/MCP infrastructure with scripted incomplete constructions, not provider calibration or door solving',
    'plan_sha256':manifest['plan_sha256'],'current_plan_sha256':plan_hash(),'archived_source_bytes_match_manifest':True,'source_bytes_match_current':not source_delta,'source_delta':source_delta,'current_added_sources':current_added_sources,'delta_validation':'numerical correction: tests/campaign.py; provider guards: offline provider-validation-check.py and tests/campaign_completion.py; no new real Minecraft rehearsal','independent_attempts':8,'production_catalogue_identical':True,
    'context_estimate_minimum':min(context),'context_estimate_maximum':max(context),'archive':check,'tasks':results}
Path('docs/evidence/issue-15/rehearsal-validation.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
stream.close()
print(json.dumps({'status':'passed','independent_attempts':8,'archive':check,'context_bytes':[min(context),max(context)]},indent=2))
