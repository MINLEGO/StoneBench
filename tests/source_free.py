"""Offline controls: the source-free checks used on real MCP responses must be able to fail."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from integration import RULES_REFERENCE, source_leaks
from verification_worker import sourced


class SourceFreeTests(unittest.TestCase):
    def test_leaks_are_found_in_every_position(self):
        self.assertEqual(source_leaks({"criteria": [{"id": "x", "sources": []}]}), ["$.criteria[0].sources"])
        self.assertEqual(source_leaks({"measurement_contract": {"volume_source_index": 1}}), ["$.measurement_contract.volume_source_index"])
        self.assertEqual(len(source_leaks({"task": {"rules_reference": RULES_REFERENCE}})), 2)
        self.assertEqual(len(source_leaks({"a": ["see https://github.com/MINLEGO/StoneBench/issues/4"]})), 1)
        self.assertEqual(len(source_leaks({"a": "revision AHj4eMT_keZ9"})), 1)
        for prose in ("Perimeter collision; Dummies index 9641", "Rules 23868 requires the union", "not an alpha restriction; source exception index 3852"):
            self.assertEqual(len(source_leaks({"observation": prose})), 1, prose)
        self.assertEqual(source_leaks({"criteria": [{"id": "frame_state", "expected": "closed", "observed": []}]}), [])
        self.assertEqual(source_leaks({"observed": {"x": 1024, "y": 80, "z": 1024, "block": "minecraft:quartz_block"}}), [])

    def test_verification_leaks_are_found_and_the_concise_form_passes(self):
        sourced = {"criteria": [{"id": "x", "sources": [{"source": "https://docs.google.com/document/d/1", "revision_id": "r", "locator": "1"}]}],
                   "measurements": {"opening_time": {"sources": [{"native_cache_sha256": "e4a01f6d47956291"}]}},
                   "boundaries": [{"geometry": {"criteria": [{"source_index": 5}]}}]}
        self.assertGreaterEqual(len(source_leaks(sourced)), 8)
        concise = {"verdict": "failed", "criteria": [{"id": "frame_state", "mandatory": True, "status": "failed"}],
                   "faults": [{"id": "frame_state", "status": "failed", "boundary": "open", "observed": [{"x": 1024, "y": 80, "z": 1024}], "diagnostic": "Snapshot occupancy"}],
                   "measurements": {"opening_time": {"status": "measured", "value": 6, "gaps": []}}}
        self.assertEqual(source_leaks(concise), [])

    def test_worker_reads_the_full_row_from_the_copy_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "stonebench").mkdir()
            rows = [{"operation_id": "a", "criteria": []}, {"operation_id": "b", "criteria": [{"id": "x", "sources": [1]}]}]
            (root / "stonebench/operations.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            self.assertEqual(sourced(root, {"operation_id": "b", "criteria": [{"id": "x"}]}), rows[1])
            with self.assertRaises(RuntimeError):
                sourced(root, {"operation_id": "missing"})


if __name__ == "__main__":
    unittest.main()
