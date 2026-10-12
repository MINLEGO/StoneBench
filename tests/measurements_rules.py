"""Small independent source-interpretation checks, not Minecraft runtime proof."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from measurements import volume, summarize, movement_end

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
