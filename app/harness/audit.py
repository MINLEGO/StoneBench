"""Scorer-side read of the complete local verification audit, independent of agent-visible MCP responses."""
from hashlib import sha256
import json
from pathlib import Path

# Report fields the scorer needs to agree on with the agent-visible status; a divergence is incoherent evidence.
COHERENT = ("request_id", "checkpoint_id", "manifest_sha256", "verdict", "conforms_to_alpha", "stop_cause", "cycles_executed")
SEVERITY = ("satisfied", "not_verified", "indeterminate", "failed")
SOURCE_FIELDS = ("source", "revision_id", "locator")


class AuditError(Exception):
    """Absent, unreadable or mismatched audit: no result can be derived from it."""


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AuditError(f"Audit file unavailable: {path.name}") from exc


def outcomes(rows):
    """The agent's per-criterion outcome: its worst status over every executed boundary."""
    result = {}
    for row in rows:
        current = result.setdefault(row["id"], {"id": row["id"], "mandatory": row["mandatory"], "status": row["status"]})
        if SEVERITY.index(row["status"]) > SEVERITY.index(current["status"]):
            current["status"] = row["status"]
    return list(result.values())


FAULT_KEYS = ("id", "status", "mode", "boundary", "expected", "observed", "diagnostic")
EVIDENCE_KEYS = ("sources", "movements", "excluded", "conditional_roles")


def faults(rows, report):
    """The agent's fault list: mandatory rows not satisfied, minus citations. Evidence already at the root of the answer is
    not repeated, and the same fault over several cycles is one entry listing them (the first `observed` is kept)."""
    difference = report.get("first_difference")
    if isinstance(difference, dict):
        difference = {key: item for key, item in difference.items() if key not in ("mode", "boundary", "first_tick")}
    listed = {}
    for row in rows:
        if row["mandatory"] and row["status"] != "satisfied":
            fault = {key: row[key] for key in FAULT_KEYS if key in row}
            if fault.get("observed") is not None and fault["observed"] in (report.get("recurrence_comparisons"), difference):
                del fault["observed"]
            entry = listed.setdefault(json.dumps({key: item for key, item in fault.items() if key != "observed"}, sort_keys=True), fault)
            if "cycle" in row:
                entry.setdefault("cycles", []).append(row["cycle"])
    return list(listed.values())


def lean(value):
    """Measurements as the agent sees them: evidence lists (citations, per-movement samples, exclusions) omitted."""
    if isinstance(value, dict):
        return {key: lean(item) for key, item in value.items() if key not in EVIDENCE_KEYS}
    return [lean(item) for item in value] if isinstance(value, list) else value


def _sources(rows):
    return isinstance(rows, list) and bool(rows) and all(isinstance(row, dict) and all(row.get(field) for field in SOURCE_FIELDS) for row in rows)


def _integer(value):
    return type(value) is int


def _stamp(value):
    return isinstance(value, dict) and _integer(value.get("world_time"))


def _movements(rows):
    return isinstance(rows, list) and bool(rows) and all(isinstance(row, dict) and _stamp(row.get("start")) for row in rows)


def _metric(metric, provenance, explained=True):
    """A measured value carries its number and timestamped provenance; an unmeasured one states why (gaps), never silently.

    Only top-level timing summaries may omit gaps (explained=False): their gaps live in the transitions."""
    if not isinstance(metric, dict) or not _sources(metric.get("sources")) or not isinstance(metric.get("gaps", []), list):
        return False
    if metric.get("status") == "measured":
        return type(metric.get("value")) in (int, float) and all(_stamp(metric.get(key)) for key in provenance)
    return metric.get("status") == "indeterminate" and metric.get("value") is None and (bool(metric.get("gaps")) or not explained)


def _transition(row):
    if not isinstance(row, dict):
        return False
    timing = "opening_time" if "opening_time" in row else "closing_time"
    return (row.get("mode") in ("repeater", "direct") and row.get("purpose")
            and _metric(row.get("dynamic_volume"), ()) and ("opening_time" in row) != ("closing_time" in row)
            and _metric(row.get(timing), ("interaction", "signal_at_input_block", "rest_recognition"))
            and isinstance(row.get("movements"), list)
            and (row[timing].get("status") != "measured" or _movements(row["movements"])) and _integer(row.get("transition_ticks"))
            and row.get("objectives_combined") is False)


