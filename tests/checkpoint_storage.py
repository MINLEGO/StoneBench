"""Stopped-process restore transaction negative controls; no Minecraft fidelity claim."""
import json
from pathlib import Path
import tempfile
import unittest
import uuid
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from checkpoint_restore import apply_restore, file_map, write_json, digest, rollback_boot, recover_incomplete
from checkpoint_server import ensure_previous_child_absent


class RestoreTransactionChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="stonebench-checkpoint-transaction-")
        self.addCleanup(self.temporary.cleanup)
        self.server = Path(self.temporary.name).resolve()
        self.control = self.server / "stonebench"
        self.control.mkdir()
        (self.server / "world").mkdir()
        (self.server / "world" / "level.dat").write_bytes(b"old world")
        self.identifier, self.attempt, self.request_id = [str(uuid.uuid4()) for _ in range(3)]
        self.checkpoint = self.control / "checkpoints" / self.identifier
        (self.checkpoint / "world" / "region").mkdir(parents=True)
        (self.checkpoint / "world" / "level.dat").write_bytes(b"new exact clocks")
        (self.checkpoint / "world" / "region" / "r.0.0.mca").write_bytes(b"seven diamonds")
        write_json(self.control / "attempt.json", {"attempt_id": self.attempt})
        write_json(self.checkpoint / "context.json", {"attempt_id": self.attempt})
        write_json(self.checkpoint / "state.json", {"world_time": 20})
        write_json(self.checkpoint / "manifest.json", {"format": 1, "checkpoint_id": self.identifier,
                                                       "files": file_map(self.checkpoint)})
        self.request = {"checkpoint_id": self.identifier, "request_id": self.request_id,
                        "attempt_id": self.attempt, "manifest_sha256": digest(self.checkpoint / "manifest.json")}
        write_json(self.control / "restore-request.json", self.request)
        # Historical artifacts/checkpoints survive a whole-world restore.
        (self.control / "artifact.jsonl").write_bytes(b"history")

    def test_stages_swaps_keeps_old_world_and_history(self):
        before = file_map(self.checkpoint)
        marker = apply_restore(self.server)
        self.assertEqual(marker["status"], "awaiting_loaded_comparison")
        self.assertEqual((self.server / "world" / "level.dat").read_bytes(), b"new exact clocks")
        self.assertEqual((self.server / marker["previous_world"] / "level.dat").read_bytes(), b"old world")
        self.assertEqual(file_map(self.checkpoint), before)
        self.assertEqual((self.control / "artifact.jsonl").read_bytes(), b"history")
        self.assertFalse((self.control / "restore-request.json").exists())
        rollback_boot(self.server, self.request_id, "injected startup failure")
        self.assertEqual((self.server / "world" / "level.dat").read_bytes(), b"old world")
        self.assertFalse((self.control / "resume.json").exists())

    def test_corrupt_world_never_replaces_live_world(self):
        (self.checkpoint / "world" / "region" / "r.0.0.mca").write_bytes(b"eight diamonds")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            apply_restore(self.server)
        self.assertEqual((self.server / "world" / "level.dat").read_bytes(), b"old world")

    def test_altered_manifest_rejected_against_request_hash(self):
        (self.checkpoint / "manifest.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "manifest SHA-256"):
            apply_restore(self.server)

    def test_failed_swap_rolls_back_live_world(self):
        import os
        original = os.replace
        def replace(source, destination):
            if Path(source).name == "world-staged":
                raise OSError("injected installation failure")
            return original(source, destination)
        with patch("checkpoint_restore.os.replace", replace):
            with self.assertRaisesRegex(OSError, "installation failure"):
                apply_restore(self.server)
        self.assertEqual((self.server / "world" / "level.dat").read_bytes(), b"old world")
        failure = json.loads((self.control / "restore-history" / self.request_id / "failure.json").read_text())
        self.assertTrue(failure["old_world_restored"])
        self.assertFalse((self.control / "resume.json").exists())

    def test_unsafe_id_and_other_attempt_rejected(self):
        self.request["checkpoint_id"] = "../escape"
        write_json(self.control / "restore-request.json", self.request)
        with self.assertRaises(ValueError):
            apply_restore(self.server)
        self.request["checkpoint_id"] = self.identifier
        self.request["attempt_id"] = str(uuid.uuid4())
        write_json(self.control / "restore-request.json", self.request)
        with self.assertRaisesRegex(ValueError, "another attempt"):
            apply_restore(self.server)

    def test_process_crash_between_world_moves_recovers_backup(self):
        import os
        original = os.replace
        def replace(source, destination):
            if Path(source).name == "world-staged":
                raise SystemExit("injected abrupt supervisor death")
            return original(source, destination)
        with patch("checkpoint_restore.os.replace", replace):
            with self.assertRaises(SystemExit):
                apply_restore(self.server)
        self.assertFalse((self.server / "world").exists())
        recover_incomplete(self.server)
        self.assertEqual((self.server / "world" / "level.dat").read_bytes(), b"old world")
        self.assertFalse((self.control / "resume.json").exists())

    def test_process_crash_after_marker_finishes_bookkeeping_once(self):
        import os
        original = os.replace
        def replace(source, destination):
            if Path(source).name == "restore-request.json":
                raise SystemExit("injected death after durable marker")
            return original(source, destination)
        write_json(self.control / "restore-response.json", {"request_id": self.request_id})
        with patch("checkpoint_restore.os.replace", replace):
            with self.assertRaises(SystemExit):
                apply_restore(self.server)
        recover_incomplete(self.server)
        recover_incomplete(self.server)
        self.assertEqual((self.server / "world" / "level.dat").read_bytes(), b"new exact clocks")
        self.assertTrue((self.control / "resume.json").exists())
        self.assertFalse((self.control / "restore-request.json").exists())
        self.assertFalse((self.control / "restore-response.json").exists())
        self.assertTrue((self.control / "restore-history" / self.request_id / "request.json").exists())

    def test_uncertain_launch_marker_refuses_before_recovery(self):
        write_json(self.control / "child-starting.json", {"status": "child_launch_pending"})
        before = file_map(self.server / "world")
        with self.assertRaisesRegex(RuntimeError, "ownership uncertain"):
            ensure_previous_child_absent(self.server)
        self.assertEqual(file_map(self.server / "world"), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
