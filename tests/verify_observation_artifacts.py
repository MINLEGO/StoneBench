"""Verify exported evidence bytes/counts and rebuild complete snapshot/event references."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile


def check(path):
    with zipfile.ZipFile(path) as archive:
        refs, rows = {}, {}
        for name in archive.namelist():
            if not name.endswith(".jsonl.meta"):
                continue
            ref = json.loads(archive.read(name))
            content = archive.read(name[:-5])
            assert len(content) == ref["bytes"], name
            assert hashlib.sha256(content).hexdigest() == ref["sha256"], name
            entries = [json.loads(line) for line in content.decode("utf-8").splitlines()]
            assert len(entries) == ref["count"], name
            assert ref["complete"] is True, name
            refs[ref["artifact_id"]], rows[ref["artifact_id"]] = ref, entries
        assert refs, "No recoverable artifacts"
        traces = []
        for identity, ref in refs.items():
            if ref["kind"] != "trace":
                continue
            complete = len(rows[identity]) == ref["expected_ticks"]
            for index, tick in enumerate(rows[identity], 1):
                assert tick["tick_index"] == index
                assert tick["simulation_index"] == ref["start_simulation_index"] + index
                assert tick["world_time"] == ref["start_world_time"] + index
                assert tick["phase"] == "end_tick"
                blocks = rows[tick["state"]["blocks"]["artifact_id"]]
                events = rows[tick["events"]["artifact_id"]]
                assert len(blocks) == tick["state"]["blocks"]["count"]
                assert [event["order"] for event in events] == list(range(len(events)))
                assert all(event["tick_index"] == index for event in events)
                complete = complete and tick["complete"]
            traces.append({"artifact_id": identity, "expected_ticks": ref["expected_ticks"], "observations": len(rows[identity]), "complete": complete})
        return {"archive": str(path), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(), "artifacts": len(refs), "entries": sum(len(value) for value in rows.values()), "traces": traces}


if __name__ == "__main__":
    print(json.dumps([check(value) for value in sys.argv[1:]], indent=2))