def missing(report):
    """Mandatory audit evidence absent from a completed report; any entry forbids a positive result."""
    gaps = [name for name in ("protocol_version", "checkpoint_provenance", "copies", "limits", "comparison_policy")
            if not report.get(name)]
    if report.get("status") != "completed":
        gaps.append("status")
    if report.get("working_construction_preserved") is not True or report.get("working_differences"):
        gaps.append("working_construction_preserved")
    if report.get("infrastructure_error"):
        gaps.append("infrastructure_error")
    criteria = report.get("criteria")
    if not criteria or not isinstance(criteria, list):
        gaps.append("criteria")
    else:
        for row in criteria:
            if not isinstance(row, dict) or not _sources(row.get("sources")):
                gaps.append(f"criteria.{row.get('id') if isinstance(row, dict) else row}.sources")
    boundaries = report.get("boundaries")
    if not boundaries or not isinstance(boundaries, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("snapshot"), dict) or not _integer(row["snapshot"].get("world_time"))
            or not isinstance(row.get("operation"), dict) or not row["operation"] or not row.get("criteria") for row in boundaries):
        gaps.append("boundaries")
    measurements = report.get("measurements")
    transitions = measurements.get("transitions") if isinstance(measurements, dict) else None
    if (not transitions or not isinstance(transitions, list) or not all(_transition(row) for row in transitions)
            or not any(row["mode"] == "repeater" for row in transitions)
            or not _metric(measurements.get("dynamic_volume"), ())
            or not all(_metric(measurements.get(key), (), False) for key in ("opening_time", "closing_time"))):
        gaps.append("measurements")
    return gaps


def load(server_root, request_id, checkpoint_id, visible):
    try:
        return _load(server_root, request_id, checkpoint_id, visible)
    except (AttributeError, TypeError, KeyError, ValueError, OSError) as exc:
        raise AuditError(f"Malformed audit: {exc!r}") from exc


def _load(server_root, request_id, checkpoint_id, visible):
    """Read `<server_root>/stonebench/verifications/<request_id>/completed.json`.

    Binding comes only from files written by the controller/checkpoint store: the local attempt identity,
    the request frozen before the worker ran and the checkpoint manifest. `visible` is the MCP status
    the scorer polled; it is cross-checked but never trusted instead of the audit.
    """
    control = Path(server_root) / "stonebench"
    directory = control / "verifications" / request_id
    attempt = _json(control / "attempt.json").get("attempt_id")
    request, report = _json(directory / "request.json"), _json(directory / "completed.json")
    manifest = sha256((control / "checkpoints" / checkpoint_id / "manifest.json").read_bytes()).hexdigest() \
        if (control / "checkpoints" / checkpoint_id / "manifest.json").is_file() else None
    expected = {"attempt_id": attempt, "request_id": request_id, "checkpoint_id": checkpoint_id, "manifest_sha256": manifest}
    if not attempt or not manifest:
        raise AuditError("Local attempt or checkpoint identity unavailable")
    for name, document in (("request", request), ("completed audit", report.get("audit"))):
        if any(not isinstance(document, dict) or document.get(key) != value for key, value in expected.items()):
            raise AuditError(f"Audit {name} is not bound to the exact attempt, request and checkpoint")
    for key in ("request_id", "checkpoint_id", "manifest_sha256"):
        if report.get(key) != expected[key]:
            raise AuditError(f"Audit report {key} mismatch")
    for key in COHERENT:
        if report.get(key) != visible.get(key):
            raise AuditError(f"Audit and MCP verification status disagree on {key}")
    # The MCP status is the concise form of the local rows: outcomes, faults and measurements are derived, never trusted.
    rows = report.get("criteria", [])  # absent in an infrastructure fallback: no rows, reported as missing evidence below
    if not isinstance(rows, list) or visible.get("criteria") != outcomes(rows) or visible.get("faults") != faults(rows, report):
        raise AuditError("Audit and MCP verification status disagree on criteria")
    if visible.get("measurements") != lean(report.get("measurements")):
        raise AuditError("Audit and MCP verification status disagree on measurements")
    gaps = missing(report)
    return {"report": report, "complete": not gaps, "missing": gaps,
            "path": str(directory / "completed.json"), "sha256": sha256((directory / "completed.json").read_bytes()).hexdigest(),
            **expected}


def positive(audit):
    report = audit["report"]
    return audit["complete"] and report.get("verdict") == "conforms_to_alpha" and report.get("conforms_to_alpha") is True
