"""Replay final measurement code over original hash-checked real MCP boundaries."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from measurements import measure
from verification_worker import artifact, trace_complete

summary=json.loads(Path(sys.argv[1]).read_text())
report=summary["report"]
roots={row["mode"]:Path(row["server_root"]) for row in report["copies"]}
request_root=roots["repeater"].parent
request=json.loads((request_root/"request.json").read_text())
manifest=json.loads((request_root.parent.parent/"checkpoints"/request["checkpoint_id"]/"manifest.json").read_text())
closed=next(b["geometry"] for b in report["boundaries"] if b["expected_state"]=="closed")
results=[]
for boundary,original in zip(report["boundaries"],report["measurements"]["transitions"],strict=True):
    root=roots[boundary["mode"]]
    operation=boundary["operation"]
    events=artifact(root,operation["intratick_events"])
    samples=[operation["initial"]]+artifact(root,operation["trace"])
    samples=({"world_time":s["world_time"],"blocks":artifact(root,s["state"]["blocks"])} for s in samples)
    replay=measure(operation,samples,events,closed,boundary["geometry"],artifact(request_root.parents[2],boundary["snapshot"])[0]["input"],trace_complete(root,operation),manifest["provenance"]["memory_coverage"])
    assert all(json.loads(json.dumps(replay[k]))==original[k] for k in replay),boundary["mode"]
    redundant=[e for e in events if e["position"]=={"x":1033,"y":81,"z":1025}]
    assert any(e["kind"]=="block_state_read" for e in redundant)
    metric=replay["dynamic_volume"]
    assert metric["status"]=="indeterminate" and metric["value"] is None and metric["observed_value"]==320
    assert metric["minimum_envelope"]!=metric["maximum_envelope"]
    results.append({"mode":boundary["mode"],"state":boundary["expected_state"],"matches_original":True,"redundant_stone_events":sorted({e["kind"] for e in redundant}),"exact_value":None,"observed_high_value":320})
print(json.dumps({"final_code_replay":results,"all_artifact_hashes_validated":True},indent=2))
