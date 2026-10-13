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
def SOURCE():
    return {"source": "https://example.test/rules", "revision_id": "rev", "locator_type": "native_character_index", "locator": "1606"}


def volume():
    return {"status": "indeterminate", "value": None, "gaps": ["conditional_role_exclusion_changes_dimensions"], "sources": [SOURCE()]}


def summary(status):
    return {"status": status, "value": 6 if status == "measured" else None, "sources": [SOURCE()]}


def transition(mode, timing):
    stamp = {"world_time": 3, "simulation_index": 1, "tick_index": 1, "phase": "tick", "operation_order": 0}
    return {"mode": mode, "purpose": "reference", "dynamic_volume": volume(), "movements": [{"start": stamp}], "transition_ticks": 9,
            "objectives_combined": False,
            timing: {"status": "measured", "value": 6, "interaction": stamp, "signal_at_input_block": stamp,
                     "rest_recognition": {"world_time": 9}, "gaps": [], "sources": [SOURCE()]}}


def report(manifest):
    binding = {"attempt_id": ATTEMPT, "request_id": REQUEST, "checkpoint_id": CHECKPOINT, "manifest_sha256": manifest}
    return {"request_id": REQUEST, "checkpoint_id": CHECKPOINT, "manifest_sha256": manifest, "audit": binding,
            "status": "completed", "protocol_version": "v", "checkpoint_provenance": {"memory_coverage": {}},
            "copies": [{"mode": "repeater"}], "limits": {"x": 1}, "comparison_policy": "exact", "cycles_executed": 1,
            "stop_cause": "first_return_to_state0", "verdict": "conforms_to_alpha", "conforms_to_alpha": True,
            "working_construction_preserved": True, "working_differences": [],
            "criteria": [{"id": "fixed_passage", "mandatory": True, "status": "satisfied", "sources": [SOURCE()]}],
            "boundaries": [{"mode": "repeater", "operation": {"operation_id": "o"}, "snapshot": {"world_time": 7},
                            "criteria": [{"id": "fixed_passage", "status": "satisfied"}]}],
            "measurements": {"dynamic_volume": volume(), "opening_time": summary("measured"), "closing_time": summary("measured"),
                             "transitions": [transition("repeater", "opening_time"), transition("direct", "closing_time")]}}


def without_evidence(value):
    if isinstance(value, dict):
        return {key: without_evidence(item) for key, item in value.items() if key not in ("sources", "movements", "excluded", "conditional_roles")}
    return [without_evidence(item) for item in value] if isinstance(value, list) else value


