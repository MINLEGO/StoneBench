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
        self.assertEqual(source_leaks({"criteria": [{"id": "frame_state", "expected": "closed", "observed": []}]}), [])

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
