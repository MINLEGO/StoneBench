import asyncio
import unittest

from integration import BLOCK_POSITION, TASK_ID, StoneBenchRuntimeIntegration


EXPECTED_CATALOG = [
    "minecraft:air",
    "minecraft:quartz_block",
    "minecraft:white_wool",
    "minecraft:orange_wool",
    "minecraft:magenta_wool",
    "minecraft:light_blue_wool",
    "minecraft:yellow_wool",
    "minecraft:lime_wool",
    "minecraft:pink_wool",
    "minecraft:gray_wool",
    "minecraft:light_gray_wool",
    "minecraft:cyan_wool",
    "minecraft:purple_wool",
    "minecraft:blue_wool",
    "minecraft:brown_wool",
    "minecraft:green_wool",
    "minecraft:red_wool",
    "minecraft:black_wool",
    "minecraft:obsidian",
    "minecraft:honey_block",
    "minecraft:slime_block",
    "minecraft:sand",
    "minecraft:smooth_stone_slab",
    "minecraft:stone_stairs",
    "minecraft:glass",
    "minecraft:glass_pane",
    "minecraft:water",
    "minecraft:scaffolding",
    "minecraft:stone_brick_wall",
    "minecraft:player_head",
    "minecraft:beacon",
    "minecraft:oak_log",
    "minecraft:oak_leaves",
    "minecraft:piston",
    "minecraft:sticky_piston",
    "minecraft:observer",
    "minecraft:dispenser",
    "minecraft:dropper",
    "minecraft:repeater",
    "minecraft:comparator",
    "minecraft:redstone_wire",
    "minecraft:redstone_torch",
    "minecraft:redstone_wall_torch",
    "minecraft:stone_button",
    "minecraft:oak_button",
    "minecraft:lever",
    "minecraft:stone_pressure_plate",
    "minecraft:oak_pressure_plate",
    "minecraft:light_weighted_pressure_plate",
    "minecraft:heavy_weighted_pressure_plate",
    "minecraft:redstone_block",
    "minecraft:redstone_lamp",
    "minecraft:target",
    "minecraft:note_block",
    "minecraft:hopper",
    "minecraft:chest",
    "minecraft:trapped_chest",
    "minecraft:barrel",
    "minecraft:composter",
    "minecraft:iron_trapdoor",
    "minecraft:oak_trapdoor",
    "minecraft:iron_door",
    "minecraft:oak_door",
    "minecraft:oak_fence_gate",
    "minecraft:furnace",
    "minecraft:shulker_box",
    "minecraft:rail",
    "minecraft:powered_rail",
    "minecraft:detector_rail",
    "minecraft:activator_rail",
    "minecraft:waxed_copper_grate",
]


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
            await self._assert_new_block_construction(session_b)
            await self._assert_clock_and_readiness(session_a)
        finally:
            await self.stack.aclose()

    async def _assert_block_catalog(self, session):
        catalog = await self.call(session, "describe_blocks")
        self.assert_ok(catalog)
        # The global list carries ids only, in the published order, with no detail.
        self.assertEqual(catalog["catalog"], EXPECTED_CATALOG, catalog)
        self.assertEqual(len(EXPECTED_CATALOG), 71)
        self.assertEqual(len(set(catalog["catalog"])), 71, catalog)
        self.assertNotIn("inventory_contract", catalog)
        self.assertTrue(all(isinstance(block, str) for block in catalog["catalog"]), catalog)

        lever = await self._describe_block(session, "minecraft:lever")
        self.assertIn("powered", lever["computed"])
        self.assertNotIn("powered", lever["configurable"])
        repeater = await self._describe_block(session, "minecraft:repeater")
        self.assertIn("locked", repeater["computed"])
        self.assertIn("powered", repeater["computed"])
        self.assertIn("north", repeater["configurable"]["facing"])
        self.assertIn("east", repeater["configurable"]["facing"])
        self.assertIn("1", [str(value) for value in repeater["configurable"]["delay"]])
        self.assertIn("4", [str(value) for value in repeater["configurable"]["delay"]])
        hopper = await self._describe_block(session, "minecraft:hopper")
        self.assertIn("cooldown", hopper["computed"])
        self.assertEqual(hopper["inventory_slots"], 5, hopper)
        self.assertEqual((await self._describe_block(session, "minecraft:chest"))["inventory_slots"], 27)
        self.assertEqual((await self._describe_block(session, "minecraft:furnace"))["inventory_slots"], 3)
        for block_id in ("minecraft:composter", "minecraft:beacon", "minecraft:player_head", "minecraft:redstone_wire"):
            self.assertEqual((await self._describe_block(session, block_id))["inventory_slots"], 0, block_id)
        self.assertIn("level", (await self._describe_block(session, "minecraft:composter"))["configurable"])

        # Water-bearing blocks publish waterlogged as configurable; no block keeps it computed.
        waterlogged = []
        for block_id in EXPECTED_CATALOG:
            detail = await self._describe_block(session, block_id)
            self.assertNotIn("waterlogged", detail["computed"], detail)
            if "waterlogged" in detail["configurable"]:
                waterlogged.append(block_id)
                self.assertEqual(sorted(detail["configurable"]["waterlogged"]), ["false", "true"], detail)
        for block_id in ("minecraft:oak_trapdoor", "minecraft:iron_trapdoor", "minecraft:waxed_copper_grate", "minecraft:glass_pane", "minecraft:chest"):
            self.assertIn(block_id, waterlogged)
        for block_id in ("minecraft:oak_log", "minecraft:lever", "minecraft:hopper", "minecraft:oak_door"):
            self.assertNotIn(block_id, waterlogged)

        # Placement settings of the new blocks; electrical/derived states stay computed.
        oak_door = await self._describe_block(session, "minecraft:oak_door")
        self.assertTrue({"facing", "hinge", "open"} <= set(oak_door["configurable"]), oak_door)
        self.assertIn("half", oak_door["computed"])
        self.assertIn("powered", oak_door["computed"])
        self.assertNotIn("open", (await self._describe_block(session, "minecraft:iron_door"))["configurable"])
        self.assertIn("open", (await self._describe_block(session, "minecraft:oak_trapdoor"))["configurable"])
        self.assertIn("open", (await self._describe_block(session, "minecraft:oak_fence_gate"))["configurable"])
        self.assertIn("level", (await self._describe_block(session, "minecraft:water"))["computed"])

        # Unknown or withdrawn ids never fall back to the full catalogue.
        for removed in ("minecraft:stone", "minecraft:spruce_button", "minecraft:command_block", "stone"):
            rejected = await self.call(session, "describe_block", {"id": removed})
            self.assert_error(rejected, "unsupported", "unsupported_component")
            self.assertNotIn("catalog", rejected, rejected)
        self.assert_error(await self.call(session, "describe_block", {}), "validation", "invalid_arguments")
        self.assert_error(
            await self.call(session, "describe_block", {"id": "minecraft:lever", "extra": 1}),
            "validation",
            "invalid_arguments",
        )

    async def _describe_block(self, session, block_id):
        before = await self.call(session, "describe_task")
        detail = await self.call(session, "describe_block", {"id": block_id})
        self.assert_ok(detail)
        self.assertEqual(detail["id"], block_id, detail)
        for key in ("configurable", "computed"):
            self.assertIsInstance(detail[key], dict, detail)
        self.assertIsInstance(detail["inventory_slots"], int, detail)
        self.assertNotIn("catalog", detail)
        # Both discovery tools are reads: no mutation and no time advance.
        self.assert_no_effect(detail, before)
        return detail

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
                    placement(first, "minecraft:quartz_block"),
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
            {"blocks": [placement(target, "minecraft:quartz_block")]},
            [target],
        )
        await self._assert_rejected_without_effect(
            session,
            {
                "blocks": [
                    placement(target, "minecraft:quartz_block"),
                    placement(target, "minecraft:obsidian"),
                ],
                "notify_neighbors": True,
            },
            [target],
        )

    async def _assert_batch_limits(self, session):
        too_many = [
            placement(
                point(1024 + index % 16, 110 + index // 256, 1024 + (index // 16) % 16),
                "minecraft:quartz_block",
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
            placement(point(1024 + x, 100, 1024 + z), "minecraft:quartz_block")
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
        self.assert_block_record(sample[(1024, 100, 1024)], "minecraft:quartz_block")
        self.assert_block_record(sample[(1039, 100, 1039)], "minecraft:quartz_block")

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
            placement(point(1030, 81, 1027), "minecraft:quartz_block"),
            placement(point(1029, 79, 1026), "minecraft:quartz_block"),
            placement(point(1031, 79, 1026), "minecraft:quartz_block"),
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
            *[placement(position, "minecraft:quartz_block") for position in support_positions],
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
            self.assert_block_record(records[coordinates(position)], "minecraft:quartz_block")

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
            placement(point(1036, 79, 1030), "minecraft:quartz_block"),
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
                    placement(position, "minecraft:quartz_block")
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
                "blocks": [placement(chest_position, "minecraft:quartz_block")],
                "notify_neighbors": False,
            },
        )
        self.assert_ok(replaced)
        self.assertEqual(replaced.get("events"), [], replaced)
        replacement = await self._read(session, [chest_position])
        self.assert_block_record(replacement[coordinates(chest_position)], "minecraft:quartz_block")
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
                "blocks": [placement(target, "minecraft:quartz_block")],
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
        self.assert_block_record(actual_repair[coordinates(target)], "minecraft:quartz_block")
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
                    placement(positions[0], "minecraft:quartz_block"),
                    placement(positions[1], "minecraft:quartz_block"),
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
            self.assert_block_record(records[coordinates(position)], "minecraft:quartz_block")

    async def _assert_comparator_notification_scope(self, session):
        comparator = point(1032, 80, 1037)
        chest = point(1033, 80, 1037)
        bridge = point(1032, 80, 1036)
        unrelated = point(1032, 80, 1035)
        setup = [
            placement(comparator, "minecraft:comparator", {"facing": "east"}),
            placement(chest, "minecraft:chest", inventory=[{"slot": 0, "item": "minecraft:quartz_block", "count": 64}]),
            placement(point(1032, 79, 1037), "minecraft:quartz_block"),
            placement(bridge, "minecraft:quartz_block"),
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
        stone = await self.call(session, "modify_blocks", {"blocks": [placement(unrelated, "minecraft:quartz_block")], "notify_neighbors": True})
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
            placement(front, "minecraft:quartz_block"),
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
        self.assert_block_record(moved[coordinates(destination)], "minecraft:quartz_block")
    async def _apply(self, session, blocks, notify=True):
        before = await self.call(session, "describe_task")
        result = await self.call(session, "modify_blocks", {"blocks": blocks, "notify_neighbors": notify})
        self.assert_ok(result)
        # Construction never advances simulation or world time.
        self.assertEqual(result.get("ticks_executed"), 0, result)
        for key in ("simulation_ticks", "preparation_ticks", "world_time"):
            self.assertEqual(result.get(key), before[key], result)
        return result

    async def _assert_new_block_construction(self, session):
        floor = [placement(point(x, 89, z), "minecraft:quartz_block") for x in range(1024, 1040) for z in range(1028, 1040)]
        for start in range(0, len(floor), 128):
            await self._apply(session, floor[start:start + 128], False)
        await self._assert_waterlogged(session)
        await self._assert_free_water(session)
        await self._assert_doors(session)
        await self._assert_shapes_and_block_entities(session)
        await self._assert_open_settings_and_withdrawn_ids(session)

    async def _assert_waterlogged(self, session):
        trapdoor, grate, stairs, log = point(1024, 90, 1028), point(1025, 90, 1028), point(1026, 90, 1028), point(1027, 90, 1028)
        await self._apply(session, [
            placement(trapdoor, "minecraft:oak_trapdoor", {"waterlogged": "true", "facing": "north", "half": "bottom"}),
            placement(grate, "minecraft:waxed_copper_grate", {"waterlogged": "true"}),
            placement(stairs, "minecraft:stone_stairs", {"waterlogged": "true"}),
        ])
        records = await self._read(session, [trapdoor, grate, stairs])
        for position, block_id in ((trapdoor, "minecraft:oak_trapdoor"), (grate, "minecraft:waxed_copper_grate"), (stairs, "minecraft:stone_stairs")):
            self.assert_block_record(records[coordinates(position)], block_id)
            self.assertEqual(records[coordinates(position)]["parameters"]["waterlogged"], "true", records)
        self.assertEqual(records[coordinates(trapdoor)]["parameters"]["facing"], "north", records)
        # An update with false removes the water: same block, different parameter.
        await self._apply(session, [
            placement(trapdoor, "minecraft:oak_trapdoor", {"waterlogged": "false", "facing": "north", "half": "bottom"}),
            placement(grate, "minecraft:waxed_copper_grate", {"waterlogged": "false"}),
        ])
        records = await self._read(session, [trapdoor, grate])
        for position in (trapdoor, grate):
            self.assertEqual(records[coordinates(position)]["parameters"]["waterlogged"], "false", records)
        # The default is dry, and only blocks that own the property accept it.
        await self._apply(session, [placement(trapdoor, "minecraft:oak_trapdoor")])
        self.assertEqual((await self._read(session, [trapdoor]))[coordinates(trapdoor)]["parameters"]["waterlogged"], "false")
        for block_id in ("minecraft:oak_log", "minecraft:lever", "minecraft:oak_door"):
            await self._assert_rejected_without_effect(
                session,
                {"blocks": [placement(log, block_id, {"waterlogged": "true"})], "notify_neighbors": True},
                [log],
            )
        await self._assert_rejected_without_effect(
            session,
            {"blocks": [placement(log, "minecraft:oak_trapdoor", {"waterlogged": "wet"})], "notify_neighbors": True},
            [log],
        )

    async def _assert_free_water(self, session):
        source, side = point(1030, 90, 1030), point(1031, 90, 1030)
        for rejected in ({"level": "3"}, {"falling": "true"}):
            await self._assert_rejected_without_effect(
                session,
                {"blocks": [placement(source, "minecraft:water", rejected)], "notify_neighbors": True},
                [source],
            )
        await self._apply(session, [placement(source, "minecraft:water")])
        records = await self._read(session, [source, side])
        self.assert_block_record(records[coordinates(source)], "minecraft:water")
        self.assertEqual(records[coordinates(source)]["parameters"]["level"], "0", records)
        # The lot does not run the simulation: nothing has flowed yet.
        self.assert_block_record(records[coordinates(side)], "minecraft:air")
        self.assert_ok(await self.call(session, "advance", {"ticks": 10}))
        flowed = await self._read(session, [side])
        self.assert_block_record(flowed[coordinates(side)], "minecraft:water")
        self.assertEqual(flowed[coordinates(side)]["parameters"]["level"], "1", flowed)

    async def _assert_doors(self, session):
        oak, iron = point(1032, 90, 1034), point(1034, 90, 1034)
        result = await self._apply(session, [
            placement(oak, "minecraft:oak_door", {"facing": "north", "hinge": "left", "open": "true"}),
            placement(iron, "minecraft:iron_door", {"facing": "east"}),
        ])
        self.assertEqual(result["placements_applied"], 4, result)
        # Lower then upper after each submitted entry; the upper half is never submitted.
        self.assertEqual(
            [coordinates(position) for position in result["notification_order"]],
            [coordinates(oak), (1032, 91, 1034), coordinates(iron), (1034, 91, 1034)],
            result,
        )
        upper_oak, upper_iron = point(1032, 91, 1034), point(1034, 91, 1034)
        records = await self._read(session, [oak, upper_oak, iron, upper_iron])
        for lower, upper, block_id in ((oak, upper_oak, "minecraft:oak_door"), (iron, upper_iron, "minecraft:iron_door")):
            low, high = records[coordinates(lower)], records[coordinates(upper)]
            self.assert_block_record(low, block_id)
            self.assert_block_record(high, block_id)
            self.assertEqual(low["parameters"]["half"], "lower", low)
            self.assertEqual(high["parameters"]["half"], "upper", high)
            for key in ("facing", "hinge", "open"):
                self.assertEqual(low["parameters"][key], high["parameters"][key], records)
        self.assertEqual(records[coordinates(oak)]["parameters"]["open"], "true", records)
        self.assertEqual(records[coordinates(oak)]["parameters"]["hinge"], "left", records)
        self.assertEqual(records[coordinates(iron)]["parameters"]["facing"], "east", records)

        # Every refusal leaves the whole lot, including the other door, unplaced.
        free, unsupported, second = point(1036, 90, 1034), point(1037, 92, 1034), point(1038, 90, 1034)
        above_free, top = point(1036, 91, 1034), point(1036, 319, 1034)
        invalid = [
            [placement(free, "minecraft:oak_door"), placement(unsupported, "minecraft:iron_door")],
            [placement(free, "minecraft:oak_door"), placement(top, "minecraft:oak_door")],
            [placement(free, "minecraft:oak_door"), placement(above_free, "minecraft:quartz_block")],
            [placement(above_free, "minecraft:quartz_block"), placement(free, "minecraft:oak_door")],
            [placement(free, "minecraft:oak_door"), placement(second, "minecraft:iron_door", {"half": "upper"})],
            [placement(free, "minecraft:oak_door"), placement(above_free, "minecraft:oak_door")],
        ]
        for blocks in invalid:
            await self._assert_rejected_without_effect(
                session,
                {"blocks": blocks, "notify_neighbors": True},
                [free, above_free, unsupported, point(1037, 93, 1034), top, second, point(1038, 91, 1034)],
            )

    async def _assert_shapes_and_block_entities(self, session):
        pane_a, pane_b = point(1024, 90, 1036), point(1025, 90, 1036)
        wall_a, wall_b = point(1024, 90, 1038), point(1025, 90, 1038)
        scaffold, scaffold_top = point(1028, 90, 1036), point(1028, 91, 1036)
        head, beacon, composter = point(1030, 90, 1036), point(1032, 90, 1036), point(1034, 90, 1036)
        furnace, chest = point(1036, 90, 1036), point(1038, 90, 1036)
        await self._apply(session, [
            placement(pane_a, "minecraft:glass_pane"), placement(pane_b, "minecraft:glass_pane"),
            placement(wall_a, "minecraft:stone_brick_wall"), placement(wall_b, "minecraft:stone_brick_wall"),
            placement(scaffold, "minecraft:scaffolding"), placement(scaffold_top, "minecraft:scaffolding"),
            placement(head, "minecraft:player_head", {"rotation": "4"}),
            placement(beacon, "minecraft:beacon"),
            placement(composter, "minecraft:composter", {"level": "5"}),
            placement(furnace, "minecraft:furnace", {"facing": "south"}, [{"slot": 0, "item": "minecraft:diamond", "count": 2}]),
            placement(chest, "minecraft:chest", {"waterlogged": "true"}, [{"slot": 1, "item": "minecraft:emerald", "count": 3}]),
        ])
        records = await self._read(session, [pane_a, pane_b, wall_a, wall_b, scaffold, scaffold_top, head, beacon, composter, furnace, chest])
        # Connections are computed by Minecraft from the neighbours, never submitted.
        self.assertEqual(records[coordinates(pane_a)]["parameters"]["east"], "true", records)
        self.assertEqual(records[coordinates(pane_b)]["parameters"]["west"], "true", records)
        self.assertEqual(records[coordinates(wall_a)]["parameters"]["east"], "low", records)
        self.assertEqual(records[coordinates(wall_b)]["parameters"]["west"], "low", records)
        for position in (scaffold, scaffold_top):
            self.assert_block_record(records[coordinates(position)], "minecraft:scaffolding")
            self.assertIn("distance", records[coordinates(position)]["parameters"])
        self.assertEqual(records[coordinates(head)]["parameters"]["rotation"], "4", records)
        for position, block_id in ((head, "minecraft:player_head"), (beacon, "minecraft:beacon")):
            self.assert_block_record(records[coordinates(position)], block_id)
            self.assertIn("block_entity_type", records[coordinates(position)], records)
        self.assertEqual(records[coordinates(composter)]["parameters"]["level"], "5", records)
        self.assertEqual(records[coordinates(furnace)]["inventory"], [{"slot": 0, "item": "minecraft:diamond", "count": 2}], records)
        self.assertEqual(records[coordinates(chest)]["inventory"], [{"slot": 1, "item": "minecraft:emerald", "count": 3}], records)
        self.assertEqual(records[coordinates(chest)]["parameters"]["waterlogged"], "true", records)
        spare = point(1039, 92, 1039)
        for block_id in ("minecraft:composter", "minecraft:beacon", "minecraft:player_head"):
            await self._assert_rejected_without_effect(
                session,
                {"blocks": [placement(spare, block_id, inventory=[{"slot": 0, "item": "minecraft:diamond", "count": 1}])], "notify_neighbors": True},
                [spare],
            )

    async def _assert_open_settings_and_withdrawn_ids(self, session):
        trapdoor, gate = point(1026, 90, 1030), point(1027, 90, 1030)
        await self._apply(session, [
            placement(trapdoor, "minecraft:oak_trapdoor", {"open": "true"}),
            placement(gate, "minecraft:oak_fence_gate", {"open": "true", "facing": "south"}),
        ])
        records = await self._read(session, [trapdoor, gate])
        self.assertEqual(records[coordinates(trapdoor)]["parameters"]["open"], "true", records)
        self.assertEqual(records[coordinates(gate)]["parameters"]["open"], "true", records)
        # Iron elements stay redstone-driven, leaves keep vanilla persistence, no water level, no power.
        target = point(1028, 90, 1030)
        for block_id, parameters in (
            ("minecraft:iron_door", {"open": "true"}),
            ("minecraft:iron_trapdoor", {"open": "true"}),
            ("minecraft:oak_leaves", {"persistent": "false"}),
            ("minecraft:oak_door", {"half": "upper"}),
            ("minecraft:oak_trapdoor", {"powered": "true"}),
        ):
            await self._assert_rejected_without_effect(
                session,
                {"blocks": [placement(target, block_id, parameters)], "notify_neighbors": True},
                [target],
            )
        # Withdrawn ids are refused in construction and as an input device, not only in details.
        await self._assert_rejected_without_effect(
            session,
            {"blocks": [placement(target, "minecraft:stone")], "notify_neighbors": True},
            [target],
            kind="unsupported",
            code="unsupported_component",
        )
        declared = await self.call(session, "declare_input", {
            "device": "minecraft:spruce_button",
            "position": target,
            "orientation": "west",
            "input_block": point(1029, 90, 1030),
        })
        self.assert_error(declared, "unsupported", "unsupported_component")

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
