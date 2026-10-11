"""Input matrix through the real MCP server; absolute records stay archived."""
import json
import os
from pathlib import Path
import unittest
from observation import ObservationRuntimeIntegration
from construction import point, placement, coordinates
from integration import TASK_ID


class InputRuntimeIntegration(ObservationRuntimeIntegration):
    async def test_real_mcp_server_contract(self):
        await self._connect()
        self.evidence = {"cycles": [], "negative_controls": []}
        try:
            for s in self.sessions:
                self.assert_ok(await self.call(s, "start_attempt", {"task_id": TASK_ID}))
            session = self.sessions[0]
            catalog = await self.call(session, "describe_blocks")
            buttons = [row["id"] for row in catalog["catalog"] if row["id"].endswith("_button") and row["id"] != "minecraft:stone_button"]
            self.assertTrue(buttons)
            await self.negatives(session)
            await self.lateral_and_partial(self.sessions[1])
            groups = {}
            for fixture in ("torch", "repeater-1", "repeater-4", "piston"):
                for device in ("minecraft:lever", "minecraft:stone_button", "minecraft:oak_button"):
                    for mode in ("direct", "repeater"):
                        for repeat in range(3):
                            record = await self.cycle(session, fixture, device, mode)
                            self.evidence["cycles"].append(record)
                            group = (fixture, device, mode)
                            # Compare explicit behavioral fields, never rewrite absolute trace clocks.
                            signature = {k: record[k] for k in ("on_delay", "off_delay", "source_pulse", "signal_pulse", "opened", "closed")}
                            if group in groups:
                                self.assertEqual(groups[group], signature)
                            groups[group] = signature
            for fixture in ("torch", "repeater-1", "repeater-4", "piston"):
                for device in ("minecraft:lever", "minecraft:stone_button", "minecraft:oak_button"):
                    self.assertEqual(groups[(fixture, device, "direct")]["opened"], groups[(fixture, device, "repeater")]["opened"])
                    self.assertEqual(groups[(fixture, device, "direct")]["closed"], groups[(fixture, device, "repeater")]["closed"])
            self.evidence["catalog_wood_buttons"] = buttons
            # Actual coverage for every retained wood button, including both modes and all fixtures.
            for device in buttons:
                if device == "minecraft:oak_button":
                    continue
                for fixture in ("torch", "repeater-1", "repeater-4", "piston"):
                    for mode in ("direct", "repeater"):
                        self.evidence["cycles"].append(await self.cycle(session, fixture, device, mode))
            self.evidence["success"] = True
        finally:
            output = Path(os.environ.get("STONEBENCH_INPUT_EVIDENCE", ".runtime/input-summary.json"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(self.evidence, indent=2), encoding="utf-8")
            await self.stack.aclose()

    async def fixture(self, s, name, device, declare=True):
        cleanup = [placement(point(x,y,z), "minecraft:air") for x in range(1025,1039) for y in range(79,83) for z in range(1029,1034)]
        for offset in range(0,len(cleanup),256):
            await self.modify(s, cleanup[offset:offset+256], False)
        floor = [placement(point(x,79,z), "minecraft:stone") for x in range(1028,1039) for z in range(1029,1034)]
        blocks = floor + [placement(point(1028,80,1030), "minecraft:stone"), placement(point(1027,80,1030), device, {"face":"wall", "facing":"west"}), placement(point(1029,80,1032), "minecraft:chest", inventory=[{"slot":0,"item":"minecraft:diamond","count":7}])]
        if name.startswith("repeater"):
            blocks.append(placement(point(1029,80,1030), "minecraft:repeater", {"facing":"west", "delay":"4" if name.endswith("4") else "1"}))
        else:
            blocks.append(placement(point(1029,80,1030), "minecraft:redstone_wall_torch", {"facing":"east"}))
        if name == "piston":
            blocks += [placement(point(1030,80,1030), "minecraft:redstone_wire"), placement(point(1031,80,1030), "minecraft:sticky_piston", {"facing":"east"}), placement(point(1032,80,1030), "minecraft:stone")]
        await self.modify(s, blocks)
        self.assert_ok(await self.call(s, "advance", {"ticks":12}))
        if not declare:
            return
        declared = await self.call(s, "declare_input", {"device":device, "position":point(1027,80,1030), "orientation":"west", "input_block":point(1028,80,1030)})
        self.assert_ok(declared)
        return declared

    async def cycle(self,s,fixture,device,mode):
        declared = await self.fixture(s,fixture,device)
        before = await self.call(s,"describe_task")
        prepared = await self.call(s,"prepare_input",{"mode":mode})
        self.assert_ok(prepared)
        self.assertTrue(prepared["construction_preserved"])
        self.assertEqual(prepared["world_time"],before["world_time"])
        self.assertEqual(prepared["simulation_ticks"],before["simulation_ticks"])
        self.assertEqual(prepared["preparation_ticks"],before["preparation_ticks"])
        if mode == "repeater":
            self.assertEqual(await self.pages(s, prepared["preservation_differences"],256), [])
        construction_positions=[point(x,y,z) for x in range(1028,1039) for y in range(79,83) for z in range(1029,1034)]
        initial = await self.call(s,"read_blocks",{"positions":construction_positions})
        reports=[]
        if device == "minecraft:lever":
            reports.append(await self.call(s,"act_input",{"ticks":12,"trace":True}))
            opened_report=reports[0]
            reports.append(await self.call(s,"act_input",{"ticks":12,"trace":True}))
        else:
            reports.append(await self.call(s,"act_input",{"ticks":45,"trace":True}))
            opened_report=reports[0]
        events=[]
        for report in reports:
            self.assert_ok(report)
            self.assertTrue(report["continuity"]["complete"])
            events += await self.pages(s,report["intratick_events"],256)
        source = [e for e in events if e["kind"]=="input_device_change"]
        signal = [e for e in events if e["kind"]=="input_signal_change"]
        interactions = [e for e in events if e["kind"]=="input_interaction"]
        self.assertEqual(len(interactions),2 if device=="minecraft:lever" else 1)
        for e in interactions:
            self.assertEqual(e["phase"],"before_world_time")
        for report,e in zip(reports,interactions):
            self.assertEqual(e["world_time"],report["initial"]["world_time"])
        self.assertEqual(len(source),2)
        self.assertEqual(len(signal),2)
        component = [e for e in events if e["kind"]=="block_write_result" and e["position"]==point(1029,80,1030) and e["detail"]["changed"]]
        self.assertEqual(len(component),2,component)
        # tick_index is operation-local, world_time is absolute; MC-172213 edge before increment has the old clock.
        on_delay = component[0]["simulation_index"]-signal[0]["simulation_index"]
        off_delay = component[1]["simulation_index"]-signal[1]["simulation_index"]
        expected = 7 if fixture=="repeater-4" else 1
        self.assertEqual(on_delay,expected if mode=="direct" else expected+1)
        self.assertEqual(off_delay,expected if device=="minecraft:lever" and mode=="direct" else expected+1)
        source_pulse=source[1]["simulation_index"]-source[0]["simulation_index"]
        signal_pulse=signal[1]["simulation_index"]-signal[0]["simulation_index"]
        if device != "minecraft:lever":
            self.assertEqual(source_pulse,19 if device=="minecraft:stone_button" else 29)
            self.assertEqual(signal_pulse,source_pulse+(mode=="repeater"))
        ticks=await self.pages(s,opened_report["trace"],256)
        opened=await self.snapshot(s,ticks[11])
        closed=await self.snapshot(s,reports[-1]["final"])
        keys=[coordinates(p) for p in construction_positions]
        for queue in ("block_ticks","fluid_ticks","block_events"):
            self.assertEqual(reports[-1]["final"]["state"][queue],[])
            adapter_positions={coordinates(p) for p in prepared["adapter_positions"]}
            self.assertFalse([event for event in ticks[11]["state"][queue] if coordinates(event) not in adapter_positions])
        adapter_rows=await self.pages(s,ticks[11]["adapter_blocks"],256)
        construction_rows=await self.pages(s,ticks[11]["construction_blocks"],256)
        self.assertEqual({coordinates(row) for row in adapter_rows},adapter_positions)
        self.assertFalse({coordinates(row) for row in construction_rows} & adapter_positions)
        initial_blocks={coordinates(row):row for row in initial["blocks"]}
        self.assertEqual({str(k):closed[k] for k in keys}, {str(k):initial_blocks[k] for k in keys})
        return {"fixture":fixture,"device":device,"mode":mode,"on_delay":on_delay,"off_delay":off_delay,"source_pulse":source_pulse,"signal_pulse":signal_pulse,"opened":{str(k):opened[k] for k in keys},"closed":{str(k):closed[k] for k in keys},"reports":reports,"prepared":prepared,"events": [e for e in events if e["kind"].startswith("input_")],"component_events":component}


    async def lateral_and_partial(self,s):
        old=[]
        directions={"west":(-1,0),"east":(1,0),"north":(0,-1),"south":(0,1)}
        for orientation,(dx,dz) in directions.items():
            if old:
                await self.modify(s,[placement(pos,"minecraft:air") for pos in old],False)
            support=point(1030,80,1030)
            source=point(1030+dx,80,1030+dz)
            output=point(1030-dx,80,1030-dz)
            opposite={"west":"east","east":"west","north":"south","south":"north"}[orientation]
            await self.modify(s,[placement(support,"minecraft:stone"),placement(source,"minecraft:stone_button",{"face":"wall","facing":orientation}),placement(output,"minecraft:redstone_wall_torch",{"facing":opposite})])
            self.assert_ok(await self.call(s,"advance",{"ticks":4}))
            declared=await self.call(s,"declare_input",{"device":"minecraft:stone_button","position":source,"orientation":orientation,"input_block":support})
            self.assert_ok(declared)
            pressed=await self.call(s,"act_input",{"ticks":1,"trace":True})
            self.assert_ok(pressed)
            active=await self.call(s,"act_input",{"ticks":1})
            self.assert_error(active,"validation")
            self.assertFalse(active["mutated"])
            self.assertEqual(active["world_time"],pressed["world_time"])
            visible=await self.call(s,"describe_task")
            self.assertEqual(visible["input"]["orientation"],orientation)
            release=await self.call(s,"advance",{"ticks":24,"trace":True})
            self.assert_ok(release)
            events=await self.pages(s,release["intratick_events"],256)
            self.assertTrue(any(e["kind"]=="input_device_change" and e["detail"]["power"]==0 for e in events))
            self.assertTrue(any(e["kind"]=="input_signal_change" and e["detail"]["power"]==0 for e in events))
            self.evidence.setdefault("lateral_faces",[]).append({"orientation":orientation,"pressed":pressed,"release":release})
            # Removing the vanilla support invalidates later activation, without a world tick.
            removed=await self.modify(s,[placement(support,"minecraft:air")])
            refused=await self.call(s,"act_input",{"ticks":1})
            self.assert_error(refused,"validation")
            self.assertFalse(refused["mutated"])
            old=[support,source,output]

    async def negatives(self,s):
        await self.fixture(s,"torch","minecraft:lever",False)
        args={"device":"minecraft:lever","position":point(1027,80,1030),"orientation":"up","input_block":point(1028,80,1030)}
        for orientation in ("up","down","east"):
            args["orientation"]=orientation
            rejected=await self.call(s,"declare_input",args)
            self.assert_error(rejected,"validation")
            self.evidence["negative_controls"].append(rejected)
        args["orientation"]="west"
        self.assert_ok(await self.call(s,"declare_input",args))
        # Typed inventory alteration is an exact observable divergence.
        changed=await self.modify(s,[placement(point(1029,80,1032),"minecraft:chest",inventory=[{"slot":0,"item":"minecraft:diamond","count":8}])],False)
        differences=await self.pages(s,changed["diff"],256)
        self.assertTrue(any("inventory" in row["field"] for row in differences))
        self.evidence["negative_controls"].append({"inventory_fields":differences})
        await self.modify(s,[placement(point(1026,80,1030),"minecraft:stone")],False)
        rejected=await self.call(s,"prepare_input",{"mode":"repeater"})
        self.assert_error(rejected,"validation")
        self.assertFalse(rejected["mutated"])
        self.evidence["negative_controls"].append(rejected)
        await self.fixture(s,"torch","minecraft:lever",False)
        await self.modify(s,[placement(point(1026,80,1030),"minecraft:stone")],False)
        exterior=await self.call(s,"declare_input",args)
        self.assert_error(exterior,"validation")
        self.assertIn("exterior",exterior["error"]["message"])
        self.evidence["negative_controls"].append(exterior)
        await self.fixture(s,"torch","minecraft:lever",False)
        await self.modify(s,[placement(point(1028,80,1030),"minecraft:observer",{"facing":"west"})])
        self.assert_ok(await self.call(s,"advance",{"ticks":12}))
        self.assert_ok(await self.call(s,"declare_input",args))
        preservation=await self.call(s,"prepare_input",{"mode":"repeater"})
        self.assert_error(preservation,"infrastructure")
        self.assertTrue(preservation["mutated"])
        self.assertIn("altered initial construction",preservation["error"]["message"])
        self.evidence["negative_controls"].append(preservation)


if __name__ == "__main__":
    unittest.main(defaultTest="InputRuntimeIntegration",verbosity=2)
