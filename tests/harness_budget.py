import json
from pathlib import Path
import tempfile
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.harness.budget import Budget, Ledger
from inspect_ai.model import ModelUsage


class HarnessBudgetTests(unittest.TestCase):
    def test_reserve_switches_before_next_construction_and_never_reverts(self):
        ledger = Ledger(Budget(1000, 100, 100, 200, 50))
        self.assertEqual(ledger.before_call(100)["phase"], "construction")
        ledger.record(ModelUsage(input_tokens=100, output_tokens=300, total_tokens=400, reasoning_tokens=200), .01)
        notice = ledger.before_call(100)
        self.assertEqual(notice["phase"], "finalization")
        self.assertEqual(notice["used_tokens"], 400)
        self.assertEqual(notice["reserve_estimate"], 450)
        ledger.record(ModelUsage(input_tokens=100, output_tokens=250, total_tokens=350, reasoning_tokens=200), .02)
        self.assertEqual(ledger.total_tokens, 750, "reasoning detail must not be charged twice")
        self.assertEqual(ledger.before_call(0)["phase"], "finalization")

    def test_missing_usage_never_becomes_zero(self):
        ledger = Ledger(Budget(1000, 100, 100, 200, 50))
        ledger.record(None, .01)
        self.assertIsNone(ledger.total_tokens)
        self.assertEqual(ledger.before_call(1)["transition_reason"], "usage_unavailable")
        ledger.record(ModelUsage(input_tokens=1, output_tokens=1, total_tokens=2), .02)
        self.assertEqual(ledger.known_tokens, 2)
        self.assertIsNone(ledger.total_tokens)

    def test_observed_overshoot_and_long_reasoning_preserved(self):
        ledger = Ledger(Budget(1000, 100, 100, 200, 50))
        ledger.before_call(900)
        ledger.record(ModelUsage(input_tokens=900, output_tokens=800, total_tokens=1700, reasoning_tokens=790), .03)
        self.assertEqual(ledger.total_tokens, 1700)
        self.assertTrue(ledger.calls[-1]["budget_exceeded_observed"])
        self.assertFalse(ledger.can_continue())
        self.assertEqual(ledger.calls[-1]["usage"]["reasoning_tokens"], 790)

    def test_cached_input_reported_total_used(self):
        ledger = Ledger(Budget(1000, 100, 100, 200, 50))
        ledger.record(ModelUsage(input_tokens=10, input_tokens_cache_read=90, output_tokens=20,total_tokens=120), .01)
        self.assertEqual(ledger.total_tokens, 120)

    def test_partial_usage_fields_remain_unavailable(self):
        ledger = Ledger(Budget(1000, 100, 100, 200, 50))
        ledger.record(ModelUsage(output_tokens=7), .01)
        self.assertIsNone(ledger.total_tokens)
        self.assertIsNone(ledger.calls[0]["usage"]["input_tokens"])
        self.assertIsNone(ledger.calls[0]["usage"]["total_tokens"])

    def test_validation_and_final_call_safety(self):
        with self.assertRaises(ValueError):
            Budget(10, 1, 10, 0, 0)
        ledger = Ledger(Budget(1000, 100, 100, 200, 50, final_calls=1))
        ledger.finalize("manual")
        ledger.before_call(1)
        self.assertFalse(ledger.can_continue())

    def test_lost_request_counts_against_budget_but_never_as_usage(self):
        ledger = Ledger(Budget(1000, 100, 100, 200, 50))
        ledger.record_lost(600, .5, "APIConnectionError", "a", "b")
        self.assertIsNone(ledger.total_tokens)
        self.assertEqual(ledger.known_tokens, 0)
        self.assertEqual(ledger.committed_tokens, 600)
        self.assertTrue(ledger.usage_complete, "a lost request is not a response lacking usage")
        notice = ledger.before_call(100)
        self.assertEqual((notice["lost_requests"], notice["lost_upper_bound_tokens"], notice["used_tokens"]), (1, 600, None))
        self.assertEqual(notice["phase"], "finalization", "600 bound + forecast + reserve exceeds the total")


if __name__ == "__main__":
    unittest.main()
