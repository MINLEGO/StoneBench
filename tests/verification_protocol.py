"""Exact state comparison and alpha verdict rules without Minecraft startup."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verification_protocol import construction, criteria, first_difference, compliant, verdict


class VerificationProtocolTests(unittest.TestCase):
    def test_boolean_and_integer_are_different_types(self):
        difference = first_difference({"powered": False}, {"powered": 0})

        self.assertEqual(difference, {
            "field": "$.powered",
            "expected": False,
            "observed": 0,
        })

    def test_ordered_inventory_and_nbt_lists_are_not_normalized(self):
        before = {"inventory": [
            {"slot": 0, "item": "minecraft:diamond", "count": 1},
            {"slot": 1, "item": "minecraft:iron_ingot", "count": 2},
        ]}
        after = {"inventory": list(reversed(before["inventory"]))}

        self.assertEqual(first_difference(before, after)["field"], "$.inventory[0].count")

        before_nbt = {"nbt": {"Items": [{"Slot": 0}, {"Slot": 1}]}}
        after_nbt = {"nbt": {"Items": [{"Slot": 1}, {"Slot": 0}]}}
        self.assertEqual(first_difference(before_nbt, after_nbt)["field"], "$.nbt.Items[0].Slot")

    def test_runtime_internal_fields_remain_part_of_construction(self):
        before = {"runtime": {"last_tick_time": 20, "cooldown": 0}}
        after = {"runtime": {"last_tick_time": 21, "cooldown": 0}}

        self.assertEqual(first_difference(before, after)["field"], "$.runtime.last_tick_time")

    def test_construction_omits_only_empty_air_sampling_records(self):
        snapshot = {"construction": {"blocks": {
            "empty": {"block": "minecraft:air"},
            "inventory": {"block": "minecraft:air", "inventory": [{"slot": 0, "item": "minecraft:diamond", "count": 1}]},
            "nbt": {"block": "minecraft:air", "nbt": {"Custom": 1}},
            "runtime": {"block": "minecraft:air", "runtime": {"cooldown": 1}},
            "stone": {"block": "minecraft:stone"},
        }}}

        result = construction(snapshot)

        self.assertNotIn("empty", result["blocks"])
        self.assertEqual(set(result["blocks"]), {"inventory", "nbt", "runtime", "stone"})

    def test_mandatory_indeterminate_vetoes_compliance_and_verdict(self):
        rows = [
            {"id": "input", "mandatory": True, "status": "indeterminate"},
            {"id": "record_isolation", "mandatory": False, "status": "not_verified"},
        ]

        self.assertFalse(compliant(rows))
        self.assertEqual(verdict({"criteria": rows}), "indeterminate")

    def test_open_failure_cannot_be_masked_by_closed_frame_evidence(self):
        ids = ("frame_state", "regular_arrangement", "door_composition",
               "stable_state", "no_required_clock", "influence_coverage")
        closed_rows = [
            {"id": identifier, "mandatory": True, "status": "satisfied",
             "observed": {"state": "closed"}, "diagnostic": "closed evidence"}
            for identifier in ids
        ]
        open_rows = [
            {"id": identifier, "mandatory": True,
             "status": "failed" if identifier == "frame_state" else "indeterminate",
             "observed": {"state": "open"}}
            for identifier in ids
        ]
        closed = {"criteria": closed_rows}
        geometry = {"expected_state": "open", "criteria": open_rows, "coverage": {"status": "observed", "chunks_ready": True}}

        evaluated = criteria(geometry, closed, {"status": "terminated"}, True,
                             {"restorable_observed_scope": True, "uncovered_components": []})

        self.assertEqual(next(row for row in evaluated if row["id"] == "regular_arrangement")["status"], "satisfied")
        self.assertEqual(next(row for row in evaluated if row["id"] == "frame_state")["status"], "failed")
        self.assertFalse(compliant(evaluated))
        self.assertEqual(verdict({"criteria": evaluated}), "failed")

    def test_verdict_keeps_infrastructure_failure_distinct_and_highest_priority(self):
        criteria_rows = [{"id": "cycle", "mandatory": True, "status": "failed"}]

        self.assertEqual(verdict({"criteria": criteria_rows}), "failed")
        self.assertEqual(verdict({"criteria": criteria_rows, "infrastructure_error": {"kind": "OSError"}}),
                         "infrastructure_error")

    def test_influence_requires_relevant_memory_and_observation_coverage(self):
        row = {"id": "influence_coverage", "mandatory": True, "status": "indeterminate"}
        geometry = {"expected_state": "closed", "criteria": [row], "coverage": {"status": "observed", "chunks_ready": True}}
        memory = {"restorable_observed_scope": True, "uncovered_components": []}
        positive = criteria(geometry, geometry, {"status": "terminated"}, True, memory)
        self.assertTrue(compliant(positive))
        for uncovered in ({}, {"restorable_observed_scope": False, "uncovered_components": ["torch:burnout_history"]},
                          {"restorable_observed_scope": True, "uncovered_components": ["missing_runtime"]}):
            negative = criteria(geometry, geometry, {"status": "terminated"}, True, uncovered)
            self.assertFalse(compliant(negative))
            self.assertEqual(verdict({"criteria": negative}), "indeterminate")
        incomplete = {**geometry, "coverage": {"status": "indeterminate", "chunks_ready": False}}
        self.assertFalse(compliant(criteria(incomplete, incomplete, {"status": "terminated"}, True, memory)))
        self.assertFalse(compliant(criteria(geometry, geometry, {"status": "terminated"}, False, memory)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
