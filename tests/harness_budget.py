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
        self.assertEqual(notice["reserve_estimate"], 400 + 300 + 50, "the forecast starts from the reported 400-token total")
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

    def test_forecast_grows_from_last_reported_total_and_reserve_follows(self):
        ledger = Ledger(Budget(10**6, 100, 100, 200, 50))
        first = ledger.before_call(5000)
        self.assertEqual(first["context_estimate"], 5000, "no usage yet: raw bytes, 1:1")
        self.assertIsNone(first["observed_bytes_per_token"])
        ledger.record(ModelUsage(input_tokens=2000, output_tokens=300, total_tokens=2300), .01)
        notice = ledger.before_call(5000 + 4001)
        self.assertEqual(notice["context_estimate"], 2300 + 2001, "growth 4001 bytes at 2 bytes/token, rounded up")
        self.assertEqual(notice["reserve_estimate"], 2300 + 2001 + 300 + 50)
        self.assertEqual((notice["context_bytes"], notice["observed_bytes_per_token"]), (9001, 2.5))
        ledger.record(ModelUsage(input_tokens=3000, output_tokens=100, total_tokens=3100), .01)
        self.assertEqual(ledger.before_call(100)["context_estimate"], 3100, "a shrinking context adds nothing")

    def test_large_tool_result_moves_the_next_call_into_finalization(self):
        ledger = Ledger(Budget(2000000, 32768, 8192, 57344, 32768, 8))
        ledger.before_call(100000)
        ledger.record(ModelUsage(input_tokens=300000, output_tokens=100000, total_tokens=400000), .01)
        self.assertEqual(ledger.before_call(102000)["phase"], "construction")
        ledger.record(ModelUsage(input_tokens=300000, output_tokens=100000, total_tokens=400000), .01)
        notice = ledger.before_call(702000)
        self.assertEqual(notice["context_estimate"], 400000 + 300000)
        self.assertEqual((notice["phase"], notice["transition_reason"]), ("finalization", "next_construction_call_would_enter_reserve"))

    def test_unreported_usage_falls_back_to_raw_bytes_and_finalizes(self):
        for usage in (None, ModelUsage(input_tokens=10, output_tokens=5)):
            ledger = Ledger(Budget(10**6, 100, 100, 200, 50))
            ledger.before_call(300)
            ledger.record(usage, .01)
            notice = ledger.before_call(800)
            self.assertEqual(notice["context_estimate"], 800)
            self.assertEqual(notice["transition_reason"], "usage_unavailable")

    def test_new_budget_fields_must_be_positive_integers(self):
        for field in ("bytes_per_token", "context_window_tokens"):
            with self.assertRaises(ValueError):
                Budget(1000, 100, 100, 200, 50, **{field: 0})

    def test_window_triggers_finalization_before_the_final_request_cannot_fit(self):
        budget = Budget(10**9, 1000, 500, 500, 100, context_window_tokens=10000)
        ledger = Ledger(budget)
        ledger.before_call(100)
        ledger.record(ModelUsage(input_tokens=6000, output_tokens=200, total_tokens=6200), .01)
        self.assertEqual(ledger.before_call(100)["phase"], "construction", "6200 + 1000 + 1000 + 100 fits 10000")
        ledger.record(ModelUsage(input_tokens=7800, output_tokens=200, total_tokens=8000), .01)
        notice = ledger.before_call(100)
        self.assertEqual((notice["phase"], notice["transition_reason"]), ("finalization", "next_construction_call_would_exceed_context_window"))
        self.assertTrue(budget.fits_window(9000, 1000))
        self.assertFalse(budget.fits_window(9001, 1000))

    def test_observed_bytes_per_token_counts_cached_input(self):
        ledger = Ledger(Budget(10**6, 100, 100, 200, 50))
        ledger.before_call(5000)
        ledger.record(ModelUsage(input_tokens=3, input_tokens_cache_read=997, output_tokens=100, total_tokens=1100), .01)
        self.assertEqual(ledger.before_call(5000)["observed_bytes_per_token"], 5.0)


if __name__ == "__main__":
    unittest.main()
