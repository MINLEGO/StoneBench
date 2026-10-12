"""One-task paid authorization gate using mocked lifecycle and real archive."""
import asyncio,json,os,sys,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.campaign import launch,run_attempt
from app.campaign.plan import TASKS,plan_hash,require_authorization

class SelectionTests(unittest.TestCase):
    def test_exact_one_task_launch_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp);(repo/'app/controller/.runtime').mkdir(parents=True)
            auth,calibration=self.inputs(repo);root=repo/'output';started=[]
            class FakeProcess:
                def __init__(self,command,**kwargs):
                    started.append(kwargs['env']['STONEBENCH_CAMPAIGN_TASK'])
                    assert 'OPENROUTER_API_KEY' not in kwargs['env']
                def wait(self):
                    attempt=root/started[-1];attempt.mkdir()
                    (attempt/'status.json').write_text(json.dumps({'status':'success','total_tokens':300,'provider_validation':{'accepted':True}}))
                    runtime=repo/'app/controller/.runtime/tests-owned';(runtime/'world').mkdir(parents=True)
                    (runtime/'world/level.dat').write_bytes(b'owned mock world')
                    return 0
                def poll(self):return 0
            argv=['launch','paid','--task','2x2-volume','--authorization',str(auth),'--calibration',str(calibration),'--output',str(root)]
            with patch.object(sys,'argv',argv),patch.object(launch,'REPO',repo),patch.object(launch,'snapshot_sources',return_value={}), \
                patch.object(launch,'snapshot_source_drift',return_value=False),patch.object(launch.subprocess,'check_output',return_value='offline-head'), \
                patch.object(launch.subprocess,'Popen',FakeProcess):launch.main()
            self.assertEqual(started,['2x2-volume'])
            provenance=json.loads((root/'campaign.json').read_text())
            self.assertEqual(provenance['selected_task_ids'],['2x2-volume'])
            self.assertEqual(provenance['authorized_task_ids'],['2x2-volume'])
            self.assertEqual(provenance['plan']['tasks'],list(TASKS))
            self.assertTrue(json.loads((root/'archive-check.json').read_text())['verified'])
            with tarfile.open(root.with_suffix('.tar.xz'),'r:xz') as archive:
                self.assertIn('campaign/2x2-volume/status.json',archive.getnames())
                self.assertFalse(any('3x3-volume' in name for name in archive.getnames()))

    def inputs(self,repo):
        auth=repo/'authorization.json';auth.write_text(json.dumps({'plan_sha256':plan_hash(),'scope':'paid','authorized_by_user':True,'task_ids':['2x2-volume']}))
        calibration=repo/'calibration.json';calibration.write_text(json.dumps({'plan_sha256':plan_hash(),'mode':'calibration','calibration_validation':{'accepted':True}}))
        return auth,calibration

    def test_wrong_extra_default_or_missing_authorized_selection_refused_before_launch(self):
        for flags in ([],['--task','3x3-volume'],['--task','2x2-volume','--task','3x3-volume'],['--task','2x2-volume','--task','2x2-volume']):
            with self.subTest(flags=flags),tempfile.TemporaryDirectory() as tmp:
                repo=Path(tmp);auth,calibration=self.inputs(repo);root=repo/'output'
                argv=['launch','paid',*flags,'--authorization',str(auth),'--calibration',str(calibration),'--output',str(root)]
                with patch.object(sys,'argv',argv),patch.object(launch.subprocess,'Popen') as process,patch.object(launch,'snapshot_sources') as sources:
                    with self.assertRaises(ValueError):launch.main()
                    process.assert_not_called();sources.assert_not_called();self.assertFalse(root.exists())
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp);auth,_=self.inputs(repo);value=json.loads(auth.read_text());value.pop('task_ids');auth.write_text(json.dumps(value))
            with self.assertRaises(ValueError):require_authorization(auth,'paid',task_ids=['2x2-volume'])

    def test_direct_attempt_outside_subset_refused_before_directory_or_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp);auth,_=self.inputs(repo);root=repo/'attempt'
            require_authorization(auth,'paid',task_id='2x2-volume')
            with patch.dict(os.environ,{'STONEBENCH_CAMPAIGN_TASK':'3x3-volume','STONEBENCH_CAMPAIGN_MODE':'paid',
                'STONEBENCH_CAMPAIGN_AUTHORIZATION':str(auth),'STONEBENCH_CAMPAIGN_ATTEMPT':str(root)}), \
                patch.object(run_attempt,'load_secret') as secret:
                with self.assertRaises(ValueError):asyncio.run(run_attempt.run())
                secret.assert_not_called();self.assertFalse(root.exists())

if __name__=='__main__':unittest.main()
