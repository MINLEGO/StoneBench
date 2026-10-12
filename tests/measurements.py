"""Real MCP measurements: the existing vanilla regular door and independent copies."""
import json
import os
from pathlib import Path
import unittest
import verification
from verification_worker import artifact, trace_complete
from measurements import measure, volume

class MeasurementsRuntimeIntegration(verification.VerificationRuntimeIntegration):
    async def test_real_mcp_server_contract(self):
        await self._connect()
        evidence = {}
        try:
            session = self.sessions[0]
            self.assert_ok(await self.call(session,"start_attempt",{"task_id":"2x2-volume"}))
            checkpoint = await self.prepare_powered_checkpoint(session)
            before = await self.call(session,"verification_snapshot")
            report = await self.verify(session,checkpoint["checkpoint_id"],"none")
            self.assertEqual(report["verdict"],"conforms_to_alpha",self.report_context(report))
            metrics = report["measurements"]
            self.assertEqual(metrics["dynamic_volume"]["status"],"indeterminate",metrics)
            # Input-connected fixture circuit spans x1018..1033, y79..83, z1022..1025:
            # 16*5*4=320. Isolated comparator chest/stone are outside the input-connected wiring.
            self.assertEqual(metrics["dynamic_volume"]["dimensions"],[16,5,4],metrics["dynamic_volume"])
            self.assertIsNone(metrics["dynamic_volume"]["value"])
            self.assertEqual(metrics["dynamic_volume"]["observed_value"],320)
            self.assertTrue(any(r["position"] == [1033,81,1025] and r["reason"] == "observed_input_connection_does_not_prove_wiring_necessity"
                for e in metrics["transitions"] for r in e["dynamic_volume"]["conditional_roles"]),metrics)
            self.assertEqual(metrics["record_eligibility"],"not_verified")
            self.assertNotIn("score",metrics)
            self.assertEqual(metrics["opening_time"]["value"],6)
            self.assertEqual(metrics["closing_time"]["value"],6)
            self.assertNotEqual(metrics["dynamic_volume"]["minimum_envelope"],metrics["dynamic_volume"]["maximum_envelope"])
            for entry in metrics["transitions"]:
                kind = "opening_time" if entry["state"] == "open" else "closing_time"
                time = entry[kind]
                self.assertEqual(time["status"],"measured",time)
                self.assertIsNotNone(time["signal_at_input_block"])
                self.assertLess(time["completion_world_time"],time["last_circuit_movement_end_world_time"],time)
                self.assertLess(time["last_circuit_movement_end_world_time"],time["rest_recognition"]["world_time"],time)
                self.assertEqual(time["value"],time["completion_world_time"]-time["interaction"]["world_time"])
                self.assertEqual(time["value"],time["adaptation_ticks"]+time["door_response_ticks"])
                self.assertEqual(time["adaptation_ticks"],2 if entry["mode"]=="repeater" else 0,time)
                self.assertEqual(entry["purpose"],"reference" if entry["mode"]=="repeater" else "direct_diagnostic")
                excluded = entry["dynamic_volume"]["excluded"]
                self.assertTrue(any(r["reason"] == "validated_external_adapter" for r in excluded),excluded)
                self.assertTrue(any(r["reason"].startswith("door_material") for r in excluded),excluded)
                self.assertFalse(any(r["block"] in ("minecraft:piston_head","minecraft:sticky_piston") for r in excluded),excluded)
                self.assertTrue(any(m["pertinent_to_door_time"] for m in entry["movements"]))
            after = await self.call(session,"verification_snapshot")
            self.assertEqual(self.frozen_snapshot(before),self.frozen_snapshot(after))
            pulse = await self.transient_pulse(self.sessions[1])
            await self.cancel_worker_during_boot(session,checkpoint["checkpoint_id"])
            evidence={"pulse":pulse, "report":report,"working_snapshot_preserved":True,"fixture_expectation":{"dimensions":[16,5,4],"volume":320}}
        finally:
            if os.environ.get("STONEBENCH_MEASUREMENTS_EVIDENCE"):
                Path(os.environ["STONEBENCH_MEASUREMENTS_EVIDENCE"]).write_text(json.dumps(evidence,indent=2),encoding="utf-8")
            await self.stack.aclose()

    async def prepare_powered_checkpoint(self,session):
        await super().prepare_powered_checkpoint(session)
        # Add one vanilla delay-4 repeater branch behind the frame. Its late
        # piston movement must extend rest but never replace door completion.
        blocks=[]
        for x in (1030,1031):
            blocks.append({"x":x,"y":80,"z":1025,"block":"minecraft:stone"})
        blocks += [
            {"x":1030,"y":81,"z":1025,"block":"minecraft:redstone_wire"},
            {"x":1031,"y":81,"z":1025,"block":"minecraft:repeater","parameters":{"facing":"west","delay":"4"}},
            {"x":1032,"y":81,"z":1025,"block":"minecraft:sticky_piston","parameters":{"facing":"up"}},
            # Redundant stone beside the piston is notified, never actuates the door.
            # Its outer x extent must remain conditional rather than exact wiring.
            {"x":1033,"y":81,"z":1025,"block":"minecraft:stone"},
        ]
        self.assert_ok(await self.call(session,"modify_blocks",{"blocks":blocks,"notify_neighbors":True}))
        settled=await self.call(session,"transition",{"max_ticks":36000,"trace":True})
        self.assert_ok(settled)
        self.assertEqual(settled["transition"]["status"],"terminated")
        created=await self.call(session,"create_checkpoint")
        self.assert_ok(created)
        return created["checkpoint"]

    async def transient_pulse(self,session):
        self.assert_ok(await self.call(session,"start_attempt",{"task_id":"2x2-volume"}))
        blocks=[{"x":x,"y":80,"z":1030,"block":"minecraft:stone"} for x in (1038,1039)]
        blocks += [
            {"x":1038,"y":81,"z":1030,"block":"minecraft:stone"},
            {"x":1037,"y":81,"z":1030,"block":"minecraft:lever","parameters":{"face":"wall","facing":"west"}},
            {"x":1039,"y":81,"z":1030,"block":"minecraft:redstone_wire"},
            {"x":1040,"y":81,"z":1030,"block":"minecraft:observer","parameters":{"facing":"west"}},
            {"x":1041,"y":81,"z":1030,"block":"minecraft:sticky_piston","parameters":{"facing":"east"}},
        ]
        self.assert_ok(await self.call(session,"modify_blocks",{"blocks":blocks,"notify_neighbors":True}))
        self.assert_ok(await self.call(session,"transition",{"trace":True}))
        declaration=await self.call(session,"declare_input",{"device":"minecraft:lever","position":{"x":1037,"y":81,"z":1030},"orientation":"west","input_block":{"x":1038,"y":81,"z":1030}})
        self.assert_ok(declaration)
        self.assert_ok(await self.call(session,"prepare_input",{"mode":"repeater"}))
        self.assert_ok(await self.call(session,"transition",{"trace":True}))
        geometry=await self.call(session,"check_geometry",{"expected_state":"closed"})
        self.assert_ok(geometry)
        self.assert_ok(await self.call(session,"transition",{"trace":True}))
        checkpoint=await self.call(session,"create_checkpoint")
        self.assert_ok(checkpoint)
        roots=[Path(p) for p in os.environ["STONEBENCH_SERVER_ROOTS"].split(";")]
        identifier=checkpoint["checkpoint"]["checkpoint_id"]
        root=next(p for p in roots if (p/"stonebench/checkpoints"/identifier).exists())
        manifest=json.loads((root/"stonebench/checkpoints"/identifier/"manifest.json").read_text())
        operation=await self.call(session,"transition",{"max_ticks":36000,"trace":True,"interact":True})
        self.assert_ok(operation)
        self.assertEqual(operation["transition"]["status"],"terminated",operation)
        final=await self.call(session,"check_geometry",{"expected_state":"open"})
        snapshot=await self.call(session,"verification_snapshot")
        traces=artifact(root,operation["trace"])
        samples=[operation["initial"]]+traces
        samples=[{"world_time":row["world_time"],"blocks":artifact(root,row["state"]["blocks"])} for row in samples]
        events=artifact(root,operation["intratick_events"])
        measured=measure(operation,samples,events,geometry,final,snapshot["input"],trace_complete(root,operation),manifest["provenance"]["memory_coverage"])
        self.assertEqual(measured["dynamic_volume"]["status"],"indeterminate",measured["dynamic_volume"])
        self.assertEqual(measured["dynamic_volume"]["dimensions"],[5,2,1],measured["dynamic_volume"])
        self.assertIsNone(measured["dynamic_volume"]["value"])
        self.assertEqual(measured["dynamic_volume"]["observed_value"],10)
        endpoints=[]
        adapters={tuple(p[k] for k in ("x","y","z")) for p in snapshot["input"]["adapter_positions"]}
        for row in (samples[0],samples[-1]):
            endpoints += [b["measurement"]["bounds"] for b in row["blocks"] if b["block"]!="minecraft:air" and tuple(b[k] for k in ("x","y","z")) not in adapters and b["measurement"].get("bounds")]
        self.assertEqual(volume(endpoints)["value"],8)
        methods={m["end"]["method"] for m in measured["movements"]}
        self.assertIn("short_pulse_extension",methods,measured["movements"])
        self.assertIn("standard_retraction",methods,measured["movements"])
        self.assertTrue(any(m["end"]["received_pulse_ticks"]==2 for m in measured["movements"]))
        # Genuine observer pulse; no stable extended endpoint. The head exists
        # only in the movement trace, and source-defined 2gt timing is retained.
        from copy import deepcopy
        negatives={}
        for name,changed_events,coverage,memory in (
            ("missing_movement_start",[e for e in events if not(e["kind"]=="piston_movement_sample" and e["detail"]["sample"]=="start")],True,manifest["provenance"]["memory_coverage"]),
            ("missing_effective_extent",[e for e in events if e["kind"]!="measurement_block"],True,manifest["provenance"]["memory_coverage"]),
            ("trace_gap",events,False,manifest["provenance"]["memory_coverage"]),
            ("memory_gap",events,True,{"restorable_observed_scope":False,"uncovered_components":["hopper:lastTickTime"]}),
        ):
            negative=measure(operation,deepcopy(samples),changed_events,geometry,final,snapshot["input"],coverage,memory)
            self.assertEqual(negative["dynamic_volume"]["status"],"indeterminate",negative)
            self.assertIsNone(negative["dynamic_volume"]["value"])
            negatives[name]=negative["dynamic_volume"]
        return {"negative_controls":negatives,"operation":operation,"metrics":measured,"endpoint_volume":8,"expected_dynamic_volume":10,"checkpoint":checkpoint}

if __name__ == "__main__":
    unittest.main()
