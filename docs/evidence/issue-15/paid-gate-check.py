import json, sys, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd()))
from app.campaign.launch import main
from app.campaign.plan import plan_hash
results=[]
with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp);authorization=tmp/'fake-test-authorization.json'
    authorization.write_text(json.dumps({'plan_sha256':plan_hash(),'scope':'paid','authorized_by_user':True}))
    rejected=tmp/'rejected-calibration.json';rejected.write_text(json.dumps({'plan_sha256':plan_hash(),'mode':'calibration','calibration_validation':{'accepted':False}}))
    for label,args in [('no-authorization',[]),('no-calibration',['--authorization',str(authorization)]),('rejected-calibration',['--authorization',str(authorization),'--calibration',str(rejected)])]:
        output=tmp/label
        with patch.object(sys,'argv',['launch','paid','--output',str(output),*args]),patch('subprocess.Popen',side_effect=AssertionError('No process may start')) as process:
            try:main()
            except SystemExit as exc:assert exc.code==2
            else:raise AssertionError('Paid gate did not reject')
            assert not process.called and not output.exists()
        results.append({'case':label,'exit_code':2,'process_started':False,'output_created':False})
print(json.dumps({'authorization_fixture':'temporary_test_only_removed','results':results},indent=2))
