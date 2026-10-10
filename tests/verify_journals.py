"""Check actual world clocks against reported execution in complete MCP journals."""
import json
import pathlib
import sys


def check(path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows, "Empty operation journal"
    previous = {"world_time": 0, "simulation_ticks": 0, "preparation_ticks": 0}
    identities = set()
    for row in rows:
        assert row["operation_id"] not in identities, "Repeated operation id"
        identities.add(row["operation_id"])
        assert row["frozen"] is True, "Operation did not return frozen"
        useful = row["simulation_ticks"] - previous["simulation_ticks"]
        preparation = row["preparation_ticks"] - previous["preparation_ticks"]
        assert useful == row["ticks_executed"], row
        assert row["world_time"] - previous["world_time"] == useful + preparation, row
        previous = row
    return {"attempt_id": previous["attempt_id"], "operations": len(rows),
            "simulation_ticks": previous["simulation_ticks"],
            "preparation_ticks": previous["preparation_ticks"],
            "world_time": previous["world_time"],
            "errors": [{"code": row["error"]["code"], "ticks_executed": row["ticks_executed"]}
                       for row in rows if row["status"] == "error"]}


if __name__ == "__main__":
    reports = [check(pathlib.Path(value)) for value in sys.argv[1:]]
    assert len(reports) == 2
    assert reports[0]["attempt_id"] != reports[1]["attempt_id"]
    print(json.dumps({"status": "ok", "journals": reports}, indent=2))
