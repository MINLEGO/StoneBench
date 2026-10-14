"""Run community reference doors (.litematic, known conformant) through the real verifier.

STONEBENCH_REFERENCE_DOORS: '|'-separated .litematic paths. Door size comes from the file name ("3x3 door ...").
Findings are recorded, not asserted: a door the verifier rejects is a result, not a test failure.
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import integration
from litematic import load

ORIGIN = (1024, 80, 1024)
DIRECTIONS = {"north": (0, 0, -1), "south": (0, 0, 1), "east": (1, 0, 0), "west": (-1, 0, 0)}


def split(state):
    name, _, props = state.partition("[")
    return name, dict(p.split("=") for p in props.rstrip("]").split(",")) if props else {}


def find_passage(cells, size, sx, sy, sz):
    """The size x size air rectangle in one z layer, flanked left/right/above by quartz."""
    found = []
    solid = lambda x, y, z: split(cells.get((x, y, z), "minecraft:air"))[0] == "minecraft:quartz_block"
    for z in range(sz):
        for y in range(sy - size + 1):
            for x in range(1, sx - size):
                if any((x + i, y + j, z) in cells for i in range(size) for j in range(size)):
                    continue
                if all(solid(x - 1, y + j, z) and solid(x + size, y + j, z) for j in range(size)) \
                        and all(solid(x + i, y + size, z) for i in range(size)):
                    found.append((x, y, z))
    return found


class ReferenceDoors(integration.StoneBenchRuntimeIntegration):
    async def call(self, session, name, arguments=None):
        # No size/source assertions of the contract suite: a large diagnostic is a result here.
        return (await session.call_tool(name, arguments or {})).structuredContent

    async def test_reference_doors(self):
        await self._connect()
        results = []
        try:
            self.free = list(self.sessions)  # each attempt consumes one server directory
            # Static copy of describe_blocks: any call before start_attempt would implicitly start an attempt.
            source = Path(__file__).resolve().parents[1] / "docs" / "blocs-a-prendre-en-charge.md"
            catalog = {f"minecraft:{line.strip()}" for line in source.read_text(encoding="utf-8").splitlines() if re.fullmatch(r"[a-z_0-9]+\s*", line)}
            for path in filter(None, os.environ["STONEBENCH_REFERENCE_DOORS"].split("|")):
                result = {"door": Path(path).name}
                results.append(result)
                try:
                    await self.run_door(path, catalog, result)
                except Exception as error:  # a stage failing is a finding about that door
                    result["stage_error"] = f"{type(error).__name__}: {error}"[:1500]
                print(json.dumps(result, indent=1, default=str))
        finally:
            out = os.environ.get("STONEBENCH_REFERENCE_EVIDENCE")
            if out:
                Path(out).write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
            await self.stack.aclose()

    async def run_door(self, path, catalog, result):
        size = int(re.match(r"(\d)x\1", Path(path).name).group(1))
        blocks = load(path)
        sx, sy, sz = blocks["_size"]
        tes = blocks["_tes"]
        cells = {k: v for k, v in blocks.items() if isinstance(k, tuple)}
        # STONEBENCH_REFERENCE_MOVE="3x3:3,7,0>2,7,0": move one block (used to apply a design fix to an idle-state file).
        for rule in filter(None, os.environ.get("STONEBENCH_REFERENCE_MOVE", "").split("|")):
            prefix, _, move = rule.partition(":")
            if Path(path).name.startswith(prefix):
                src, dst = (tuple(map(int, part.split(","))) for part in move.split(">"))
                cells[dst] = cells.pop(src)
                result["moved"] = f"{src}>{dst}"
        missing = sorted({split(v)[0] for v in cells.values()} - catalog)
        if missing:
            result["status"] = "not_buildable"
            result["missing_blocks"] = missing
            return
        passage = find_passage(cells, size, sx, sy, sz)
        if len({c[:2] for c in passage}) == 1:  # thick door: several layers share the same cross-section; use the first
            passage = passage[:1]
        if len(passage) != 1:
            result["status"] = "passage_not_found"
            result["candidates"] = passage
            return
        px, py, pz = passage[0]
        # The design omits the hallway it sits in; add quartz only where the ring around the passage is empty.
        ring = [(px + i, py - 1, pz) for i in range(size)] + [(px + i, py + size, pz) for i in range(size)]             + [(px - 1, py + j, pz) for j in range(size)] + [(px + size, py + j, pz) for j in range(size)]
        added = [c for c in ring if c not in cells]
        for c in added:
            cells[c] = "minecraft:quartz_block"
        result["hallway_added"] = added
        world = lambda x, y, z: (ORIGIN[0] + x - px, ORIGIN[1] + y - py, ORIGIN[2] + z - pz)
        result["passage_offset"] = passage[0]

        if not self.free:
            result["status"] = "no_free_server"
            return
        session = self.free.pop(0)
        started = await self.call(session, "start_attempt", {"task_id": f"{size}x{size}-volume"})
        self.assert_ok(started)
        details = {}
        for ident in {split(v)[0] for v in cells.values()}:
            details[ident] = await self.call(session, "describe_block", {"id": ident})
        placements, dropped = [], set()
        for (x, y, z), state in sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2])):
            ident, props = split(state)
            configurable = details[ident]["configurable"]
            wx, wy, wz = world(x, y, z)
            item = {"x": wx, "y": wy, "z": wz, "block": ident}
            params = {}
            for key, value in props.items():
                if key in configurable and value in [str(v) for v in configurable[key]]:
                    params[key] = value
                elif key not in details[ident]["computed"]:
                    dropped.add(f"{ident}:{key}={value}")
            if params:
                item["parameters"] = params
            items = [{"slot": i["Slot"], "item": i["id"], "count": i.get("count", i.get("Count"))}
                     for i in tes.get((x, y, z), {}).get("Items", [])]
            if items:
                item["inventory"] = items
            placements.append(item)
        result["blocks"] = len(placements)
        result["unmapped_properties"] = sorted(dropped)

        for i in range(0, len(placements), 256):
            placed = await self.call(session, "modify_blocks", {"blocks": placements[i:i + 256], "notify_neighbors": os.environ.get("STONEBENCH_REFERENCE_NOTIFY") == "1"})
            if placed["status"] != "ok":
                result["status"] = "build_failed"
                result["error"] = placed.get("error")
                return

        device = next(k for k, v in cells.items() if split(v)[0] in ("minecraft:lever", "minecraft:stone_button"))
        ident, props = split(cells[device])
        dx, dy, dz = DIRECTIONS[props["facing"]]
        declaration = {"device": ident, "position": dict(zip("xyz", world(*device))), "orientation": props["facing"],
                       "input_block": dict(zip("xyz", world(device[0] - dx, device[1] - dy, device[2] - dz)))}

        stages = result.setdefault("stages", {})

        async def stage(name, tool, args=None):
            payload = await self.call(session, tool, args)
            stages[name] = payload["status"]
            if payload["status"] != "ok":
                result["status"] = f"{name}_failed"
                result["error"] = payload.get("error")
                return None
            transition = payload.get("transition")
            if transition:
                result.setdefault("transitions", {})[name] = {k: (v if len(json.dumps(v, default=str)) < 400 else json.dumps(v, default=str)[:400]) for k, v in transition.items()}
                if transition.get("status") != "terminated":
                    stages[name] = f"transition_{transition.get('status')}"
            return payload

        if not await stage("initial_rest", "transition", {"max_ticks": 36000, "trace": True}): return
        result["geometry_open"] = self.geometry_summary(await stage("geometry_open", "check_geometry", {"expected_state": "open"}))
        if not await stage("declare_input", "declare_input", declaration): return
        if not await stage("interact", "transition", {"max_ticks": 36000, "trace": True, "interact": True}): return
        result["geometry_closed"] = self.geometry_summary(await stage("geometry_closed", "check_geometry", {"expected_state": "closed"}))
        if not await stage("closed_rest", "transition", {"max_ticks": 36000, "trace": True}): return
        created = await stage("create_checkpoint", "create_checkpoint")
        if not created: return
        await self.call(session, "__test_verification_config", {"scenario": "none"})
        started = await self.call(session, "verify_checkpoint", {"checkpoint_id": created["checkpoint"]["checkpoint_id"]})
        if started["status"] != "ok":
            result["status"] = "verify_not_started"
            result["error"] = started.get("error")
            return
        request_id = started["verification"]["request_id"]
        while "verdict" not in (verification := (await self.call(session, "verification_status", {"request_id": request_id})).get("verification") or {}):
            await asyncio.sleep(1)
        result["status"] = "verified"
        result["verification"] = {k: verification.get(k) for k in
                                  ("verdict", "conforms_to_alpha", "stop_cause", "cycles_executed", "faults", "infrastructure_error", "measurements")}

    @staticmethod
    def geometry_summary(payload):
        if not payload:
            return None
        return [{"id": c["id"], "status": c["status"], "observed": c.get("observed")}
                for c in payload.get("criteria", []) if c.get("status") != "satisfied"]


if __name__ == "__main__":
    import unittest
    unittest.main(defaultTest="ReferenceDoors.test_reference_doors")
