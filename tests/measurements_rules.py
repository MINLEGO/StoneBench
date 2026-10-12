"""Small independent source-interpretation checks, not Minecraft runtime proof."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from measurements import volume, summarize, movement_end, measure

class MeasurementRulesChecks(unittest.TestCase):
    def test_cumulative_axes_not_endpoint_max_or_block_count(self):
        # Two 1-cube objects visit perpendicular arms. Both local envelopes have
        # volume 5, but the complete x/y union is a 5x5x1 volume of 25.
        self.assertEqual(volume([[0,0,0,5,1,1],[0,0,0,1,5,1]])["value"],25)
    def test_ceil_dimensions_before_multiplication(self):
        self.assertEqual(volume([[0,0,0,1.01,2.01,3.01]])["dimensions"],[2,3,4])
        self.assertEqual(volume([[0,0,0,1.01,2.01,3.01]])["value"],24)
    def test_empty_observation_and_nonconformance_do_not_make_a_record(self):
        report=summarize([],False)
        self.assertEqual(report["dynamic_volume"]["status"],"indeterminate")
        self.assertIsNone(report["dynamic_volume"]["value"])
        self.assertEqual(report["interpretation"],"alpha_diagnostic")
        self.assertEqual(report["record_eligibility"],"not_verified")
    def test_axis_union_across_cycles_and_independent_objectives(self):
        def row(box,time):
            return {"mode":"repeater","dynamic_volume":{"envelope":box,"gaps":[]},"opening_time":{"status":"measured","value":time}}
        report=summarize([row([0,0,0,5,1,1],4),row([0,0,0,1,5,1],6)],True)
        self.assertEqual(report["dynamic_volume"]["value"],25)
        self.assertEqual(report["opening_time"]["value"],6)
        self.assertNotIn("score",report)
    def test_conditional_exclusion_is_rechecked_across_cycle_axes(self):
        row={"mode":"repeater","dynamic_volume":{"envelope":[0,0,0,5,5,1],"minimum_envelope":[0,0,0,4,5,1],"gaps":[]}}
        report=summarize([row],True)
        self.assertEqual(report["dynamic_volume"]["status"],"indeterminate")
        self.assertIsNone(report["dynamic_volume"]["value"])
        self.assertIn("conditional_exclusion_changes_cumulative_dimensions",report["dynamic_volume"]["gaps"])

    def test_notification_or_read_does_not_prove_wiring_membership(self):
        # A 1-cube declared input and a redundant stone at x6 have possible
        # widths 1..7. A notification cannot choose the exact width 7.
        # Event schema/source matches native artifact 0b257c92-f6ce-41ed-bafa-f4d330a500f5
        # from the archived server-2 observer fixture; coordinates are translated.
        operation={"initial":{"world_time":0,"state":{}}, "transition":{"status":"terminated","recognition_tick":1,"last_movement_tick":0}, "ticks_executed":1,"execution":{"wall_seconds":0.01}}
        geometry={"expected_state":"closed","measurement_roles":[{"x":0,"y":2,"z":0,"role":"frame_interior","block":"minecraft:quartz_block"}],"criteria":[{"id":"hallway_composition","mandatory":False,"status":"not_verified"},{"id":"frame_state","status":"satisfied"}]}
        declaration={"input_block":{"x":0,"y":0,"z":0},"adapter_positions":[],"mode":"repeater"}
        clock={"world_time":0,"simulation_index":0,"tick_index":0,"phase":"tick","operation_order":1}
        origin={**clock,"kind":"input_interaction","position":declaration["input_block"],"detail":{}}
        for kind in ("neighbor_update","neighbor_state_update","block_state_read"):
            for role,block in (("passive_material","minecraft:stone"),("component","minecraft:repeater")):
                with self.subTest(kind=kind,role=role):
                    rows=[]
                    for x,name,wiring_role in ((0,"minecraft:stone","passive_material"),(6,block,role)):
                        detail={"x":x,"y":0,"z":0,"block":name,"wiring_role":wiring_role,"bounds":[x,0,0,x+1,1,1]}
                        rows.append({**detail,"measurement":detail})
                    notified={**clock,"kind":kind,"position":{"x":6,"y":0,"z":0},"detail":{"source":"minecraft:repeater"}}
                    metric=measure(operation,[{"world_time":0,"blocks":rows}],[origin,notified],geometry,geometry,declaration,True,{"restorable_observed_scope":True,"uncovered_components":[]})["dynamic_volume"]
                    self.assertEqual(metric["status"],"indeterminate")
                    self.assertIsNone(metric["value"])
                    self.assertEqual(metric["observed_value"],7)
                    self.assertEqual(metric["minimum_envelope"],[0,0,0,1,1,1])
                    self.assertEqual(metric["maximum_envelope"],[0,0,0,7,1,1])
                    self.assertIn("conditional_role_exclusion_changes_dimensions",metric["gaps"])

    def test_source_defined_ends_use_movement_start(self):
        self.assertEqual(movement_end(11,"standard_extension"),13)
        self.assertEqual(movement_end(11,"standard_retraction"),13)
        self.assertEqual(movement_end(11,"instant_retraction"),11)
        for pulse in (0,1,2):
            self.assertEqual(movement_end(11,"short_pulse_extension",pulse),11+pulse)
        with self.assertRaises(ValueError):movement_end(11,"short_pulse_extension")
        with self.assertRaises(ValueError):movement_end(11,"unclassified")

    def test_gap_does_not_publish_an_exact_volume(self):
        report=summarize([{"mode":"repeater","dynamic_volume":{"envelope":[0,0,0,2,2,2],"gaps":["missing_intratick"]}}],False)
        self.assertIsNone(report["dynamic_volume"]["value"])
        self.assertEqual(report["dynamic_volume"]["observed_value"],8)

if __name__=="__main__":unittest.main()
