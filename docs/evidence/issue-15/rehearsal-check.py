import json, hashlib, sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from app.campaign.plan import TASKS, PINS, plan_hash
from app.campaign.launch import snapshot_source_drift
root=Path('app/campaign/.runtime/rehearsal-v7')
manifest=json.loads((root/'campaign.json').read_text(encoding='utf-8'))
assert not snapshot_source_drift(manifest['source_sha256'])
assert len(manifest['tasks'])==8
ids=[];roots=[];catalogues=[];results=[];context=[]
for task_id,row in zip(TASKS,manifest['tasks']):
    assert row['task_id']==task_id and row['exit_code']==0
    attempt=root/task_id
    initial=json.loads((attempt/'initial.json').read_text(encoding='utf-8'))
    reset=json.loads((attempt/'reset-check.json').read_text(encoding='utf-8'))
    status=json.loads((attempt/'status.json').read_text(encoding='utf-8'))
    run=json.loads((attempt/'harness/run.json').read_text(encoding='utf-8'))
    residue=json.loads((attempt/'residue.json').read_text(encoding='utf-8'))
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
    events=[json.loads(line) for line in (attempt/'harness/events.jsonl').read_text(encoding='utf-8').splitlines()]
    forecasts=[event for event in events if event['kind']=='before_generation']
    context.extend(event['context_estimate'] for event in forecasts)
    results.append({'task_id':task_id,'exit_code':0,'attempt_id':ids[-1],'runtime':roots[-1],
        'preparation_ticks':reset['preparation_ticks'],'initial_useful_ticks':initial['description']['simulation_ticks'],
        'result':status['result']['status'],'verdict':status['result'].get('verification',{}).get('verdict'),
        'scripted_tokens':status['total_tokens'],'calls':len(status['calls']),
        'minimum_context_byte_estimate':min(event['context_estimate'] for event in forecasts),
        'maximum_context_byte_estimate':max(event['context_estimate'] for event in forecasts)})
assert len(set(ids))==len(set(roots))==8 and len(set(catalogues))==1
check=json.loads((root/'archive-check.json').read_text(encoding='utf-8'))
assert check['verified'] and hashlib.sha256(root.with_suffix('.tar.xz').read_bytes()).hexdigest()==check['sha256']
output={'status':'passed','paid_inference_calls':0,'scope':'real Minecraft/Inspect/MCP infrastructure with scripted incomplete constructions, not provider calibration or door solving',
    'plan_sha256':plan_hash(),'source_bytes_match_delivered':True,'independent_attempts':8,'production_catalogue_identical':True,
    'context_estimate_minimum':min(context),'context_estimate_maximum':max(context),'archive':check,'tasks':results}
Path('docs/evidence/issue-15/rehearsal-validation.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','independent_attempts':8,'archive':check,'context_bytes':[min(context),max(context)]},indent=2))
