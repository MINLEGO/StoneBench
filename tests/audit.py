"""Local verification audit: binding and completeness, without Minecraft or MCP."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.harness import audit

ATTEMPT, REQUEST, CHECKPOINT = "a" * 8, "r" * 8, "c" * 8
SOURCE = {"source": "https://example.test/rules", "revision_id": "rev", "locator_type": "native_character_index", "locator": "1606"}


def report(manifest):
    binding = {"attempt_id": ATTEMPT, "request_id": REQUEST, "checkpoint_id": CHECKPOINT, "manifest_sha256": manifest}
    return {"request_id": REQUEST, "checkpoint_id": CHECKPOINT, "manifest_sha256": manifest, "audit": binding,
            "status": "completed", "protocol_version": "v", "checkpoint_provenance": {"memory_coverage": {}},
            "copies": [{"mode": "repeater"}], "limits": {"x": 1}, "comparison_policy": "exact", "cycles_executed": 1,
            "stop_cause": "first_return_to_state0", "verdict": "conforms_to_alpha", "conforms_to_alpha": True,
            "working_construction_preserved": True, "working_differences": [],
            "criteria": [{"id": "fixed_passage", "mandatory": True, "status": "satisfied", "sources": [SOURCE]}],
            "boundaries": [{"mode": "repeater", "operation": {"operation_id": "o"}, "snapshot": {"world_time": 7},
                            "criteria": [{"id": "fixed_passage", "status": "satisfied"}]}],
            "measurements": {"transitions": [{"state": "open", "opening_time": {"value": 6}}]}}


def visible(full):
    """What the MCP status shows: same decisive fields, boundary snapshots replaced by artifact references."""
    shown = deepcopy(full)
    shown.pop("audit")
    shown["full_report"] = {"artifact_id": "x"}
    return shown


class LocalAudit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        control = self.root / "stonebench"
        (control / "checkpoints" / CHECKPOINT).mkdir(parents=True)
        (control / "verifications" / REQUEST).mkdir(parents=True)
        (control / "attempt.json").write_text(json.dumps({"attempt_id": ATTEMPT}))
        manifest = control / "checkpoints" / CHECKPOINT / "manifest.json"
        manifest.write_text("{}")
        self.manifest = sha256(manifest.read_bytes()).hexdigest()
        self.write(report(self.manifest))

    def write(self, full, request=None):
        directory = self.root / "stonebench/verifications" / REQUEST
        (directory / "completed.json").write_text(json.dumps(full))
        (directory / "request.json").write_text(json.dumps(request or full["audit"]))

    def load(self, full=None):
        full = full or json.loads((self.root / "stonebench/verifications" / REQUEST / "completed.json").read_text())
        return audit.load(self.root, REQUEST, CHECKPOINT, visible(full))

    def test_complete_report_is_positive_and_bound(self):
        local = self.load()
        self.assertTrue(local["complete"], local["missing"])
        self.assertTrue(audit.positive(local))
        self.assertEqual((local["attempt_id"], local["request_id"], local["checkpoint_id"]), (ATTEMPT, REQUEST, CHECKPOINT))

    def test_absent_report_cannot_be_read(self):
        full = report(self.manifest)
        (self.root / "stonebench/verifications" / REQUEST / "completed.json").unlink()
        with self.assertRaises(audit.AuditError):
            self.load(full)

    def test_mismatched_identity_is_rejected(self):
        for key, value in (("attempt_id", "other"), ("request_id", "other"), ("checkpoint_id", "other"), ("manifest_sha256", "0" * 64)):
            full = report(self.manifest)
            full["audit"][key] = value
            self.write(full)
            with self.assertRaises(audit.AuditError, msg=key):
                self.load(full)
        full = report(self.manifest)
        full["checkpoint_id"] = "other"
        self.write(full)
        with self.assertRaises(audit.AuditError):
            self.load(full)

    def test_request_frozen_for_another_attempt_is_rejected(self):
        full = report(self.manifest)
        self.write(full, dict(full["audit"], attempt_id="other"))
        with self.assertRaises(audit.AuditError):
            self.load(full)

    def test_checkpoint_manifest_change_is_rejected(self):
        (self.root / "stonebench/checkpoints" / CHECKPOINT / "manifest.json").write_text('{"changed": true}')
        with self.assertRaises(audit.AuditError):
            self.load()

    def test_mcp_status_disagreement_is_rejected(self):
        full = report(self.manifest)
        shown = visible(full)
        for key, value in (("verdict", "failed"), ("conforms_to_alpha", False), ("measurements", {}), ("criteria", [])):
            with self.assertRaises(audit.AuditError, msg=key):
                audit.load(self.root, REQUEST, CHECKPOINT, dict(shown, **{key: value}))

    def test_incomplete_report_is_never_positive(self):
        def no_source(full): full["criteria"][0]["sources"] = []
        def no_locator(full): del full["criteria"][0]["sources"][0]["locator"]
        def no_criteria(full): full["criteria"] = []
        def artifact_snapshot(full): full["boundaries"][0]["snapshot"] = {"artifact_id": "x"}
        def no_boundaries(full): full["boundaries"] = []
        def no_measurements(full): full["measurements"] = {"transitions": []}
        def no_provenance(full): del full["checkpoint_provenance"]
        def no_transition_operation(full): del full["boundaries"][0]["operation"]
        def changed_working(full): full["working_construction_preserved"] = False
        def infrastructure(full): full["infrastructure_error"] = {"kind": "cancelled"}
        def running(full): full["status"] = "running"
        for damage in (no_source, no_locator, no_criteria, artifact_snapshot, no_boundaries, no_measurements,
                       no_provenance, no_transition_operation, changed_working, infrastructure, running):
            full = report(self.manifest)
            damage(full)
            self.write(full)
            local = self.load(full)
            self.assertFalse(local["complete"], damage.__name__)
            self.assertFalse(audit.positive(local), damage.__name__)

    def test_complete_nonconforming_report_is_not_positive(self):
        full = report(self.manifest)
        full.update(verdict="failed", conforms_to_alpha=False)
        self.write(full)
        local = self.load(full)
        self.assertTrue(local["complete"])
        self.assertFalse(audit.positive(local))


if __name__ == "__main__":
    unittest.main()
