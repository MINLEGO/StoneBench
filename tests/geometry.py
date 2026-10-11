"""Source-table assertions on real MCP geometry; no full alpha protocol claim."""
import json
import os
from pathlib import Path
import unittest
from integration import StoneBenchRuntimeIntegration, TASK_ID
from construction import point, placement


class GeometryRuntimeIntegration(StoneBenchRuntimeIntegration):
    async def modify(self, session, rows):
        report = await self.call(session, "modify_blocks", {"blocks": rows, "notify_neighbors": True})
        self.assert_ok(report)
        return report

    async def geometry(self, session, expected="open", **extra):
        report = await self.call(session, "check_geometry", {"expected_state": expected, **extra})
        self.assert_ok(report)
        self.assertTrue(report["frozen"])
        self.assertEqual(report["ticks_executed"], 0)
        self.evidence.append(report)
        return {row["id"]: row for row in report["criteria"]}

    async def test_real_mcp_server_contract(self):
        await self._connect()
        self.evidence = []
        try:
            a, b = self.sessions
            for session in self.sessions:
                self.assert_ok(await self.call(session, "start_attempt", {"task_id": TASK_ID}))
            names = {tool.name for tool in (await a.list_tools()).tools}
            self.assertTrue({"describe_rules", "check_geometry", "__test_geometry_entity"}.issubset(names))
            rules = await self.call(a, "describe_rules")
            self.assert_ok(rules)
            self.assertEqual(rules["protocol_version"], "regular-door-alpha-2026-10-11")
            table = {row["id"]: row for row in rules["criteria"]}
            self.assertEqual(table["frame_state"]["source_index"], 30358)
            self.assertEqual(table["continuable"]["source_index"], 14017)
            self.assertEqual(table["door_composition"]["source_index"], 2932)

            # A real two-sided 2x2 piston door: open quartz at side pillars, closed at fixed passage.
            rows = []
            for y in (80, 81):
                for x, facing, block_x in ((1022, "east", 1023), (1027, "west", 1026)):
                    rows += [placement(point(x, y, 1024), "minecraft:sticky_piston", {"facing": facing}),
                             placement(point(block_x, y, 1024), "minecraft:quartz_block")]
            for x in range(1023, 1027):
                for y in (79, 82):
                    rows.append(placement(point(x, y, 1024), "minecraft:quartz_block"))
            await self.modify(a, rows)
            opened = await self.geometry(a)
            self.assertEqual(opened["frame_state"]["status"], "satisfied", "Rules 30358 opened frame")
            self.assertEqual(opened["encadrement"]["status"], "satisfied", "Dummies 9641 fixed layer physical walls")
            self.assertEqual(opened["continuable"]["status"], "satisfied", "Rules 14017/Dummies 5274 fixed entrance pattern")
            self.assertEqual(opened["stable_state"]["status"], "indeterminate")
            power = [placement(point(x, y, 1025), "minecraft:redstone_block") for x in (1022, 1027) for y in (80, 81)]
            await self.modify(a, power)
            self.assert_ok(await self.call(a, "advance", {"ticks": 8, "trace": True}))
            closed = await self.geometry(a, "closed")
            self.assertEqual(closed["frame_state"]["status"], "satisfied", "Vanilla actually moved all four door blocks")
            self.assertEqual(closed["door_composition"]["status"], "satisfied", "Rules 2932/31749 canonical quartz")
            self.assertEqual(closed["encadrement"]["status"], "satisfied", "Piston head full inward collision face is valid enclosure")
            await self.modify(a, [placement(point(x, y, 1025), "minecraft:air") for x in (1022, 1027) for y in (80, 81)])
            self.assert_ok(await self.call(a, "advance", {"ticks": 8}))
            opened = await self.geometry(a)
            self.assertEqual(opened["frame_state"]["status"], "satisfied")

            # Obstruction anywhere through observed circuit depth cannot be hidden by moving the frame.
            obstacle = point(1024, 80, 1030)
            await self.modify(a, [placement(obstacle, "minecraft:stone")])
            blocked = await self.geometry(a)
            self.assertEqual(blocked["continuable"]["status"], "failed")
            await self.modify(a, [placement(obstacle, "minecraft:air"), placement(point(1024, 79, 1024), "minecraft:air")])
            shifted = await self.geometry(a)
            self.assertEqual(shifted["encadrement"]["status"], "failed")
            rejected = await self.call(a, "check_geometry", {"expected_state": "open", "frame_min_z": 1025, "frame_max_z": 1025})
            self.assert_error(rejected, "validation")
            await self.modify(a, [placement(point(1024, 79, 1024), "minecraft:quartz_block")])

            self.assert_ok(await self.call(a, "__test_geometry_entity", {"present": True}))
            entities = await self.geometry(a)
            self.assertEqual(entities["no_entities"]["status"], "failed", "Alpha excludes entity constructions")
            self.assert_ok(await self.call(a, "__test_geometry_entity", {"present": False}))
            no_entities = await self.geometry(a)
            self.assertEqual(no_entities["no_entities"]["status"], "satisfied")
            # No static evidence may certify cycles/clock necessity, and record rules stay unverified.
            for criterion in ("stable_state", "no_required_clock", "influence_coverage", "input"):
                self.assertEqual(no_entities[criterion]["status"], "indeterminate")
            for criterion in ("record_reliability", "record_isolation", "record_seamless"):
                self.assertEqual(no_entities[criterion]["status"], "not_verified")
            exclusion_rejected = await self.call(a, "check_geometry", {"expected_state": "open", "exclude": [obstacle]})
            self.assert_error(exclusion_rejected, "validation")

            # Explicit two-layer frame remains possible; no face image imposes a depth-one rule.
            two_layers = []
            for z in (1024, 1025):
                for y in range(79, 83):
                    for x in range(1023, 1027):
                        two_layers.append(placement(point(x, y, z), "minecraft:quartz_block"))
            await self.modify(b, two_layers)
            multi = await self.geometry(b, "closed", frame_min_z=1024, frame_max_z=1025)
            self.assertEqual(multi["frame_state"]["status"], "satisfied")
            self.assertEqual(multi["regular_arrangement"]["status"], "satisfied")
            self.assertEqual(multi["door_composition"]["status"], "satisfied")
            for position, orientation, face in ((point(1023, 83, 1025), "up", "floor"), (point(1023, 78, 1025), "down", "ceiling")):
                support = point(1023, 82 if orientation == "up" else 79, 1025)
                await self.modify(b, [placement(position, "minecraft:lever", {"face": face, "facing": "north"})])
                invalid_input = await self.call(b, "declare_input", {"device": "minecraft:lever", "position": position, "input_block": support, "orientation": orientation})
                self.assert_error(invalid_input, "validation")
                await self.modify(b, [placement(position, "minecraft:air")])
            device, support = point(1023, 80, 1026), point(1023, 80, 1025)
            await self.modify(b, [placement(device, "minecraft:lever", {"face": "wall", "facing": "south"})])
            self.assert_ok(await self.call(b, "declare_input", {"device": "minecraft:lever", "position": device, "input_block": support, "orientation": "south"}))
            declared = await self.geometry(b, "closed", frame_min_z=1024, frame_max_z=1025)
            self.assertEqual(declared["input"]["status"], "satisfied")
            self.assertEqual(declared["input"]["observed"]["input_block"], support)
        finally:
            out = Path(os.environ.get("STONEBENCH_GEOMETRY_EVIDENCE", ".runtime/geometry-summary.json"))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
            await self.stack.aclose()


if __name__ == "__main__":
    unittest.main()
