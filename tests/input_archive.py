"""Export input evidence and verify referenced artifacts one sample at a time."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
import zipfile


def load_rows(archive, name):
    with archive.open(name) as stream:
        return [json.loads(line) for line in stream]


def data_name(base, ref):
    return f'{base}/by-sha256/{ref["sha256"]}.jsonl'


def verify(path):
    artifacts = entries = traces = samples = 0
    with zipfile.ZipFile(path) as archive:
        refs = {}
        verified_data = {}
        for name in archive.namelist():
            if not name.endswith('.jsonl.meta'):
                continue
            ref = json.loads(archive.read(name))
            identity = ref['artifact_id']
            assert str(uuid.UUID(identity)) == identity
            assert Path(name).name == identity + '.jsonl.meta'
            base = name.rsplit('/', 1)[0]
            key = (base, ref['sha256'])
            if key not in verified_data:
                digest, count, size = hashlib.sha256(), 0, 0
                with archive.open(data_name(base, ref)) as stream:
                    for line in stream:
                        digest.update(line)
                        size += len(line)
                        json.loads(line)
                        count += 1
                verified_data[key] = (digest.hexdigest(), size, count)
            assert verified_data[key] == (ref['sha256'], ref['bytes'], ref['count']) and ref['complete']
            count = ref['count']
            refs[(base, identity)] = ref
            artifacts += 1
            entries += count
        for (base, identity), ref in refs.items():
            if ref['kind'] != 'trace':
                continue
            traces += 1
            rows = load_rows(archive, data_name(base, ref))
            assert len(rows) == ref['expected_ticks']
            for index, tick in enumerate(rows, 1):
                assert tick['complete'] and tick['phase'] == 'end_tick'
                assert tick['tick_index'] == index
                assert tick['world_time'] == ref['start_world_time'] + index
                assert tick['simulation_index'] == ref['start_simulation_index'] + index
                decoded = {}
                pointers = {'blocks': tick['state']['blocks'], 'adapter': tick['adapter_blocks'], 'construction': tick['construction_blocks'], 'events': tick['events']}
                for key, pointer in pointers.items():
                    assert pointer == refs[(base, pointer['artifact_id'])]
                    decoded[key] = load_rows(archive, data_name(base, pointer))
                point = lambda row: (row['x'], row['y'], row['z'])
                blocks = {point(row): row for row in decoded['blocks']}
                adapter = {point(row): row for row in decoded['adapter']}
                construction = {point(row): row for row in decoded['construction']}
                assert len(blocks) == len(decoded['blocks']) and len(adapter) == len(decoded['adapter']) and len(construction) == len(decoded['construction'])
                assert not adapter.keys() & construction.keys()
                assert blocks == construction | adapter
                assert [e['order'] for e in decoded['events']] == list(range(len(decoded['events'])))
                assert all(e['tick_index'] == index for e in decoded['events'])
                samples += 1
    summary = json.loads(archive_summary(path))
    by_id = {identity: ref for (_, identity), ref in refs.items()}
    assert len(by_id) == len(refs)
    reported = [report for cycle in summary['cycles'] for report in cycle['reports']]
    reported += [face[key] for face in summary['lateral_faces'] for key in ('pressed', 'release')]
    assert len(reported) == traces
    assert sum(report['trace']['expected_ticks'] for report in reported) == samples
    for report in reported:
        assert report['trace'] == by_id[report['trace']['artifact_id']]
    for cycle in summary['cycles']:
        source = [e for e in cycle['events'] if e['kind'] == 'input_device_change']
        signal = [e for e in cycle['events'] if e['kind'] == 'input_signal_change']
        assert source[0]['phase'] == 'before_world_time'
        assert source[1]['phase'] == ('before_world_time' if cycle['device'] == 'minecraft:lever' else 'scheduled_block_ticks')
        assert signal[0]['phase'] == ('before_world_time' if cycle['mode'] == 'direct' else 'scheduled_block_ticks')
        assert signal[1]['phase'] == ('before_world_time' if cycle['mode'] == 'direct' and cycle['device'] == 'minecraft:lever' else 'scheduled_block_ticks')
        assert all(e['phase'] == 'scheduled_block_ticks' for e in cycle['component_events'])
    return {'artifacts': artifacts, 'artifact_entries': entries, 'traces': traces, 'samples': samples, 'cycle_phases_verified': len(summary['cycles']), 'unique_artifact_contents': len(verified_data)}


def archive_summary(path):
    with zipfile.ZipFile(path) as archive:
        return archive.read('input-summary.json')


def export():
    repo = Path(__file__).resolve().parent.parent
    log = repo / '.runtime/input-final-test.log'
    text = log.read_text(encoding='utf-8-sig')
    roots = re.findall(r'Disposable server data and logs: (.+)', text)
    # PowerShell Write-Host is not captured by Tee-Object; accept an explicit run root.
    supplied = __import__('os').environ.get('STONEBENCH_INPUT_EVIDENCE_ROOT')
    assert (roots and 'Integration suite finished' in text) or supplied, 'Supply the completed test-server root'
    assert 'OK' in text and 'Ran 1 test' in text
    source = Path(supplied or roots[-1].strip()).resolve()
    assert source.is_relative_to(repo / 'app/controller/.runtime')
    summary_path = repo / '.runtime/input-summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    assert summary['success'] is True
    assert len(summary['cycles']) == 72 + 8 * (len(summary['catalog_wood_buttons']) - 1)
    target = repo / 'docs/evidence/issue-8'
    target.mkdir(parents=True, exist_ok=True)
    output = target / 'input-evidence.zip'
    assert not output.exists(), 'Evidence archives are immutable; select a new target for a new run'
    partial = output.with_suffix('.zip.partial')
    with zipfile.ZipFile(partial, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for index in (1, 2):
            server = source / f'server-{index}'
            assert 'All dimensions are saved' in (server / 'logs/stdout.log').read_text(encoding='utf-8'), 'Both servers must stop gracefully'
            stored = set()
            for path in sorted((server / 'stonebench').rglob('*')):
                if not path.is_file():
                    continue
                relative = path.relative_to(source).as_posix()
                if path.parent.name == 'artifacts' and path.name.endswith('.jsonl'):
                    continue
                archive.write(path, relative)
                if path.name.endswith('.jsonl.meta'):
                    ref = json.loads(path.read_text(encoding='utf-8'))
                    if ref['sha256'] not in stored:
                        base = relative.rsplit('/', 1)[0]
                        archive.write(path.with_suffix(''), data_name(base, ref))
                        stored.add(ref['sha256'])
            for name in ('stdout.log', 'stderr.log'):
                path = server / 'logs' / name
                archive.write(path, path.relative_to(source).as_posix())
            archive.write(server / 'mods/stonebench-controller.jar', f'server-{index}/controller.jar')
        archive.write(summary_path, 'input-summary.json')
        archive.write(log, 'test.log')
        archive.write(repo / '.runtime/input-final-build.log', 'build.log')
    verified = verify(partial)
    partial.replace(output)
    jar = source / 'server-1/mods/stonebench-controller.jar'
    result = {'status': 'verified', 'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(), 'archive': output.name, 'archive_sha256': hashlib.file_digest(output.open('rb'), 'sha256').hexdigest(), 'archive_bytes': output.stat().st_size, 'artifact_storage': 'Exact metadata by UUID; raw JSONL content by SHA-256, without repeated identical bytes', 'jar_sha256': hashlib.file_digest(jar.open('rb'), 'sha256').hexdigest(), 'matrix_cycles': 72, 'additional_wood_cycles': len(summary['cycles']) - 72, 'wood_buttons': summary['catalog_wood_buttons'], 'negative_controls': len(summary['negative_controls']), 'lateral_faces': len(summary['lateral_faces']), 'limits': ['Dedicated-server interaction, no player network path', 'Four fixed circuit fixtures, no complete regular DOOR certification', 'Observed typed state and events; no universal JVM memory claim']}
    result.update(verified)
    (target / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    print(json.dumps(verify(Path(sys.argv[1])), indent=2)) if len(sys.argv) == 2 else export()
