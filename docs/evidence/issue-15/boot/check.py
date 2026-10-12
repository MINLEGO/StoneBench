"""Offline verification of published boot archive and explicit startup outcomes."""
import hashlib,json,tarfile
from pathlib import Path
base=Path('docs/evidence/issue-15/boot')
check=json.loads((base/'archive-check.json').read_text())
archive=base/'boot-preflight.tar.xz'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==check['sha256']
with tarfile.open(archive,'r:xz') as stream:
    manifest=json.load(stream.extractfile('campaign/archive-manifest.json'))
    for row in manifest['payloads']:
        payload=stream.extractfile(row['path']).read()
        assert len(payload)==row['bytes'] and hashlib.sha256(payload).hexdigest()==row['sha256']
    proof=json.load(stream.extractfile('campaign/boot-proof.json'))
    assert proof['inference_calls']==0 and proof['actual_preflight']['status']=='passed'
    assert proof['actual_preflight']['useful_ticks']==0 and proof['actual_preflight']['production_tools']==22
    assert proof['actual_preflight']['preparation_ticks']==22
    assert proof['installer_metadata_fetch_messages'] is False and proof['tls_trust_changed'] is False
    for row in proof['copied_cache']:
        assert row['source_sha256']==row['copied_sha256'] and row['payload_matches_prior_real_calibration']
    for name in ('scripts/test-server.ps1','tests/campaign_boot.py'):
        archived=stream.extractfile('campaign/source/'+name).read()
        assert hashlib.sha256(archived).hexdigest()==proof['source_sha256'][name]
        assert Path(name).read_bytes()==archived
print(json.dumps({'status':'passed','archive_sha256':check['sha256'],'payloads_verified':len(manifest['payloads']),
    'actual_mcp_preflight':True,'inference_calls':0,'tls_trust_changed':False},indent=2))
