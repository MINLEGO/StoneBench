"""Real Minecraft/MCP observations: no fake tick or manufactured piston state."""
import json
import os
from pathlib import Path
import unittest

from integration import StoneBenchRuntimeIntegration, TASK_ID
from construction import point, placement, coordinates


class ObservationRuntimeIntegration(StoneBenchRuntimeIntegration):
    async def pages(self, session, ref, limit=7):
        rows, offset = [], 0
        while True:
            page = await self.call(session, "read_artifact", {"artifact_id": ref["artifact_id"], "offset": offset, "limit": limit})
            self.assert_ok(page)
            self.assertEqual(page["artifact"], ref)
            self.assertEqual(page["offset"], offset)
            self.assertLessEqual(len(page["entries"]), limit)
            rows.extend(page["entries"])
            if page["next_offset"] is None:
                self.assertTrue(page["complete"])
                break
            self.assertFalse(page["complete"])
            self.assertEqual(page["next_offset"], len(rows))
            offset = page["next_offset"]
        self.assertEqual(len(rows), ref["count"])
        return rows

    async def snapshot(self, session, observation):
        blocks = await self.pages(session, observation["state"]["blocks"], 256)
        return {coordinates(block): block for block in blocks}

    async def modify(self, session, blocks, notify=True):
        report = await self.call(session, "modify_blocks", {"blocks": blocks, "notify_neighbors": notify})
        self.assert_ok(report)
        return report

    async def test_real_mcp_server_contract(self):
        await self._connect()
        self.evidence = {}
        try:
            a, b = self.sessions
            for session in self.sessions:
                self.assert_ok(await self.call(session, "start_attempt", {"task_id": TASK_ID}))
            names = {tool.name for tool in (await a.list_tools()).tools}
            self.assertTrue({"read_region", "read_artifact", "compare_traces"}.issubset(names))
            await self.transients(a)
            await self.regions_and_inventories(a)
            await self.partial_trace(b)
            await self.outside_coverage(b)
        finally:
            output = Path(os.environ.get("STONEBENCH_OBSERVATION_EVIDENCE", ".runtime/observation-summary.json"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
            await self.stack.aclose()

    async def transients(self, session):
        observer, piston, stone = point(1030, 80, 1030), point(1030, 80, 1029), point(1031, 80, 1029)
        await self.modify(session, [placement(observer, "minecraft:observer", {"facing": "south"}), placement(piston, "minecraft:sticky_piston", {"facing": "east"}), placement(stone, "minecraft:quartz_block")])
        self.assert_ok(await self.call(session, "advance", {"ticks": 8}))
        changed = await self.modify(session, [placement(point(1030, 80, 1031), "minecraft:quartz_block")])
        self.assertGreater(changed["initial"]["world_time"], 0)
        # The observer queues its ordinary 2-tick callback while the world remains frozen.
        self.assertTrue(changed["final"]["state"]["block_ticks"], changed)
        for tick in changed["final"]["state"]["block_ticks"]:
            self.assertTrue({"trigger_tick", "priority", "sub_tick_order", "type", "x", "y", "z"}.issubset(tick))
        report = await self.call(session, "advance", {"ticks": 12, "trace": True})
        self.assert_ok(report)
        self.assertEqual(report["ticks_executed"], 12)
        self.assertTrue(report["frozen"])
        self.assertTrue(report["continuity"]["complete"], report)
        ticks = await self.pages(session, report["trace"], 3)
        self.assertEqual(len(ticks), 12)
        snapshots, events = [], []
        for i, tick in enumerate(ticks, 1):
            self.assertEqual(tick["tick_index"], i)
            self.assertEqual(tick["simulation_index"], report["trace"]["start_simulation_index"] + i)
            self.assertEqual(tick["world_time"], report["trace"]["start_world_time"] + i)
            self.assertEqual(tick["phase"], "end_tick")
            self.assertTrue(tick["complete"])
            snapshots.append(await self.snapshot(session, tick))
            tick_events = await self.pages(session, tick["events"], 256)
            self.assertEqual([event["order"] for event in tick_events], list(range(len(tick_events))))
            self.assertTrue(all(event["tick_index"] == i for event in tick_events))
            events.extend(tick_events)
        initial, final = await self.snapshot(session, report["initial"]), await self.snapshot(session, report["final"])
        observer_key = coordinates(observer)
        self.assertEqual(initial[observer_key]["parameters"]["powered"], "false")
        self.assertEqual(final[observer_key]["parameters"]["powered"], "false")
        self.assertIn("true", [snapshot[observer_key]["parameters"]["powered"] for snapshot in snapshots])
        diff = await self.pages(session, report["diff"], 256)
        self.assertFalse(any("1030,80,1030.parameters.powered" in row["field"] for row in diff), diff)
        kinds = {event["kind"] for event in events}
        self.assertTrue({"block_event_callback", "block_event_enqueued", "scheduled_block_tick", "block_tick_schedule_requested", "block_write_requested", "block_write_result", "block_state_read"}.issubset(kinds), kinds)
        self.assertTrue(all({"phase", "simulation_index", "world_time", "time_of_day", "operation_order"}.issubset(event) for event in events))
        moving = [block for snapshot in snapshots for block in snapshot.values() if block.get("block_entity_type") == "minecraft:piston"]
        self.assertTrue(moving, "Vanilla piston never exposed its mobile block entity")
        for block in moving:
            self.assertEqual(block["nbt"]["type"], 10)
            self.assertEqual(block["runtime"]["progress_type"], "float")
            self.assertEqual(block["runtime"]["saved_world_time_type"], "long")
        self.assertTrue(any(coordinates(block) == (1032, 80, 1029) for block in moving), moving)
        comparison = await self.call(session, "compare_traces", {"left": report["trace"]["artifact_id"], "right": report["trace"]["artifact_id"]})
        self.assert_ok(comparison)
        self.assertEqual(comparison["comparison"]["status"], "equal", comparison)
        self.evidence["transient"] = {"report": report, "observer_powered_ticks": [i for i, snapshot in enumerate(snapshots, 1) if snapshot[observer_key]["parameters"]["powered"] == "true"], "event_kinds": sorted(kinds), "mobile_piston_samples": len(moving), "diff_fields": len(diff)}

    async def regions_and_inventories(self, session):
        before = await self.call(session, "describe_task")
        region = await self.call(session, "read_region", {"min": point(1056, 79, 1056), "max": point(1087, 80, 1063)})
        self.assert_ok(region)
        self.assertEqual(region["world_time"], before["world_time"])
        self.assertEqual(region["simulation_ticks"], before["simulation_ticks"])
        self.assertEqual(region["preparation_ticks"], before["preparation_ticks"])
        rows = await self.pages(session, region["blocks"], 29)
        self.assertEqual(len(rows), 512)
        self.assertEqual(len({coordinates(row) for row in rows}), 512)
        self.assertTrue(all(row["block"] == "minecraft:air" for row in rows))
        for args in [{"artifact_id": region["blocks"]["artifact_id"], "offset": 513, "limit": 1}, {"artifact_id": "../../operations", "offset": 0, "limit": 1}, {"artifact_id": region["blocks"]["artifact_id"], "offset": 0, "limit": 257}]:
            rejected = await self.call(session, "read_artifact", args)
            self.assert_error(rejected, "validation")
        chest, hopper = point(1070, 80, 1060), point(1074, 80, 1060)
        await self.modify(session, [placement(chest, "minecraft:chest", inventory=[{"slot": 0, "item": "minecraft:diamond", "count": 7}, {"slot": 8, "item": "minecraft:redstone", "count": 13}]), placement(hopper, "minecraft:hopper", inventory=[{"slot": 0, "item": "minecraft:diamond", "count": 9}])], False)
        read = await self.call(session, "read_blocks", {"positions": [chest, hopper]})
        self.assert_ok(read)
        chest_record, hopper_record = read["blocks"]
        self.assertEqual(chest_record["inventory"][0]["count"], 7)
        items = chest_record["nbt"]["value"]["Items"]
        self.assertEqual(items["type"], 9)
        self.assertEqual(len(items["value"]), 2)
        self.assertEqual(items["value"][0]["value"]["Slot"], {"type": 1, "value": "0b"})
        self.assertEqual(hopper_record["runtime"]["last_tick_time_type"], "long")
        advanced = await self.call(session, "advance", {"ticks": 2, "trace": True})
        self.assert_ok(advanced)
        trace = await self.pages(session, advanced["trace"], 256)
        state1, state2 = await self.snapshot(session, trace[0]), await self.snapshot(session, trace[1])
        self.assertNotEqual(state1[coordinates(hopper)]["runtime"]["last_tick_time"], state2[coordinates(hopper)]["runtime"]["last_tick_time"])
        comparison = await self.call(session, "compare_traces", {"left": self.evidence["transient"]["report"]["trace"]["artifact_id"], "right": advanced["trace"]["artifact_id"]})
        self.assert_ok(comparison)
        self.assertEqual(comparison["comparison"]["status"], "different")
        self.assertEqual(comparison["comparison"]["first_tick"], 1)
        self.assertTrue(comparison["comparison"]["left_continuity"]["complete"])
        self.assertTrue(comparison["comparison"]["right_continuity"]["complete"])
        different_fields = await self.pages(session, comparison["comparison"]["first_fields"], 256)
        self.assertTrue(any(row["field"] == "$.world_time" for row in different_fields), different_fields)
        # Exact inventory changes are observable, never normalized away.
        modified = await self.modify(session, [placement(chest, "minecraft:chest", inventory=[{"slot": 0, "item": "minecraft:diamond", "count": 8}])], False)
        diff = await self.pages(session, modified["diff"], 256)
        self.assertTrue(any("1070,80,1060.inventory" in row["field"] for row in diff), diff)
        self.evidence["pagination_inventory"] = {"region": region, "region_count": len(rows), "chest": chest_record, "hopper": hopper_record, "hopper_times": [state1[coordinates(hopper)]["runtime"]["last_tick_time"], state2[coordinates(hopper)]["runtime"]["last_tick_time"]], "inventory_diff_count": len(diff)}

    async def partial_trace(self, session):
        self.assert_ok(await self.call(session, "__test_release_chunks", {"after_ticks": 2}))
        report = await self.call(session, "advance", {"ticks": 40, "trace": True})
        self.assert_error(report, "infrastructure", "chunks_unavailable")
        self.assertGreater(report["ticks_executed"], 0)
        self.assertLess(report["ticks_executed"], 40)
        self.assertFalse(report["continuity"]["complete"], report)
        self.assertEqual(report["continuity"]["observed"], report["ticks_executed"])
        ticks = await self.pages(session, report["trace"], 1)
        self.assertEqual(len(ticks), report["ticks_executed"])
        compare = await self.call(session, "compare_traces", {"left": report["trace"]["artifact_id"], "right": report["trace"]["artifact_id"]})
        self.assert_ok(compare)
        self.assertEqual(compare["comparison"]["status"], "incomplete")
        self.evidence["partial"] = report

    async def outside_coverage(self, session):
        self.assert_ok(await self.call(session, "__test_restore_chunks"))
        before = await self.call(session, "describe_task")
        fault = await self.call(session, "__test_outside_influence")
        self.assert_ok(fault)
        self.assertEqual(fault["world_time"], before["world_time"])
        self.assertEqual(fault["coverage"]["status"], "insufficient")
        self.assertFalse(fault["coverage"]["certification"])
        self.assertIn(point(1120, 80, 1120), fault["coverage"]["outside_prepared_chunks"])
        events = await self.pages(session, fault["intratick_events"], 256)
        self.assertTrue(any(event["kind"] == "block_tick_schedule_requested" and event["position"] == point(1120, 80, 1120) for event in events), events)
        traced = await self.call(session, "advance", {"ticks": 1, "trace": True})
        self.assert_ok(traced)
        self.assertFalse(traced["continuity"]["complete"])
        ticks = await self.pages(session, traced["trace"], 1)
        self.assertFalse(ticks[0]["complete"])
        self.evidence["outside_coverage"] = {"fault": fault, "trace": traced}


if __name__ == "__main__":
    unittest.main(defaultTest="ObservationRuntimeIntegration", verbosity=2)
