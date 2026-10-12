"""Offline integrity and accounting check; no provider or secret-loader imports."""
import hashlib
import json
import re
import tarfile
from decimal import Decimal
from pathlib import Path

base = Path(__file__).resolve().parent
archive = base / 'attempt.tar.xz'
expected = '733268907abadff17f90f512b6287c1ad942ae0b5210e290c9eb99948e3e369f'
assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
review = json.loads((base / 'review.json').read_text())
with tarfile.open(archive, 'r:xz') as stream:
    manifest = json.load(stream.extractfile('campaign/archive-manifest.json'))
    assert len(manifest['payloads']) == 173
    for row in manifest['payloads']:
        payload = stream.extractfile(row['path']).read()
        assert len(payload) == row['bytes']
        assert hashlib.sha256(payload).hexdigest() == row['sha256']
        assert Path(row['path']).name != 'openrouter.env'
        assert not re.search(rb'sk-or-v1-[A-Za-z0-9]{32,}', payload), 'credential-shaped value found'
        if not row['path'].startswith('campaign/source/'):
            assert not re.search(rb'(?:sentinel-key|stonebench-secret-sentinel|fake-openrouter-key)', payload, re.I)
    campaign = json.load(stream.extractfile('campaign/campaign.json'))
    status = json.load(stream.extractfile('campaign/2x2-volume/status.json'))
    assert campaign['git_head'] == '8244d45a8bd46c38c4dd6e0316c4320143c265da'
    assert campaign['plan_sha256'] == '8758eb0f4d8b2a14c321bf161685103d4e0e88b135fada97b04abe293da2fc21'
    assert campaign['selected_task_ids'] == campaign['authorized_task_ids'] == ['2x2-volume']
    records = status['provider_records']
    assert len(records) == len(status['calls']) == 5
    completed = records[:4]
    assert [r['response_id'] for r in completed] == review['response_ids']
    assert all(r['finish_reason'] == 'tool_calls' for r in completed)
    assert all(r['resolved_provider_evidence']['provider'] == 'Makora' for r in completed)
    assert records[4]['response_id'] is None and records[4]['raw_provider_usage'] is None
    assert status['calls'][4]['usage'] is None
    assert abs(status['calls'][4]['wall_seconds'] - 204.187) < .001
    raw = [r['raw_provider_usage'] for r in completed]
    sums = {key: sum(r[key] for r in raw) for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    assert sums == {'prompt_tokens': 73551, 'completion_tokens': 11842, 'total_tokens': 85393}
    assert sum(r['completion_tokens_details']['reasoning_tokens'] for r in raw) == 10901
    cost = sum(Decimal(str(r['cost'])) for r in raw)
    assert cost == Decimal('0.011451982') == Decimal(str(review['known_cost_usd']))
    assert status['known_tokens_subtotal'] == review['known_tokens'] == 85393
    assert status['total_tokens'] is review['total_tokens'] is review['total_cost_usd'] is None
    assert status['result'] == review['result'] == {'checkpoint_id': None, 'inspect_status': 'error', 'status': 'no_submission'}
    assert 'RetryError' in status['error']['message']
    assert 'APIConnectionError' in status['error']['traceback']
    assert 'APIConnectionError' in review['error'] and 'RetryError' in review['error']
    tools = [json.load(stream.extractfile(f'campaign/2x2-volume/harness/tool-{i:06d}.json')) for i in range(1, 6)]
    assert [t['operation'] for t in tools] == ['describe_task', 'describe_rules', 'describe_blocks', 'read_region', 'check_geometry']
    assert all(t['mutated'] is False for t in tools)
    assert review['remaining_seven_tasks_authorized'] is False

proof = {'status': 'passed', 'archive_sha256': expected, 'payloads_verified': 173,
         'completed_responses': 4, 'failed_calls_without_usage': 1,
         'known_raw_tokens': sums, 'known_reasoning_tokens': 10901, 'known_cost_usd': str(cost),
         'total_tokens': None, 'total_cost_usd': None, 'result': status['result'],
         'completed_tool_mutations': 0, 'credential_pattern_absent': True,
         'execution_sentinels_absent': True, 'secret_read': False, 'network_calls': 0,
         'remaining_seven_tasks_authorized': False}
(base / 'verification.json').write_text(json.dumps(proof, indent=2) + '\n')
print(json.dumps(proof, indent=2))
