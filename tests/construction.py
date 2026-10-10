import asyncio
import unittest

from integration import BLOCK_POSITION, TASK_ID, StoneBenchRuntimeIntegration


def point(x, y, z):
    return {"x": x, "y": y, "z": z}


def coordinates(value):
    if isinstance(value, dict):
        return value["x"], value["y"], value["z"]
    return tuple(value)


def placement(position, block, parameters=None, inventory=None, **extra):
    item = {**position, "block": block}
    if parameters is not None:
        item["parameters"] = parameters
    if inventory is not None:
        item["inventory"] = inventory
    item.update(extra)
    return item


class ConstructionRuntimeIntegration(StoneBenchRuntimeIntegration):
    async def test_real_mcp_server_contract(self):
        await self._connect()
        try:
            session_a, session_b = self.sessions
            tool_names = set()
            for session in self.sessions:
                tool_names.update(tool.name for tool in (await session.list_tools()).tools)
            self.assertTrue(
                {
                    "start_attempt",
                    "describe_task",
                    "describe_blocks",
                    "read_blocks",
                    "modify_blocks",
                    "advance",
                    "__test_fail_next_lot",
                    "__test_default_wire",
                }.issubset(tool_names),
                tool_names,
            )

            start_a = await self.call(
                session_a,
                "start_attempt",
                {"task_id": TASK_ID, "budget_tokens": 1},
            )
            start_b = await self.call(
                session_b,
                "start_attempt",
                {"task_id": TASK_ID, "budget_tokens": None},
            )
            self.assert_ok(start_a)
            self.assert_ok(start_b)
            self.assertNotEqual(start_a["attempt_id"], start_b["attempt_id"])
            description_a = await self.wait_for_chunks(session_a, True)
            description_b = await self.wait_for_chunks(session_b, True)
            self.assert_description(description_a, known_budget=1)
            self.assert_description(description_b, known_budget=None)

            await self._assert_block_catalog(session_a)
            await self._assert_validation_is_atomic(session_a)
            await self._assert_batch_limits(session_a)
            await self._assert_configurable_settings(session_a)
            await self._assert_dust_and_inventory_batch(session_a)
            await self._assert_default_wire_placement(session_a)
            await self._assert_same_block_and_inventory_replacement(session_b)
            await self._assert_post_mutation_failure_and_recovery(session_b)
            await self._assert_chunk_expansion_without_simulation(session_b)
            await self._assert_comparator_notification_scope(session_b)
            await self._assert_powered_neighbor_batch(session_a)
            await self._assert_clock_and_readiness(session_a)
        finally:
            await self.stack.aclose()

    async def _assert_block_catalog(self, session):
        catalog = await self.call(session, "describe_blocks")
        self.assert_ok(catalog)
        entries = {item["id"]: item for item in catalog.get("catalog", [])}
        for block_id in (
            "minecraft:lever",
            "minecraft:repeater",
            "minecraft:hopper",
            "minecraft:chest",
            "minecraft:redstone_wire",
        ):
            self.assertIn(block_id, entries, catalog)
            self.assertIsInstance(entries[block_id].get("configurable"), dict, entries[block_id])
            self.assertIsInstance(entries[block_id].get("computed"), dict, entries[block_id])
            self.assertIn("inventory_slots", entries[block_id], entries[block_id])

        self.assertIn("powered", entries["minecraft:lever"]["computed"])
        self.assertNotIn("powered", entries["minecraft:lever"]["configurable"])
        self.assertIn("locked", entries["minecraft:repeater"]["computed"])
        self.assertIn("powered", entries["minecraft:repeater"]["computed"])
        self.assertIn("cooldown", entries["minecraft:hopper"]["computed"])
        self.assertGreater(entries["minecraft:chest"]["inventory_slots"], 0)

        repeater = entries["minecraft:repeater"]["configurable"]
        self.assertIn("north", repeater["facing"])
        self.assertIn("east", repeater["facing"])
        self.assertIn("1", [str(value) for value in repeater["delay"]])
        self.assertIn("4", [str(value) for value in repeater["delay"]])

    async def _read(self, session, positions):
        result = await self.call(session, "read_blocks", {"positions": positions})
        self.assert_ok(result)
        blocks = result.get("blocks")
        self.assertIsInstance(blocks, list, result)
        self.assertEqual(len(blocks), len(positions), result)
        return {coordinates(block): block for block in blocks}

    def assert_block_record(self, record, block_id):
        self.assertEqual(record.get("block"), block_id, record)
        self.assertIsInstance(record.get("state"), str, record)
        self.assertTrue(record["state"].startswith(f"Block{{{block_id}"), record)
        parameters = record.get("parameters")
        self.assertIsInstance(parameters, dict, record)
        self.assertTrue(all(isinstance(value, str) for value in parameters.values()), record)
        self.assertIsInstance(record.get("inventory"), list, record)

    async def _assert_air(self, session, positions):
        blocks = await self._read(session, positions)
        for position in positions:
            record = blocks[coordinates(position)]
            self.assert_block_record(record, "minecraft:air")
            self.assertEqual(record["state"], "Block{minecraft:air}", record)
            self.assertEqual(record["inventory"], [], record)

    def assert_no_effect(self, report, before):
        self.assertIs(report.get("mutated"), False, report)
        self.assertEqual(report.get("ticks_executed"), 0, report)
        for key in ("simulation_ticks", "preparation_ticks", "world_time"):
            self.assertEqual(report.get(key), before[key], report)

    async def _assert_rejected_without_effect(
        self, session, arguments, positions, *, kind="validation", code="invalid_arguments"
    ):
        before = await self.call(session, "describe_task")
        rejected = await self.call(session, "modify_blocks", arguments)
        self.assert_error(rejected, kind, code)
        self.assert_no_effect(rejected, before)
        await self._assert_air(session, positions)

    async def _assert_validation_is_atomic(self, session):
        first = point(1032, 80, 1024)
        second = point(1033, 80, 1024)
        await self._assert_rejected_without_effect(
            session,
            {
                "blocks": [
                    placement(first, "minecraft:stone"),
                    placement(second, "minecraft:repeater", {"locked": "true"}),
                ],
                "notify_neighbors": True,
            },
            [first, second],
        )

        target = point(1032, 80, 1024)
        invalids = [
            (
                placement(target, "minecraft:lever", {"powered": "true"}),
                "validation",
                "invalid_arguments",
            ),
            (
                placement(target, "minecraft:repeater", {"powered": "true"}),
                "validation",
                "invalid_arguments",
            ),
            (
                placement(target, "minecraft:repeater", {"locked": "true"}),
                "validation",
                "invalid_arguments",
            ),
            (
                placement(target, "minecraft:hopper", {"cooldown": "8"}),
                "validation",
                "invalid_arguments",
            ),
            (
                placement(
                    target,
                    "minecraft:chest",
                    nbt={"Items": [{"Slot": 0, "id": "minecraft:diamond", "Count": 64}]},
                ),
                "validation",
                "invalid_arguments",
            ),
            (
                placement(
                    target,
                    "minecraft:chest",
                    inventory=[{"slot": 0, "item": "minecraft:diamond", "count": 65}],
                ),
                "validation",
                "invalid_arguments",
            ),
            (
                placement(
                    target,
                    "minecraft:chest",
                    inventory=[{"slot": 0, "item": "minecraft:stone_that_does_not_exist", "count": 1}],
                ),
                "validation",
                "invalid_arguments",
            ),
            (
                placement(
                    target,
                    "minecraft:chest",
                    inventory=[{"slot": 27, "item": "minecraft:diamond", "count": 1}],
                ),
                "validation",
                "invalid_arguments",
            ),
            (
                placement(
                    target,
                    "minecraft:chest",
                    inventory=[{"slot": 0, "item": "minecraft:diamond", "count": 0}],
                ),
                "validation",
                "invalid_arguments",
            ),
            (
                placement(target, "minecraft:command_block"),
                "unsupported",
                "unsupported_component",
            ),
        ]
        invalids.extend([
            (placement(target, "minecraft:sticky_piston", {"extended": "true"}), "validation", "invalid_arguments"),
            (placement(target, "minecraft:sticky_piston", {"piston_progress": "0.5"}), "validation", "invalid_arguments"),
            (placement(target, "minecraft:hopper", {"last_tick_time": "100"}), "validation", "invalid_arguments"),
            (placement(target, "minecraft:hopper", scheduled_ticks=[]), "validation", "invalid_arguments"),
        ])
        for block, kind, code in invalids:
            await self._assert_rejected_without_effect(
                session,
                {"blocks": [block], "notify_neighbors": True},
                [target],
                kind=kind,
                code=code,
            )

        await self._assert_rejected_without_effect(
            session,
            {"blocks": [placement(target, "minecraft:stone")]},
            [target],
        )
        await self._assert_rejected_without_effect(
            session,
            {
                "blocks": [
                    placement(target, "minecraft:stone"),
                    placement(target, "minecraft:dirt"),
                ],
                "notify_neighbors": True,
            },
            [target],
        )

    async def _assert_batch_limits(self, session):
        too_many = [
            placement(
                point(1024 + index % 16, 110 + index // 256, 1024 + (index // 16) % 16),
                "minecraft:stone",
            )
            for index in range(257)
        ]
        await self._assert_rejected_without_effect(
            session,
            {"blocks": too_many, "notify_neighbors": False},
            [point(1024, 110, 1024), point(1024, 111, 1024)],
        )

        before = await self.call(session, "describe_task")
        valid_limit = [
            placement(point(1024 + x, 100, 1024 + z), "minecraft:stone")
            for x in range(16)
            for z in range(16)
        ]
        result = await self.call(
            session,
            "modify_blocks",
            {"blocks": valid_limit, "notify_neighbors": False},
        )
        self.assert_ok(result)
        self.assertEqual(result.get("placements_applied"), 256, result)
        self.assertEqual(result.get("notification_order"), [], result)
        self.assertEqual(result.get("events"), [], result)
        self.assertIs(result.get("frozen"), True, result)
        self.assertEqual(result.get("ticks_executed"), 0, result)
        self.assertEqual(result.get("simulation_ticks"), before["simulation_ticks"], result)
        self.assertEqual(result.get("preparation_ticks"), before["preparation_ticks"], result)
        self.assertEqual(result.get("world_time"), before["world_time"], result)
        sample = await self._read(
            session,
            [point(1024, 100, 1024), point(1039, 100, 1039)],
        )
        self.assert_block_record(sample[(1024, 100, 1024)], "minecraft:stone")
        self.assert_block_record(sample[(1039, 100, 1039)], "minecraft:stone")

    def assert_callback_order(self, report, submitted):
        expected = [coordinates(block) for block in submitted]
        self.assertEqual(
            [coordinates(position) for position in report.get("notification_order", [])],
            expected,
            report,
        )
        events = report.get("events")
        self.assertIsInstance(events, list, report)
        self.assertTrue(events, report)
        self.assertTrue(all(event.get("geometry_complete") is True for event in events), events)
        self.assertTrue(all(event.get("inventories_complete") is True for event in events), events)
        self.assertTrue(all(event.get("parameters_complete") is True for event in events), events)

        indexes = [event.get("root_index") for event in events]
        self.assertTrue(all(isinstance(index, int) for index in indexes), events)
        self.assertNotIn(-1, indexes, events)
        self.assertEqual(indexes, sorted(indexes), events)

        notification_kinds = {
            "notify_neighbors",
            "notify_neighbors_always",
            "notify_neighbors_except",
        }
        roots = []
        for event in events:
            index = event["root_index"]
            if (
                event.get("kind") in notification_kinds
                and 0 <= index < len(expected)
                and coordinates(event["position"]) == expected[index]
                and index not in roots
            ):
                roots.append(index)
        self.assertEqual(roots, list(range(len(expected))), events)

    async def _assert_configurable_settings(self, session):
        lever = point(1030, 81, 1026)
        repeater = point(1029, 80, 1026)
        comparator = point(1031, 80, 1026)
        hopper = point(1033, 80, 1026)
        submitted = [
            placement(lever, "minecraft:lever", {"face": "wall", "facing": "north"}),
            placement(repeater, "minecraft:repeater", {"delay": "4", "facing": "east"}),
            placement(comparator, "minecraft:comparator", {"mode": "subtract", "facing": "north"}),
            placement(hopper, "minecraft:hopper", {"facing": "down"}, [{"slot": 0, "item": "minecraft:diamond", "count": 2}]),
            placement(point(1030, 81, 1027), "minecraft:stone"),
            placement(point(1029, 79, 1026), "minecraft:stone"),
            placement(point(1031, 79, 1026), "minecraft:stone"),
        ]
        before = await self.call(session, "describe_task")
        result = await self.call(session, "modify_blocks", {"blocks": submitted, "notify_neighbors": True})
        self.assert_ok(result)
        self.assert_callback_order(result, submitted)
        self.assertEqual(result["world_time"], before["world_time"], result)
        records = await self._read(session, [lever, repeater, comparator, hopper])
        for position, parameters in (
            (lever, {"face": "wall", "facing": "north"}),
            (repeater, {"delay": "4", "facing": "east"}),
            (comparator, {"mode": "subtract", "facing": "north"}),
            (hopper, {"facing": "down"}),
        ):
            for key, value in parameters.items():
                self.assertEqual(records[coordinates(position)]["parameters"][key], value, records)
        self.assertEqual(records[coordinates(hopper)]["inventory"], [{"slot": 0, "item": "minecraft:diamond", "count": 2}], records)
    async def _assert_dust_and_inventory_batch(self, session):
        dust_left = point(1024, 80, 1024)
        dust_center = point(1025, 80, 1024)
        dust_right = point(1026, 80, 1024)
        chest_position = point(1028, 80, 1024)
        second_chest_position = point(1030, 80, 1024)
        support_positions = [
            point(1024, 79, 1024),
            point(1025, 79, 1024),
            point(1026, 79, 1024),
            point(1028, 79, 1024),
            point(1030, 79, 1024),
        ]
        submitted = [
            placement(dust_right, "minecraft:redstone_wire"),
            placement(
                chest_position,
                "minecraft:chest",
                inventory=[{"slot": 0, "item": "minecraft:diamond", "count": 7}],
            ),
            placement(dust_left, "minecraft:redstone_wire"),
            placement(
                second_chest_position,
                "minecraft:chest",
                inventory=[{"slot": 3, "item": "minecraft:emerald", "count": 4}],
            ),
            placement(dust_center, "minecraft:redstone_wire"),
            *[placement(position, "minecraft:stone") for position in support_positions],
        ]
        before = await self.call(session, "describe_task")
        result = await self.call(
            session,
            "modify_blocks",
            {"blocks": submitted, "notify_neighbors": True},
        )
        self.assert_ok(result)
        self.assertEqual(result.get("placements_applied"), len(submitted), result)
        self.assert_callback_order(result, submitted)
        self.assertGreater(result.get("deferred_comparator_updates", 0), 0, result)
        comparator_events = [
            event for event in result["events"] if event.get("kind") == "update_comparators"
        ]
        self.assertTrue(comparator_events, result)
        self.assertTrue(comparator_events[0].get("inventories_complete"), comparator_events[0])
        self.assertIs(result.get("frozen"), True, result)
        self.assertEqual(result.get("ticks_executed"), 0, result)
        self.assertEqual(result.get("simulation_ticks"), before["simulation_ticks"], result)
        self.assertEqual(result.get("preparation_ticks"), before["preparation_ticks"], result)
        self.assertEqual(result.get("world_time"), before["world_time"], result)

        records = await self._read(
            session,
            [
                dust_left,
                dust_center,
                dust_right,
                chest_position,
                second_chest_position,
                *support_positions,
            ],
        )
        for position in (dust_left, dust_center, dust_right):
            self.assert_block_record(records[coordinates(position)], "minecraft:redstone_wire")
        left = records[coordinates(dust_left)]["parameters"]
        center = records[coordinates(dust_center)]["parameters"]
        right = records[coordinates(dust_right)]["parameters"]
        self.assertEqual(left.get("east"), "side", left)
        self.assertEqual(left.get("west"), "side", left)
        self.assertEqual(left.get("north"), "none", left)
        self.assertEqual(left.get("south"), "none", left)
        self.assertEqual(center.get("east"), "side", center)
        self.assertEqual(center.get("west"), "side", center)
        self.assertEqual(center.get("north"), "none", center)
        self.assertEqual(center.get("south"), "none", center)
        self.assertEqual(right.get("east"), "side", right)
        self.assertEqual(right.get("west"), "side", right)
        self.assertEqual(right.get("north"), "none", right)
        self.assertEqual(right.get("south"), "none", right)

        chest = records[coordinates(chest_position)]
        self.assert_block_record(chest, "minecraft:chest")
        self.assertEqual(
            chest["inventory"],
            [{"slot": 0, "item": "minecraft:diamond", "count": 7}],
            chest,
        )
        second_chest = records[coordinates(second_chest_position)]
        self.assert_block_record(second_chest, "minecraft:chest")
        self.assertEqual(
            second_chest["inventory"],
            [{"slot": 3, "item": "minecraft:emerald", "count": 4}],
            second_chest,
        )
        for position in support_positions:
            self.assert_block_record(records[coordinates(position)], "minecraft:stone")

    async def _assert_default_wire_placement(self, session):
        wire = point(1036, 80, 1030)
        forced = await self.call(session, "__test_default_wire")
        self.assert_ok(forced)
        self.assert_block_record(forced.get("block", {}), "minecraft:redstone_wire")
        default_parameters = forced["block"]["parameters"]
        for direction in ("north", "south", "east", "west"):
            self.assertEqual(default_parameters.get(direction), "none", forced)

        before_setup = await self.call(session, "describe_task")
        supports_and_piston = [
            placement(point(1036, 79, 1030), "minecraft:stone"),
            placement(
                point(1037, 80, 1030),
                "minecraft:sticky_piston",
                {"facing": "east"},
            ),
        ]
        setup = await self.call(
            session,
            "modify_blocks",
            {"blocks": supports_and_piston, "notify_neighbors": False},
        )
        self.assert_ok(setup)
        self.assertEqual(setup.get("events"), [], setup)
        self.assertEqual(setup.get("notification_order"), [], setup)
        self.assertEqual(setup.get("simulation_ticks"), before_setup["simulation_ticks"], setup)
        self.assertEqual(setup.get("preparation_ticks"), before_setup["preparation_ticks"], setup)
        self.assertEqual(setup.get("world_time"), before_setup["world_time"], setup)

        still_dot = await self._read(session, [wire])
        for direction in ("north", "south", "east", "west"):
            self.assertEqual(
                still_dot[coordinates(wire)]["parameters"].get(direction),
                "none",
                still_dot,
            )

        repair = [placement(wire, "minecraft:redstone_wire")]
        repaired = await self.call(
            session,
            "modify_blocks",
            {"blocks": repair, "notify_neighbors": False},
        )
        self.assert_ok(repaired)
        self.assertEqual(repaired.get("events"), [], repaired)
        self.assertEqual(repaired.get("notification_order"), [], repaired)
        repaired_record = (await self._read(session, [wire]))[coordinates(wire)]
        self.assert_block_record(repaired_record, "minecraft:redstone_wire")
        repaired_parameters = repaired_record["parameters"]
        self.assertEqual(repaired_parameters.get("east"), "side", repaired_record)
        self.assertEqual(repaired_parameters.get("west"), "side", repaired_record)
        self.assertFalse(
            all(repaired_parameters.get(direction) == "none" for direction in ("north", "south", "east", "west")),
            repaired_record,
        )

        notified = await self.call(
            session,
            "modify_blocks",
            {"blocks": repair, "notify_neighbors": True},
        )
        self.assert_ok(notified)
        self.assert_callback_order(notified, repair)
        notified_record = (await self._read(session, [wire]))[coordinates(wire)]
        self.assertEqual(notified_record["parameters"].get("east"), "side", notified_record)
        self.assertEqual(notified_record["parameters"].get("west"), "side", notified_record)
    async def _assert_same_block_and_inventory_replacement(self, session):
        await self.assert_air_at_fixture(session)
        support_positions = [point(1024, 79, 1024), point(1025, 79, 1024)]
        before = await self.call(session, "describe_task")
        support_result = await self.call(
            session,
            "modify_blocks",
            {
                "blocks": [
                    placement(position, "minecraft:stone")
                    for position in support_positions
                ],
                "notify_neighbors": False,
            },
        )
        self.assert_ok(support_result)
        self.assertEqual(support_result.get("events"), [], support_result)
        self.assertEqual(support_result.get("simulation_ticks"), before["simulation_ticks"], support_result)

        repeater_position = BLOCK_POSITION.copy()
        chest_position = point(1025, 80, 1024)
        initial = [
            placement(
                repeater_position,
                "minecraft:repeater",
                {"facing": "north", "delay": "1"},
            ),
            placement(
                chest_position,
                "minecraft:chest",
                inventory=[{"slot": 0, "item": "minecraft:diamond", "count": 7}],
            ),
        ]
        result = await self.call(
            session,
            "modify_blocks",
            {"blocks": initial, "notify_neighbors": False},
        )
        self.assert_ok(result)
        self.assertEqual(result.get("notification_order"), [], result)
        self.assertEqual(result.get("events"), [], result)
        self.assertGreater(result.get("deferred_comparator_updates", 0), 0, result)
        initial_records = await self._read(session, [repeater_position, chest_position])
        self.assert_block_record(initial_records[coordinates(repeater_position)], "minecraft:repeater")
        self.assertEqual(
            initial_records[coordinates(repeater_position)]["parameters"].get("facing"),
            "north",
            initial_records[coordinates(repeater_position)],
        )
        self.assertEqual(
            initial_records[coordinates(chest_position)]["inventory"],
            [{"slot": 0, "item": "minecraft:diamond", "count": 7}],
        )

        updated = [
            placement(
                repeater_position,
                "minecraft:repeater",
                {"facing": "east", "delay": "4"},
            ),
            placement(
                chest_position,
                "minecraft:chest",
                inventory=[{"slot": 1, "item": "minecraft:emerald", "count": 3}],
            ),
        ]
        before_changed = await self.call(session, "describe_task")
        changed = await self.call(
            session,
            "modify_blocks",
            {"blocks": updated, "notify_neighbors": True},
        )
        self.assert_ok(changed)
        self.assert_callback_order(changed, updated)
        self.assertTrue(any(
            event["kind"] == "on_block_added"
            and coordinates(event["position"]) == coordinates(repeater_position)
            for event in changed["events"]
        ), changed["events"])
        self.assertEqual(changed.get("simulation_ticks"), before_changed["simulation_ticks"], changed)
        self.assertEqual(changed.get("preparation_ticks"), before_changed["preparation_ticks"], changed)
        self.assertEqual(changed.get("world_time"), before_changed["world_time"], changed)
        self.assertGreater(changed.get("deferred_comparator_updates", 0), 0, changed)
        updated_records = await self._read(session, [repeater_position, chest_position])
        repeater = updated_records[coordinates(repeater_position)]
        self.assert_block_record(repeater, "minecraft:repeater")
        self.assertEqual(repeater["parameters"].get("facing"), "east", repeater)
        self.assertEqual(repeater["parameters"].get("delay"), "4", repeater)
        chest = updated_records[coordinates(chest_position)]
        self.assert_block_record(chest, "minecraft:chest")
        self.assertEqual(
            chest["inventory"],
            [{"slot": 1, "item": "minecraft:emerald", "count": 3}],
            chest,
        )

        replaced = await self.call(
            session,
            "modify_blocks",
            {
                "blocks": [placement(chest_position, "minecraft:stone")],
                "notify_neighbors": False,
            },
        )
        self.assert_ok(replaced)
        self.assertEqual(replaced.get("events"), [], replaced)
        replacement = await self._read(session, [chest_position])
        self.assert_block_record(replacement[coordinates(chest_position)], "minecraft:stone")
        self.assertEqual(replacement[coordinates(chest_position)]["inventory"], [])

        deleted = await self.call(
            session,
            "modify_blocks",
            {
                "blocks": [placement(chest_position, "minecraft:air")],
                "notify_neighbors": False,
            },
        )
        self.assert_ok(deleted)
        self.assertEqual(deleted.get("events"), [], deleted)
        self.assertEqual(deleted.get("notification_order"), [], deleted)
        empty = await self._read(session, [chest_position])
        self.assert_block_record(empty[coordinates(chest_position)], "minecraft:air")
        self.assertEqual(empty[coordinates(chest_position)]["inventory"], [])

    async def _assert_post_mutation_failure_and_recovery(self, session):
        target = point(1026, 80, 1024)
        armed = await self.call(session, "__test_fail_next_lot")
        self.assert_ok(armed)
        before = await self.call(session, "describe_task")
        failure = await self.call(
            session,
            "modify_blocks",
            {
                "blocks": [
                    placement(
                        target,
                        "minecraft:chest",
                        inventory=[{"slot": 0, "item": "minecraft:emerald", "count": 5}],
                    )
                ],
                "notify_neighbors": True,
            },
        )
        self.assert_error(failure, "infrastructure", "server_error")
        self.assertIn(
            "Test fault after all geometry/inventories, before callbacks",
            failure.get("error", {}).get("message", ""),
            failure,
        )
        self.assertIs(failure.get("mutated"), True, failure)
        self.assertIs(failure.get("frozen"), True, failure)
        self.assertEqual(failure.get("ticks_executed"), 0, failure)
        self.assertEqual(failure.get("simulation_ticks"), before["simulation_ticks"], failure)
        self.assertEqual(failure.get("preparation_ticks"), before["preparation_ticks"], failure)
        self.assertEqual(failure.get("world_time"), before["world_time"], failure)

        self.assertIsInstance(failure.get("recovery"), str, failure)
        self.assertTrue(failure["recovery"], failure)

        actual = failure.get("blocks")
        self.assertIsInstance(actual, list, failure)
        self.assertEqual(len(actual), 1, failure)
        self.assert_block_record(actual[0], "minecraft:chest")
        self.assertEqual(
            actual[0]["inventory"],
            [{"slot": 0, "item": "minecraft:emerald", "count": 5}],
            actual[0],
        )

        before_repair = await self.call(session, "describe_task")
        repaired = await self.call(
            session,
            "modify_blocks",
            {
                "blocks": [placement(target, "minecraft:stone")],
                "notify_neighbors": False,
            },
        )
        self.assert_ok(repaired)
        self.assertEqual(repaired.get("events"), [], repaired)
        self.assertEqual(repaired.get("notification_order"), [], repaired)
        self.assertEqual(repaired.get("simulation_ticks"), before_repair["simulation_ticks"], repaired)
        self.assertEqual(repaired.get("preparation_ticks"), before_repair["preparation_ticks"], repaired)
        self.assertEqual(repaired.get("world_time"), before_repair["world_time"], repaired)
        self.assertIs(repaired.get("frozen"), True, repaired)
        actual_repair = await self._read(session, [target])
        self.assert_block_record(actual_repair[coordinates(target)], "minecraft:stone")
        self.assertEqual(actual_repair[coordinates(target)]["inventory"], [])
    async def _assert_chunk_expansion_without_simulation(self, session):
        positions = [point(1215, 80, 1216), point(1216, 80, 1216)]
        before = await self.call(session, "describe_task")
        unprepared = await self.call(
            session,
            "read_blocks",
            {"positions": [positions[-1]]},
        )
        self.assert_error(unprepared, "validation", "invalid_arguments")
        self.assertTrue(unprepared["error"]["message"].startswith("scope_unprepared"), unprepared)
        self.assert_no_effect(unprepared, before)

        result = await self.call(
            session,
            "modify_blocks",
            {
                "blocks": [
                    placement(positions[0], "minecraft:stone"),
                    placement(positions[1], "minecraft:stone"),
                ],
                "notify_neighbors": False,
            },
        )
        self.assert_ok(result)
        self.assertEqual(result.get("placements_applied"), 2, result)
        self.assertEqual(result.get("notification_order"), [], result)
        self.assertEqual(result.get("events"), [], result)
        self.assertEqual(result.get("simulation_ticks"), before["simulation_ticks"], result)
        self.assertEqual(result.get("preparation_ticks"), before["preparation_ticks"], result)
        self.assertEqual(result.get("world_time"), before["world_time"], result)
        self.assertEqual(result.get("ticks_executed"), 0, result)
        self.assertIs(result.get("frozen"), True, result)
        records = await self._read(session, positions)
        for position in positions:
            self.assert_block_record(records[coordinates(position)], "minecraft:stone")

    async def _assert_comparator_notification_scope(self, session):
        comparator = point(1032, 80, 1037)
        chest = point(1033, 80, 1037)
        bridge = point(1032, 80, 1036)
        unrelated = point(1032, 80, 1035)
        setup = [
            placement(comparator, "minecraft:comparator", {"facing": "east"}),
            placement(chest, "minecraft:chest", inventory=[{"slot": 0, "item": "minecraft:stone", "count": 64}]),
            placement(point(1032, 79, 1037), "minecraft:stone"),
            placement(bridge, "minecraft:stone"),
        ]
        result = await self.call(session, "modify_blocks", {"blocks": setup, "notify_neighbors": True})
        self.assert_ok(result)
        self.assert_ok(await self.call(session, "advance", {"ticks": 4}))
        powered = await self._read(session, [comparator])
        self.assertEqual(powered[coordinates(comparator)]["parameters"]["powered"], "true", powered)
        silent = await self.call(session, "modify_blocks", {"blocks": [placement(chest, "minecraft:chest", inventory=[])], "notify_neighbors": False})
        self.assert_ok(silent)
        self.assertEqual(silent["events"], [], silent)
        self.assert_ok(await self.call(session, "advance", {"ticks": 4}))
        stale = await self._read(session, [comparator])
        self.assertEqual(stale[coordinates(comparator)]["parameters"]["powered"], "true", stale)
        stone = await self.call(session, "modify_blocks", {"blocks": [placement(unrelated, "minecraft:stone")], "notify_neighbors": True})
        self.assert_ok(stone)
        self.assert_ok(await self.call(session, "advance", {"ticks": 4}))
        after_stone = await self._read(session, [comparator])
        self.assertEqual(after_stone[coordinates(comparator)]["parameters"]["powered"], "true", after_stone)
        self.assertFalse(any(event["kind"] == "update_comparators" for event in stone["events"]), stone)
        notified = await self.call(session, "modify_blocks", {"blocks": [placement(chest, "minecraft:chest", inventory=[])], "notify_neighbors": True})
        self.assert_ok(notified)
        self.assertTrue(any(event["kind"] == "update_comparators" for event in notified["events"]), notified)
        self.assert_ok(await self.call(session, "advance", {"ticks": 4}))
        refreshed = await self._read(session, [comparator])
        self.assertEqual(refreshed[coordinates(comparator)]["parameters"]["powered"], "false", refreshed)

    async def _assert_powered_neighbor_batch(self, session):
        piston = point(1032, 80, 1034)
        front = point(1033, 80, 1034)
        destination = point(1034, 80, 1034)
        source = point(1031, 80, 1034)
        submitted = [
            placement(piston, "minecraft:sticky_piston", {"facing": "east"}),
            placement(front, "minecraft:stone"),
            placement(source, "minecraft:redstone_block"),
        ]
        before = await self.call(session, "describe_task")
        result = await self.call(session, "modify_blocks", {"blocks": submitted, "notify_neighbors": True})
        self.assert_ok(result)
        self.assert_callback_order(result, submitted)
        self.assertEqual(result["world_time"], before["world_time"], result)
        self.assertEqual(result["simulation_ticks"], before["simulation_ticks"], result)
        frozen = await self._read(session, [piston, front, destination])
        self.assertEqual(frozen[coordinates(piston)]["parameters"]["extended"], "false", frozen)
        advanced = await self.call(session, "advance", {"ticks": 4})
        self.assert_ok(advanced)
        self.assertEqual(advanced["ticks_executed"], 4, advanced)
        moved = await self._read(session, [piston, front, destination])
        self.assertEqual(moved[coordinates(piston)]["parameters"]["extended"], "true", moved)
        self.assert_block_record(moved[coordinates(front)], "minecraft:piston_head")
        self.assert_block_record(moved[coordinates(destination)], "minecraft:stone")
    async def _assert_clock_and_readiness(self, session):
        before_invalid = await self.call(session, "describe_task")
        for ticks in (0, 6001):
            rejected = await self.call(session, "advance", {"ticks": ticks})
            self.assert_error(rejected, "validation", "invalid_arguments")
            self.assert_no_effect(rejected, before_invalid)

        one_tick = await self.call(session, "advance", {"ticks": 1})
        self.assert_ok(one_tick)
        self.assertEqual(one_tick.get("ticks_executed"), 1, one_tick)
        self.assertIs(one_tick.get("frozen"), True, one_tick)
        self.assertEqual(one_tick.get("simulation_ticks"), before_invalid["simulation_ticks"] + 1, one_tick)
        self.assertEqual(one_tick.get("world_time"), before_invalid["world_time"] + 1, one_tick)
        self.assertEqual(one_tick.get("preparation_ticks"), before_invalid["preparation_ticks"], one_tick)

        after_advance = await self.call(session, "describe_task")
        await asyncio.sleep(1.0)
        after_freeze = await self.call(session, "describe_task")
        for key in ("simulation_ticks", "preparation_ticks", "world_time"):
            self.assertEqual(after_freeze.get(key), after_advance.get(key), after_freeze)
        self.assertIs(after_freeze.get("frozen"), True, after_freeze)

        before_concurrent = after_freeze
        concurrent = await asyncio.gather(
            self.call(session, "advance", {"ticks": 1}),
            self.call(session, "advance", {"ticks": 20}),
        )
        for result, expected in zip(concurrent, (1, 20)):
            self.assert_ok(result)
            self.assertEqual(result.get("ticks_executed"), expected, result)
            self.assertIs(result.get("frozen"), True, result)
        after_concurrent = await self.call(session, "describe_task")
        self.assertEqual(
            after_concurrent.get("simulation_ticks"),
            before_concurrent["simulation_ticks"] + 21,
            after_concurrent,
        )
        self.assertEqual(
            after_concurrent.get("world_time"),
            before_concurrent["world_time"] + 21,
            after_concurrent,
        )
        self.assertEqual(
            after_concurrent.get("preparation_ticks"),
            before_concurrent["preparation_ticks"],
            after_concurrent,
        )

        before_loss = after_concurrent
        released = await self.call(
            session,
            "__test_release_chunks",
            {"after_ticks": 1},
        )
        self.assert_ok(released)
        interrupted = await self.call(session, "advance", {"ticks": 20})
        self.assert_error(interrupted, "infrastructure", "chunks_unavailable")
        self.assertEqual(interrupted.get("ticks_executed"), 1, interrupted)
        self.assertEqual(
            interrupted.get("simulation_ticks"),
            before_loss["simulation_ticks"] + 1,
            interrupted,
        )
        self.assertEqual(interrupted.get("world_time"), before_loss["world_time"] + 1, interrupted)
        self.assertEqual(
            interrupted.get("preparation_ticks"),
            before_loss["preparation_ticks"],
            interrupted,
        )
        self.assertIs(interrupted.get("frozen"), True, interrupted)

        await asyncio.sleep(1.0)
        after_loss_freeze = await self.call(session, "describe_task")
        for key in ("simulation_ticks", "preparation_ticks", "world_time"):
            self.assertEqual(after_loss_freeze.get(key), interrupted.get(key), after_loss_freeze)
        self.assertIs(after_loss_freeze.get("frozen"), True, after_loss_freeze)

        restored = await self.call(session, "__test_restore_chunks")
        self.assert_ok(restored)
        self.assertEqual(restored.get("ticks_executed"), 0, restored)
        self.assertGreater(restored.get("preparation_ticks"), interrupted["preparation_ticks"], restored)
        self.assertEqual(
            restored.get("world_time") - interrupted["world_time"],
            restored.get("preparation_ticks") - interrupted["preparation_ticks"],
            restored,
        )
        self.assertEqual(restored.get("simulation_ticks"), interrupted["simulation_ticks"], restored)
        self.assertIs(restored.get("frozen"), True, restored)
        ready = await self.call(session, "describe_task")
        self.assertIs(ready.get("chunks_ready"), True, ready)
        self.assertEqual(ready.get("simulation_ticks"), restored["simulation_ticks"], ready)
        self.assertEqual(ready.get("world_time"), restored["world_time"], ready)


if __name__ == "__main__":
    unittest.main(defaultTest="ConstructionRuntimeIntegration", verbosity=2)
