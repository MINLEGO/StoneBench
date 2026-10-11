"""Validate exported transition traces and prove false-rest/truncation controls fail."""
import copy
import hashlib
import json
from pathlib import Path
import sys


class Evidence:
    def __init__(self, server):
        self.artifacts = Path(server) / "stonebench" / "artifacts"
        self.verified = {}

    def rows(self, ref):
        path = self.artifacts / (ref["artifact_id"] + ".jsonl")
        data = path.read_bytes()
        rows = [json.loads(line) for line in data.splitlines()]
        actual = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "count": len(rows)}
        if not ref["complete"] or any(actual[key] != ref[key] for key in actual):
            raise ValueError("Artifact integrity mismatch " + ref["artifact_id"])
        self.verified[ref["artifact_id"]] = actual
        return rows

    def verify_operation_stream(self, ref, report):
        path = self.artifacts / (ref["artifact_id"] + ".jsonl")
        digest, size, count = hashlib.sha256(), 0, 0
        with path.open("rb") as source:
            for line in source:
                digest.update(line); size += len(line)
                event = json.loads(line)
                tick = event["tick_index"]
                if event["operation_order"] != count or not 1 <= tick <= report["ticks_executed"] or event["simulation_index"] != report["initial"]["simulation_index"] + tick:
                    raise ValueError("Discontinuous operation event stream")
                expected = report["initial"]["world_time"] + tick
                if event["world_time"] not in (expected-1, expected):
                    raise ValueError("Operation event clock outside its actual tick")
                count += 1
        actual = {"sha256": digest.hexdigest(), "bytes": size, "count": count}
        if not ref["complete"] or any(actual[key] != ref[key] for key in actual):
            raise ValueError("Artifact integrity mismatch " + ref["artifact_id"])
        self.verified[ref["artifact_id"]] = actual
        return actual

    def trace(self, report, ticks=None):
        ticks = self.rows(report["trace"]) if ticks is None else ticks
        expected = report["trace"]["expected_ticks"]
        if len(ticks) != expected or report["ticks_executed"] != expected:
            raise ValueError("Truncated or mismatched transition trace")
        previous = None
        for ordinal, tick in enumerate(ticks, 1):
            if tick["tick_index"] != ordinal or tick["simulation_index"] != report["trace"]["start_simulation_index"] + ordinal or tick["world_time"] != report["trace"]["start_world_time"] + ordinal or tick["phase"] != "end_tick":
                raise ValueError("Discontinuous real tick observation")
            blocks = self.rows(tick["state"]["blocks"])
            partition = self.rows(tick["adapter_blocks"]) + self.rows(tick["construction_blocks"])
            coordinate = lambda b: (b["x"], b["y"], b["z"])
            if sorted(blocks, key=coordinate) != sorted(partition, key=coordinate) or len({coordinate(b) for b in partition}) != len(blocks):
                raise ValueError("Input/construction partition altered complete raw records")
            self.rows(tick["events"])
            state = {str((b["x"], b["y"], b["z"])): b for b in blocks}
            rest = tick["rest"]
            if previous is not None and rest["states_equal"] != (state == previous):
                raise ValueError("Reported equality differs from exact block/NBT/runtime records")
            if rest["tick"] != ordinal:
                raise ValueError("Rest tick differs from observation")
            if rest["status"] == "terminated":
                pending = any(tick["state"][q] for q in ("block_ticks", "fluid_ticks", "block_events"))
                mobile = any(b["block"] == "minecraft:moving_piston" or b.get("block_entity_type") == "minecraft:piston" for b in blocks)
                uncertain = any(b.get("block_entity_type") not in (None, "minecraft:chest") for b in blocks)
                if pending or mobile or uncertain or not rest["states_equal"] or not tick["complete"] or tick["state"]["coverage"]["status"] != "observed" or "relevant_events_this_tick" in rest["causes"]:
                    raise ValueError("False rest with future work, motion, missing coverage or memory")
            previous = state
        if ticks[-1]["rest"] != report["transition"]:
            raise ValueError("Final domain report differs from last real observation")
        return ticks


def main():
    root, summary_path = map(Path, sys.argv[1:3])
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    evidence = Evidence(root / "server-1")
    records = {}
    for name in ("piston", "piston_close", "chain", "hopper_cooldown", "hopper_empty", "hopper_locked", "clock_short"):
        report = summary[name].get("report", summary[name])
        ticks = evidence.trace(report)
        records[name] = {"status": report["transition"]["status"], "tick": len(ticks), "last_movement_tick": report["transition"]["last_movement_tick"], "recognition_tick": report["transition"]["recognition_tick"]}
    negative = []
    piston = summary["piston"]
    original = evidence.rows(piston["trace"])
    fake = copy.deepcopy(original)
    fake[0]["rest"]["status"] = "terminated"
    fake[0]["rest"]["states_equal"] = True
    for name, altered in (("false_rest_with_scheduled_work", fake), ("truncated_trace", original[:-1])):
        try:
            evidence.trace(piston, altered)
        except ValueError as error:
            negative.append({"control": name, "rejected": True, "diagnostic": str(error)})
        else:
            raise AssertionError("Negative control accepted: " + name)
    second = Evidence(root / "server-2")
    partial = summary["chunk_loss"]
    if partial["status"] != "error" or partial["error"]["kind"] != "infrastructure" or partial["error"]["code"] != "chunks_unavailable" or partial["continuity"]["complete"]:
        raise ValueError("Chunk loss did not preserve infrastructure/partial result")
    insufficient = summary["coverage"]
    if insufficient["transition"]["status"] != "indeterminate" or insufficient["continuity"]["complete"] or insufficient["coverage"]["status"] != "insufficient":
        raise ValueError("Insufficient coverage acquired positive rest")
    second.rows(insufficient["trace"])
    for item in summary.get("input_callbacks", []):
        evidence.trace(item["pause"]); evidence.trace(item["finished"])
        if item["finished"]["transition"]["external_input_events"] <= 0:
            raise ValueError("Native expected external callback classification lost")
    if "unexpected_adapter_callback" in summary:
        item = summary["unexpected_adapter_callback"]
        evidence.trace(item["waiting"]); evidence.trace(item["finished"])
        if item["finished"]["transition"]["external_input_events"] != 0:
            raise ValueError("Wrong scheduled type was classified external")
    full = summary.get("clock_full", {})
    if "report" in full:
        report = full["report"]
        if report["transition"]["status"] != "limit_reached" or report["ticks_executed"] != 36000 or report["transition"]["observed_ticks"] != 36000 or report["world_time"] - report["initial"]["world_time"] != 36000 or report["transition"]["pending_ticks"] != 36000 or report["transition"]["recognition_tick"] is not None:
            raise ValueError("Full clock did not reach actual 36000-tick bound")
        records["clock_full"] = {"status": "limit_reached", "real_ticks": 36000, "wall_seconds": full["wall_seconds"]}
        evidence.verify_operation_stream(report["intratick_events"], report)
    print(json.dumps({"verified": True, "fixtures": records, "negative_controls": negative, "artifact_hashes": {"server-1": evidence.verified, "server-2": second.verified}}, indent=2))


if __name__ == "__main__":
    main()