def visible(full):
    """What the MCP status shows (written independently of audit.outcomes): decisive fields, one outcome per criterion id,
    mandatory faults without citations, measurements without evidence lists. No full_report identifier exists."""
    shown = {key: deepcopy(full.get(key)) for key in audit.COHERENT}
    rows = full.get("criteria") if isinstance(full.get("criteria"), list) and all(isinstance(row, dict) for row in full["criteria"]) else []
    order = ("satisfied", "not_verified", "indeterminate", "failed")
    outcomes = {}
    for row in rows:
        outcome = outcomes.setdefault(row["id"], {"id": row["id"], "mandatory": row["mandatory"], "status": row["status"]})
        outcome["status"] = max(outcome["status"], row["status"], key=order.index)
    shown["criteria"] = list(outcomes.values())
    keys = ("id", "status", "mode", "boundary", "expected", "observed", "diagnostic")
    shown["faults"] = []
    for row in rows:
        if row["mandatory"] and row["status"] != "satisfied":
            fault = {key: row[key] for key in keys if key in row}
            located = full.get("first_difference")
            located = {k: v for k, v in located.items() if k not in ("mode", "boundary", "first_tick")} if isinstance(located, dict) else None
            if fault.get("observed") is not None and fault["observed"] in (full.get("recurrence_comparisons"), located):
                del fault["observed"]  # already shown at the root
            without = lambda value: {k: v for k, v in value.items() if k not in ("cycles", "observed")}
            twin = next((other for other in shown["faults"] if without(other) == without(fault)), None)
            if twin is None:
                shown["faults"].append(twin := fault)
            if "cycle" in row:
                twin.setdefault("cycles", []).append(row["cycle"])
    if "measurements" in full:
        shown["measurements"] = without_evidence(full["measurements"])
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
        """The controller-owned request stays pristine unless a test alters it on purpose."""
        directory = self.root / "stonebench/verifications" / REQUEST
        (directory / "completed.json").write_text(json.dumps(full))
        (directory / "request.json").write_text(json.dumps(request or report(self.manifest)["audit"]))

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
        def null_world_time(full): full["boundaries"][0]["snapshot"]["world_time"] = None
        def float_world_time(full): full["boundaries"][0]["snapshot"]["world_time"] = 7.5
        def bare_transition(full): full["measurements"]["transitions"] = [{"mode": "repeater"}]
        def no_repeater(full): full["measurements"]["transitions"] = full["measurements"]["transitions"][1:]
        def no_timing_provenance(full): full["measurements"]["transitions"][0]["opening_time"]["signal_at_input_block"] = None
        def no_rest_recognition(full): del full["measurements"]["transitions"][0]["opening_time"]["rest_recognition"]
        def unexplained_timing(full): full["measurements"]["transitions"][0]["opening_time"].update(status="indeterminate", value=None, gaps=[])
        def timing_without_sources(full): full["measurements"]["transitions"][0]["opening_time"]["sources"] = []
        def volume_without_sources(full): del full["measurements"]["transitions"][0]["dynamic_volume"]["sources"]
        def unexplained_volume(full): full["measurements"]["transitions"][1]["dynamic_volume"]["gaps"] = []
        def summary_indeterminate_value(full): full["measurements"]["opening_time"] = {"status": "measured", "value": None, "sources": [SOURCE()]}
        def no_summary(full): del full["measurements"]["closing_time"]
        def fused_objectives(full): full["measurements"]["transitions"][0]["objectives_combined"] = True
        def volume_no_gaps_key(full): del full["measurements"]["dynamic_volume"]["gaps"]
        def volume_empty_gaps(full): full["measurements"]["dynamic_volume"]["gaps"] = []
        def transition_volume_no_gaps_key(full): del full["measurements"]["transitions"][0]["dynamic_volume"]["gaps"]
        def no_movements(full): full["measurements"]["transitions"][0]["movements"] = []
        def junk_movements(full): full["measurements"]["transitions"][0]["movements"] = [1, "x"]
        def movement_without_start_time(full): full["measurements"]["transitions"][0]["movements"] = [{"start": {"world_time": None}}]
        def interaction_without_time(full): full["measurements"]["transitions"][0]["opening_time"]["interaction"] = {"world_time": None}
        def rest_without_time(full): full["measurements"]["transitions"][0]["opening_time"]["rest_recognition"] = {"world_time": None}
        def signal_not_a_stamp(full): full["measurements"]["transitions"][0]["opening_time"]["signal_at_input_block"] = "t"
        def boolean_value(full): full["measurements"]["transitions"][0]["opening_time"]["value"] = True
        for damage in (volume_no_gaps_key, volume_empty_gaps, transition_volume_no_gaps_key, no_movements, junk_movements,
                       movement_without_start_time, interaction_without_time, rest_without_time, signal_not_a_stamp,
                       boolean_value, no_source, no_locator, no_criteria, artifact_snapshot, no_boundaries, no_measurements,
                       no_provenance, no_transition_operation, changed_working, infrastructure, running,
                       null_world_time, float_world_time, bare_transition, no_repeater, no_timing_provenance,
                       no_rest_recognition, unexplained_timing, timing_without_sources, volume_without_sources,
                       unexplained_volume, summary_indeterminate_value, no_summary, fused_objectives):
            full = report(self.manifest)
            damage(full)
            self.write(full)
            local = self.load(full)
            self.assertFalse(local["complete"], damage.__name__)
            self.assertFalse(audit.positive(local), damage.__name__)

    def test_explained_indeterminate_measurement_stays_positive(self):
        """A conforming verdict may carry an unmeasured volume when its gaps are stated (as the live fixture does)."""
        full = report(self.manifest)
        full["measurements"]["transitions"][0]["opening_time"].update(status="indeterminate", value=None, gaps=["rest_not_established"])
        full["measurements"]["opening_time"] = summary("indeterminate")
        self.write(full)
        self.assertTrue(audit.positive(self.load(full)))

    def test_legitimate_variants_stay_positive(self):
        def float_value(full): full["measurements"]["transitions"][0]["opening_time"]["value"] = 6.0
        def closing_only(full):
            full["measurements"]["transitions"] = [transition("repeater", "closing_time")]
            full["measurements"]["opening_time"] = {"status": "indeterminate", "value": None, "sources": [SOURCE()]}
        def summaries_without_gaps(full):
            full["measurements"]["opening_time"] = summary("indeterminate")
            full["measurements"]["closing_time"] = summary("indeterminate")
        def explained_volume(full): full["measurements"]["dynamic_volume"]["gaps"] = ["conditional_role_exclusion_changes_dimensions"]
        def unmeasured_without_movements(full):
            full["measurements"]["transitions"][0]["movements"] = []
            full["measurements"]["transitions"][0]["opening_time"].update(status="indeterminate", value=None, gaps=["last_pertinent_movement_missing"])
        for variant in (float_value, closing_only, summaries_without_gaps, explained_volume, unmeasured_without_movements):
            full = report(self.manifest)
            variant(full)
            self.write(full)
            local = self.load(full)
            self.assertTrue(audit.positive(local), (variant.__name__, local["missing"]))

    def test_malformed_content_is_incomplete_and_never_positive(self):
        full = report(self.manifest)
        full["criteria"] = ["x"]  # no concise form can agree with rows that are not rows: an audit error, still never positive
        self.write(full)
        with self.assertRaises(audit.AuditError):
            self.load(full)
        for damage in (lambda full: full["criteria"][0].update(sources=["x"]),
                       lambda full: full.update(boundaries=["x"]), lambda full: full["measurements"].update(transitions=[1]),
                       lambda full: full.update(measurements="x")):
            full = report(self.manifest)
            damage(full)
            self.write(full)
            local = self.load(full)
            self.assertFalse(local["complete"])
            self.assertTrue(local["missing"])
            self.assertFalse(audit.positive(local))

    def test_concise_status_must_match_the_local_rows(self):
        """Outcomes, faults and measurements are re-derived from completed.json; the MCP form cannot overstate them."""
        full = report(self.manifest)
        stamp = {"id": "stable_state", "mandatory": True}
        full["criteria"] += [dict(stamp, status="satisfied", boundary="open", sources=[SOURCE()]),
                             dict(stamp, status="failed", boundary="closed", observed={"x": 1}, diagnostic="d", sources=[SOURCE()]),
                             {"id": "hallway_composition", "mandatory": False, "status": "not_verified", "sources": [SOURCE()]}]
        full.update(verdict="failed", conforms_to_alpha=False)
        self.write(full)
        shown = visible(full)
        self.assertEqual([row["status"] for row in shown["criteria"]], ["satisfied", "failed", "not_verified"])  # worst status per id
        self.assertEqual([row["boundary"] for row in shown["faults"]], ["closed"])
        self.assertTrue(audit.load(self.root, REQUEST, CHECKPOINT, shown)["complete"])
        for damage in (lambda value: value["criteria"][1].update(status="satisfied"), lambda value: value.update(faults=[]),
                       lambda value: value["faults"][0].update(diagnostic="other"), lambda value: value["criteria"].pop(),
                       lambda value: value["measurements"].update(opening_time={}), lambda value: value.pop("measurements"),
                       lambda value: value["measurements"].pop("dynamic_volume")):
            changed = deepcopy(shown)
            damage(changed)
            with self.assertRaises(audit.AuditError):
                audit.load(self.root, REQUEST, CHECKPOINT, changed)

    def test_faults_group_cycles_and_omit_evidence_shown_at_the_root(self):
        full = report(self.manifest)
        again = {"id": "continuable", "mandatory": True, "status": "indeterminate", "mode": "repeater", "boundary": "closed", "diagnostic": "d", "sources": [SOURCE()]}
        difference = {"path": "blocks"}
        full["criteria"] += [dict(again, cycle=1, observed={"rest": 1}), dict(again, cycle=2, observed={"rest": 2}), dict(again, cycle=2, boundary="open"),
                             {"id": "recurrence", "mandatory": True, "status": "failed", "observed": [{"cycle": 1}], "diagnostic": "d", "sources": [SOURCE()]},
                             {"id": "mode_equivalence_open", "mandatory": True, "status": "failed", "observed": difference, "diagnostic": "d", "sources": [SOURCE()]},
                             {"id": "mode_equivalence_closed", "mandatory": True, "status": "failed", "observed": {"path": "other"}, "diagnostic": "d", "sources": [SOURCE()]}]
        full["recurrence_comparisons"] = [{"cycle": 1}]
        full["first_difference"] = dict(difference, mode="direct", boundary="open", first_tick=9)
        full.update(verdict="failed", conforms_to_alpha=False)
        self.write(full)
        shown = visible(full)
        self.assertEqual([(row["id"], row.get("boundary"), row.get("cycles")) for row in shown["faults"]],
                         [("continuable", "closed", [1, 2]), ("continuable", "open", [2]), ("recurrence", None, None),
                          ("mode_equivalence_open", None, None), ("mode_equivalence_closed", None, None)])
        self.assertEqual(shown["faults"][0]["observed"], {"rest": 1})  # the first observed is kept
        self.assertEqual(["observed" in row for row in shown["faults"][2:]], [False, False, True])
        self.assertTrue(audit.load(self.root, REQUEST, CHECKPOINT, shown)["complete"])  # the derivation agrees
        for damage in (lambda value: value["faults"][0].update(cycles=[1]), lambda value: value["faults"][3].update(observed={"path": "blocks"}),
                       lambda value: value["faults"][0].update(observed={"rest": 2})):
            changed = deepcopy(shown)
            damage(changed)
            with self.assertRaises(audit.AuditError):
                audit.load(self.root, REQUEST, CHECKPOINT, changed)

    def test_infrastructure_fallback_without_criteria_is_missing_evidence_not_an_error(self):
        """The heartbeat-lost fallback has no criteria, boundaries or measurements: incomplete, never positive, never an audit error."""
        full = {key: report(self.manifest)[key] for key in ("request_id", "checkpoint_id", "manifest_sha256", "audit")}
        full.update(status="completed", verdict="infrastructure_error", conforms_to_alpha=False, stop_cause="owner_heartbeat_lost",
                    infrastructure_error="Supervisor heartbeat absent")
        self.write(full)
        shown = dict(visible(full), criteria=[], faults=[])
        local = audit.load(self.root, REQUEST, CHECKPOINT, shown)
        self.assertFalse(local["complete"])
        self.assertIn("criteria", local["missing"])
        self.assertFalse(audit.positive(local))
        with self.assertRaises(audit.AuditError):
            audit.load(self.root, REQUEST, CHECKPOINT, dict(shown, criteria=[{"id": "x", "mandatory": True, "status": "satisfied"}]))

    def test_unreadable_or_unbound_file_is_an_audit_error(self):
        full = report(self.manifest)
        full["audit"] = "x"
        self.write(full)
        with self.assertRaises(audit.AuditError):
            self.load(full)
        (self.root / "stonebench/verifications" / REQUEST / "completed.json").write_text("[]")
        with self.assertRaises(audit.AuditError):
            audit.load(self.root, REQUEST, CHECKPOINT, visible(report(self.manifest)))

    def test_complete_nonconforming_report_is_not_positive(self):
        full = report(self.manifest)
        full.update(verdict="failed", conforms_to_alpha=False)
        self.write(full)
        local = self.load(full)
        self.assertTrue(local["complete"])
        self.assertFalse(audit.positive(local))


if __name__ == "__main__":
    unittest.main()
