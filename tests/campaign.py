"""Campaign boundary tests; no network inference or real secret access."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.campaign.plan import BUDGET, MODEL, PROVIDER, TASKS, load_secret, plan, plan_hash, require_authorization
from app.campaign.launch import archive
from app.campaign.run_attempt import assert_clean, Rehearsal
from app.harness.inspect_task import stonebench_task
from inspect_ai.model import GenerateConfig


class CampaignTests(unittest.TestCase):
    def test_eight_separate_tasks_budget_and_cost(self):
        self.assertEqual(len(set(TASKS)),8)
        self.assertEqual(TASKS,("2x2-volume","2x2-speed","3x3-volume","3x3-speed","4x4-volume","4x4-speed","5x5-volume","5x5-speed"))
        self.assertEqual(BUDGET.final_completion,65536)
        self.assertEqual(BUDGET.reserve(12345),110649)
        forecast=plan()["forecast"]
        self.assertAlmostEqual(forecast["worst_split_campaign_usd"],BUDGET.total*8*.5/1000000)
        self.assertAlmostEqual(forecast["conditional_calibration_plus_excess_usd"],
            (400000+1114112)*.5/1000000)
        self.assertAlmostEqual(forecast["conditional_campaign_plus_excess_and_calibration_usd"],
            8.0+9*1114112*.5/1000000+.2)
        self.assertTrue(all(value>0 for value in asdict(BUDGET).values()))

    def test_exact_endpoint_allowlist(self):
        self.assertEqual(MODEL,"openrouter/openai/gpt-6-luna")
        self.assertEqual(PROVIDER["order"],["openai"])
        self.assertEqual(PROVIDER["only"],["openai"])
        self.assertIs(PROVIDER["allow_fallbacks"],False)
        self.assertEqual(PROVIDER["only"],PROVIDER["order"])
        self.assertNotIn("reasoning",PROVIDER)

    def test_recorded_header_is_metadata_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):stonebench_task("http://127.0.0.1:1/mcp",BUDGET,Path(tmp)/"bad",
                config=GenerateConfig(extra_headers={"Authorization":"secret"}))
            task,attempt=stonebench_task("http://127.0.0.1:1/mcp",BUDGET,Path(tmp)/"okay",
                config=GenerateConfig(extra_headers={"X-OpenRouter-Metadata":"enabled"}),max_context_bytes=524288,stop_on_missing_usage=True)
            self.assertEqual(attempt.max_context_bytes,524288)
            self.assertTrue(attempt.stop_on_missing_usage)

    def test_scripted_provider_receives_schema_infos_not_callable_tools(self):
        from inspect_ai.model import ChatMessageUser
        from inspect_ai.tool import ToolInfo
        script=Rehearsal(None,BUDGET,"selected")
        output=script([ChatMessageUser(content="sample")],[ToolInfo(name="describe_task",description="Task")],GenerateConfig())
        self.assertEqual(len(output.message.tool_calls),3)
        self.assertGreater(script.context_bytes[0],0)

    def test_paid_gate_scope_hash_and_explicit_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"authorization.json"
            path.write_text(json.dumps({"plan_sha256":plan_hash(),"scope":"calibration","authorized_by_user":True}))
            require_authorization(path,"calibration")
            with self.assertRaises(ValueError):require_authorization(path,"paid")
            for value in ({"plan_sha256":"stale","scope":"paid","authorized_by_user":True},
                          {"plan_sha256":plan_hash(),"scope":"paid","authorized_by_user":False}):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):require_authorization(path,"paid")

    def test_sentinel_secret_stays_only_in_environment(self):
        sentinel="SENTINEL_SECRET_NEVER_ARCHIVE_15"
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{},clear=True):
            path=Path(tmp)/"openrouter.env"
            path.write_text("# local only\nOPENROUTER_API_KEY="+sentinel+"\n")
            self.assertIs(load_secret(path),True)
            self.assertEqual(os.environ["OPENROUTER_API_KEY"],sentinel)
            self.assertNotIn(sentinel,json.dumps(plan()))
            self.assertNotIn("api_key",json.dumps(plan()))
            path.write_text("OPENROUTER_API_KEY=\n")
            with self.assertRaises(ValueError):load_secret(path)

    def test_reset_checks_negative_controls(self):
        import copy
        snapshot={"checkpoint_state":{"world_time":0,"time_of_day":0,"state":{"block_ticks":[],"fluid_ticks":[],"block_events":[],
            "blocks":{"1024,80,1024":{"block":"minecraft:air","inventory":[]}}}},"input":None}
        listing={"checkpoints":[]}
        description={"simulation_ticks":0,"preparation_ticks":0,"frozen":True,"environment":{}}
        assert_clean(snapshot,listing,description)
        for field,value in (("world_time",3),("time_of_day",3)):
            bad=copy.deepcopy(snapshot);bad["checkpoint_state"][field]=value
            with self.assertRaises(RuntimeError):assert_clean(bad,listing,description)
        for field in ("block_ticks","fluid_ticks","block_events"):
            bad=copy.deepcopy(snapshot);bad["checkpoint_state"]["state"][field]=["prior state"]
            with self.assertRaises(RuntimeError):assert_clean(bad,listing,description)
        bad=copy.deepcopy(snapshot);bad["input"]={"driver":"prior"}
        with self.assertRaises(RuntimeError):assert_clean(bad,listing,description)
        with self.assertRaises(RuntimeError):assert_clean(snapshot,{"checkpoints":["old"]},description)
        bad=copy.deepcopy(snapshot);bad["checkpoint_state"]["state"]["blocks"]["1024,80,1024"]={"block":"minecraft:chest","inventory":["old"]}
        with self.assertRaises(RuntimeError):assert_clean(bad,listing,description)

    def test_failed_incomplete_archive_roundtrip(self):
        import tarfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"campaign";root.mkdir()
            (root/"failed.json").write_text('{"status":"infrastructure_error"}')
            runtime=Path(tmp)/"runtime";(runtime/"world").mkdir(parents=True)
            (runtime/"world/level.dat").write_bytes(b"exact-world")
            (runtime/"libraries").mkdir();(runtime/"libraries/unused.jar").write_bytes(b"copy-dependency")
            output=archive(root,[runtime])
            check=json.loads((root/"archive-check.json").read_text())
            self.assertTrue(check["verified"])
            with tarfile.open(output,"r:xz") as stream:
                self.assertEqual(stream.extractfile("runtime-0/world/level.dat").read(),b"exact-world")
                self.assertNotIn("runtime-0/libraries/unused.jar",stream.getnames())
                self.assertIn("campaign/failed.json",stream.getnames())


if __name__=="__main__":unittest.main()
