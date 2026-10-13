"""Source-table assertions on real MCP geometry; no full alpha protocol claim."""
import json
import os
from pathlib import Path
import unittest
import integration
from integration import source_leaks
from construction import point, placement
TASK_ID = integration.TASK_ID
SOURCE_ROW_KEYS = {"sources", "source", "revision_id", "source_index"}


class GeometryRuntimeIntegration(integration.StoneBenchRuntimeIntegration):
    async def modify(self, session, rows):
        report = await self.call(session, "modify_blocks", {"blocks": rows, "notify_neighbors": True})
        self.assert_ok(report)
        return report

    async def geometry(self, session, expected="open", **extra):
        report = await self.call(session, "check_geometry", {"expected_state": expected, **extra})
        self.assert_ok(report)
        self.assertTrue(report["frozen"])
        self.assertEqual(report["ticks_executed"], 0)
        self.assertFalse(report["mutated"])
        self.evidence.append(report)
        full = self.audit_row(session, report)
        # Presentation never changes a verdict: same statuses, observed evidence and explanations as the audit.
        for key in ("geometry_status", "conforms_to_alpha", "measurement_roles", "coverage", "expected_state"):
            self.assertEqual(report[key], full[key], key)
        self.assertEqual(report["criteria"][-1]["id"], "record_eligibility")
        self.assertEqual(len(report["criteria"]), 14)
        self.assertEqual(report["criteria"][:-1], [{key: value for key, value in row.items() if key not in SOURCE_ROW_KEYS} for row in full["criteria"][:-3]])
        self.assertEqual({row["status"] for row in full["criteria"][-3:]}, {report["criteria"][-1]["status"]})
        self.assertTrue(all(row["sources"] and row["sources"][0]["revision_id"] and row["sources"][0]["locator"] for row in full["criteria"]))
        self.assertTrue(source_leaks(full))
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
            # Concise: the direct MCP result (both forms) fits the harness's 16 KiB threshold, which stays unchanged.
            raw = await a.call_tool("describe_rules", {})
            self.assertLess(len(raw.content[0].text.encode("utf-8")), 16384)
            self.assertEqual(len(rules["criteria"]), 14)
            self.assertNotIn("record_reliability", table)
            self.assertEqual(table["record_eligibility"]["mandatory"], False)
            self.assertIn("outside this alpha", table["record_eligibility"]["expected"])
            for row in rules["criteria"]:
                self.assertEqual(set(row), {"id", "expected", "observation", "coverage", "mandatory"}, row)
                self.assertTrue(all(row[key] for key in ("expected", "observation", "coverage")), row)
            self.assertEqual({row["id"] for row in rules["criteria"] if row["mandatory"]},
                {"fixed_passage", "door_orientation", "regular_arrangement", "door_composition", "frame_state", "encadrement",
                 "continuable", "input", "no_entities", "no_required_clock", "stable_state", "influence_coverage"})
            self.assertFalse(table["hallway_composition"]["mandatory"])
            self.assertEqual({"volume", "exclusions", "timing_origin", "opening_end", "closing_end", "movement_end", "rest"},
                             set(rules["measurement_contract"]))
            self.assertIn("ceil", rules["measurement_contract"]["volume"])

            # The audit keeps the full sourced response; the agent form is that response without its citations.
            audit = self.audit_row(a, rules)
            full = {row["id"]: row for row in audit["criteria"]}
            self.assertEqual(len(full), 16)
            self.assertTrue(source_leaks(audit), "The audit must retain what the agent never sees")
            self.assertEqual(audit["source"], integration.RULES_REFERENCE)
            self.assertEqual(full["frame_state"]["source_index"], 30358)
            self.assertEqual(full["continuable"]["source_index"], 14017)
            self.assertEqual(full["door_composition"]["source_index"], 2932)
            locator = "Implementation Decisions / Description d'une tâche et zone pertinente"
            for criterion in ("fixed_passage", "influence_coverage"):
                alpha_source = next(r for r in full[criterion]["sources"] if r["authority"] == "alpha_scope")
                self.assertEqual(alpha_source["locator"], locator)
            self.assertNotIn("�", json.dumps(full, ensure_ascii=False), "Source strings must not contain replacement characters")
            self.assertEqual(full["no_entities"]["sources"][0]["authority"], "alpha_scope")
            self.assertEqual(full["influence_coverage"]["sources"][0]["authority"], "alpha_scope")
            self.assertEqual({r["locator"] for r in full["door_composition"]["sources"]}, {"2932", "31749"})
            self.assertEqual(full["encadrement"]["sources"][1]["locator"], "9641")
            self.assertEqual(full["continuable"]["sources"][1]["locator"], "5274")
            self.assertEqual({r["locator"] for r in full["hallway_composition"]["sources"]}, {"3627", "3852"})
            self.assertEqual(audit["measurement_contract"]["volume_source_index"], 23868)
            for identifier, row in table.items():
                if identifier != "record_eligibility":
                    self.assertEqual(row, {key: value for key, value in full[identifier].items() if key not in SOURCE_ROW_KEYS}, identifier)
            empty_closed = await self.geometry(a, "closed")
            self.assertEqual(empty_closed["regular_arrangement"]["status"], "failed", "Observed air is not a closed rectangular door")
            self.assertEqual(empty_closed["frame_state"]["status"], "failed")

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
            self.assertEqual(opened["regular_arrangement"]["status"], "indeterminate", "Open snapshot cannot establish closed arrangement")
            self.assertEqual(opened["stable_state"]["status"], "indeterminate")
            power = [placement(point(x, y, 1025), "minecraft:redstone_block") for x in (1022, 1027) for y in (80, 81)]
            await self.modify(a, power)
            self.assert_ok(await self.call(a, "advance", {"ticks": 8, "trace": True}))
            closed = await self.geometry(a, "closed")
            self.assertEqual(closed["frame_state"]["status"], "satisfied", "Vanilla actually moved all four door blocks")
            self.assertEqual(closed["regular_arrangement"]["status"], "satisfied")
            self.assertEqual(closed["door_composition"]["status"], "satisfied", "Rules 2932/31749 canonical quartz")
            self.assertEqual(closed["encadrement"]["status"], "satisfied", "Piston head full inward collision face is valid enclosure")
            heads = [row for row in self.evidence[-1]["measurement_roles"] if row.get("block") == "minecraft:piston_head"]
            self.assertTrue(heads)
            self.assertTrue(all(row["volume_exclusion"] == "retained_wiring" for row in heads), "A physical enclosure role does not erase piston circuitry")
            await self.modify(a, [placement(point(x, y, 1025), "minecraft:air") for x in (1022, 1027) for y in (80, 81)])
            self.assert_ok(await self.call(a, "advance", {"ticks": 8}))
            opened = await self.geometry(a)
            self.assertEqual(opened["frame_state"]["status"], "satisfied")

            occupied_frame = point(1024, 80, 1024)
            await self.modify(a, [placement(occupied_frame, "minecraft:stone")])
            obstructed_open = await self.geometry(a)
            self.assertEqual(obstructed_open["frame_state"]["status"], "failed", "Rules 30358 actual open passage obstruction")
            await self.modify(a, [placement(occupied_frame, "minecraft:air")])
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
            self.assertEqual(no_entities["record_eligibility"]["status"], "not_verified")
            self.assertTrue({"record_reliability", "record_isolation", "record_seamless"}.isdisjoint(no_entities))
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
            material = point(1024, 80, 1024)
            await self.modify(b, [placement(material, "minecraft:stone")])
            unknown_material = await self.geometry(b, "closed", frame_min_z=1024, frame_max_z=1025)
            self.assertEqual(unknown_material["door_composition"]["status"], "indeterminate", "Quartz substitution functionality is not inferred from a whitelist")
            await self.modify(b, [placement(material, "minecraft:quartz_block")])
            skydoor = await self.call(b, "check_geometry", {"expected_state": "closed", "normal": "+Y"})
            self.assert_error(skydoor, "validation")
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
            roles = self.evidence[-1]["measurement_roles"]
            support_role = next(row for row in roles if all(row[key] == support[key] for key in ("x", "y", "z")))
            self.assertEqual(support_role["volume_exclusion"], "retained_wiring", "Rules 30714 input block must not become arbitrary excluded frame")
            device_role = next(row for row in roles if all(row[key] == device[key] for key in ("x", "y", "z")))
            self.assertEqual(device_role["volume_exclusion"], "excluded_validated_input_adapter", "Rules 24437 input device exclusion")
            adapted = await self.call(b, "prepare_input", {"mode": "repeater"})
            self.assert_ok(adapted)
            self.assertTrue(adapted["construction_preserved"])
            repeater_geometry = await self.geometry(b, "closed", frame_min_z=1024, frame_max_z=1025)
            self.assertEqual(repeater_geometry["input"]["status"], "satisfied", "Actual driver remains a device; original coordinate is now a repeater")
            self.assertNotEqual(repeater_geometry["input"]["observed"]["driver"], device)
            self.assert_ok(await self.call(b, "__test_outside_influence"))
            incomplete = await self.geometry(b, "closed", frame_min_z=1024, frame_max_z=1025)
            self.assertEqual(incomplete["continuable"]["status"], "indeterminate")
            self.assertEqual(incomplete["influence_coverage"]["status"], "indeterminate")
            self.assertEqual(self.evidence[-1]["coverage"]["status"], "insufficient")
            self.assertFalse(self.evidence[-1]["conforms_to_alpha"])
        finally:
            out = Path(os.environ.get("STONEBENCH_GEOMETRY_EVIDENCE", ".runtime/geometry-summary.json"))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
            await self.stack.aclose()


if __name__ == "__main__":
    unittest.main()
