"""Alpha report decisions. Raw archives retain clocks, adapters, typed NBT and queue order."""
from copy import deepcopy

MAX_TRANSITION_TICKS = 36000
DERIVED_MAXIMUM_TICKS = 432000
VERSION = "checkpoint-alpha-2026-10-12"


def first_difference(left, right, path="$"):
    if type(left) is not type(right):
        return {"field": path, "expected": left, "observed": right}
    if isinstance(left, dict):
        for key in sorted(left.keys() | right.keys()):
            if key not in left or key not in right:
                return {"field": path + "." + key, "expected": left.get(key), "observed": right.get(key)}
            difference = first_difference(left[key], right[key], path + "." + key)
            if difference:
                return difference
    elif isinstance(left, list):
        if len(left) != len(right):
            return {"field": path + ".length", "expected": len(left), "observed": len(right)}
        for index, (a, b) in enumerate(zip(left, right)):
            difference = first_difference(a, b, f"{path}[{index}]")
            if difference:
                return difference
    elif left != right:
        return {"field": path, "expected": left, "observed": right}
    return None


def construction(snapshot):
    # Complete observations grow their air sampling set. Absent sampled air is
    # implicit air, never permission to drop a nonair block or an internal field.
    value = deepcopy(snapshot["construction"])
    value["blocks"] = {p: b for p, b in value["blocks"].items()
                       if b["block"] != "minecraft:air" or b.get("inventory") or b.get("nbt") or b.get("runtime")}
    return value


def criteria(geometry, closed, rest, trace_complete):
    rows = deepcopy(geometry["criteria"])
    initial = {row["id"]: row for row in closed["criteria"]}
    for row in rows:
        identifier = row["id"]
        if identifier in ("regular_arrangement", "door_composition") and geometry["expected_state"] == "open":
            row["status"] = initial[identifier]["status"]
            row["diagnostic"] = "Closed frame evidence from this same checkpoint mechanism: " + initial[identifier]["diagnostic"]
            row["closed_frame_evidence"] = initial[identifier]["observed"]
        if identifier in ("stable_state", "no_required_clock"):
            row["status"] = "satisfied" if rest["status"] == "terminated" else "failed" if rest["status"] == "limit_reached" else "indeterminate"
            row["observed"] = rest
            row["diagnostic"] = "Bounded functional rest proof; no universal indefinite stability claim."
        if identifier == "influence_coverage":
            row["status"] = "satisfied" if trace_complete and rest["status"] == "terminated" else "indeterminate"
            row["observed"] = {"complete_real_tick_trace": trace_complete, "rest": rest}
            row["diagnostic"] = "Every real tick and intratick observer event covered in the instrumented alpha component scope; original mandatory memory gaps remain."
    return rows


def compliant(rows):
    return all(row["status"] == "satisfied" for row in rows if row["mandatory"])


def verdict(report):
    if report.get("infrastructure_error"):
        return "infrastructure_error"
    statuses = [row["status"] for row in report["criteria"] if row["mandatory"]]
    if "failed" in statuses:
        return "failed"
    return "conforms_to_alpha" if statuses and all(s == "satisfied" for s in statuses) else "indeterminate"
