"""Offline launcher rejection paths; no Java, Minecraft, HTTP or credentials."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.campaign import launch
from app.campaign.plan import plan_hash


class CompletionGateTests(unittest.TestCase):
    def test_rejected_paid_completion_stops_before_second_task_and_archives(self):
        self.check_rejected("paid",{"accepted":False,"gaps":["reasoning_exhausted_completion_without_usable_response"]})

    def test_rejected_calibration_is_nonzero_even_if_lifecycle_exits_zero(self):
        self.check_rejected("calibration",{"accepted":False,"gaps":["input_context_forecast_not_covered_by_margin"]})

    def check_rejected(self,mode,validation):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp);(repo/"app/controller/.runtime").mkdir(parents=True)
            root=repo/"output"
            calibration=repo/"accepted.json"
            calibration.write_text(json.dumps({"plan_sha256":plan_hash(),"mode":"calibration","calibration_validation":{"accepted":True}}))
            launches=[]
            class FakeProcess:
                def __init__(self,command,**kwargs):
                    launches.append(kwargs["env"]["STONEBENCH_CAMPAIGN_TASK"])
                def wait(self,**kwargs):
                    attempt=root/launches[-1];attempt.mkdir()
                    status={"status":"success","total_tokens":300,"provider_validation":validation}
                    if mode=="calibration":status["calibration_validation"]=validation
                    (attempt/"status.json").write_text(json.dumps(status))
                    (repo/"app/controller/.runtime/tests-owned").mkdir()
                    return 0
                def poll(self):return 0
            argv=["campaign",mode,"--authorization",str(repo/"authorization.json"),"--output",str(root)]
            if mode=="paid":argv.extend(["--calibration",str(calibration)])
            with patch.object(sys,"argv",argv),patch.object(launch,"REPO",repo), \
                patch.object(launch,"require_authorization"),patch.object(launch,"snapshot_sources",return_value={}), \
                patch.object(launch.subprocess,"check_output",return_value="offline-head"), \
                patch.object(launch.subprocess,"Popen",FakeProcess),patch.object(launch,"archive",return_value=repo/"archive.tar.xz") as archived:
                with self.assertRaises(SystemExit) as raised:launch.main()
            self.assertNotEqual(raised.exception.code,0)
            self.assertEqual(launches,["2x2-volume"])
            archived.assert_called_once()
            retained=json.loads((root/"campaign.json").read_text())
            self.assertEqual(retained["campaign_stop"],"provider_usage_or_validation_rejected")
            self.assertEqual(retained["tasks"][0]["status"]["provider_validation"],validation)


if __name__=="__main__":unittest.main()
