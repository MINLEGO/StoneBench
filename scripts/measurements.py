"""Source-defined metrics over hash-validated Minecraft snapshots and intratick events."""
from math import ceil

RULES_URL = "https://docs.google.com/document/d/1kDNXIvQ8uAMU5qRFXIk6nLxbVliIjcMu1MjHjLJrRH4/edit"
REVISION = "AHj4eMT_keZ9k_mo9La-s7C1bFHDqp8qAcERIYP8JSNCf922quSNhQQ0ICk0WEgJCGqRKxiqzo8qUe4DNy7-4Q"
CACHE_HASH = "e4a01f6d47956291bb9952392e3cf8216f2dc3c4537a81aaea0ccaf73e44eb68"


def sources(*indices):
    return [{"authority": "community", "source": RULES_URL, "revision_id": REVISION,
             "native_cache_sha256": CACHE_HASH, "locator_type": "native_character_index", "locator": str(index)} for index in indices]


def position(row):
    return tuple(row[k] for k in ("x", "y", "z"))


def timestamp(event):
    return {key: event[key] for key in ("world_time", "simulation_index", "tick_index", "phase", "operation_order")}


def union(bounds):
    if not bounds:
        return None
    return [min(b[i] for b in bounds) for i in range(3)] + [max(b[i] for b in bounds) for i in range(3,6)]


def volume(bounds):
    envelope = union(bounds)
    dimensions = [ceil(envelope[i+3]-envelope[i]) for i in range(3)] if envelope else None
    return {"envelope": envelope, "dimensions": dimensions,
            "value": dimensions[0]*dimensions[1]*dimensions[2] if dimensions else None}


def movement_end(start,method,pulse=None):
    if method == "short_pulse_extension":
        if pulse is None or pulse < 0 or pulse > 2:
            raise ValueError("Received pulse length 0..2gt required")
        return start+pulse
    if method == "instant_retraction":
        return start
    if method in ("standard_extension", "standard_retraction"):
        return start+2
    raise ValueError("Unclassified movement cannot have an exact end")


def measure(operation, samples, events, closed_geometry, final_geometry, input_declaration, complete, memory):
    """samples include initial then every actual tick; caller validates artifact identities."""
    gaps = []
    if not complete:
        gaps.append("incomplete_tick_or_intratick_trace")
    if not memory.get("restorable_observed_scope") or memory.get("uncovered_components") != []:
        gaps.append("uncovered_checkpoint_memory")
    if any(operation["initial"]["state"].get(key) for key in ("block_ticks", "fluid_ticks", "block_events")):
        gaps.append("initial_not_quiescent_for_input_connection")
    if len([e for e in events if e["kind"] == "input_interaction"]) != 1:
        gaps.append("single_input_origin_missing_for_connection")
    for index,event in enumerate(events):
        if event["kind"] == "block_write_result" and event["detail"]["changed"]:
            if index+1 >= len(events) or events[index+1]["kind"] != "measurement_block" or events[index+1]["position"] != event["position"]:
                gaps.append("effective_write_extent_event_missing")
    if operation["transition"]["status"] != "terminated":
        gaps.append("rest_not_established")
    roles = {position(r): r for r in closed_geometry["measurement_roles"]}
    adapters = {position(r) for r in input_declaration["adapter_positions"]}
    support = position(input_declaration["input_block"])
    frame = {p for p,r in roles.items() if r["role"] == "frame_interior"}
    door_materials = {r["block"] for r in roles.values() if r["role"] == "frame_interior" and r.get("block") not in (None,"minecraft:air","minecraft:piston_head","minecraft:moving_piston","minecraft:piston","minecraft:sticky_piston")}
    # The alpha regular category imposes no quartz/air hallway composition requirement.
    optional = next((r for r in closed_geometry["criteria"] if r["id"] == "hallway_composition"), {})
    composition_optional = optional.get("mandatory") is False and optional.get("status") == "not_verified"
    movements, active, powers, callbacks = [], {}, {}, None
    causal_positions = {position(e["position"]) for e in events if e["kind"] not in ("measurement_block", "piston_movement_sample")}
    causal_positions.add(support)
    observations = {}
    last_sample_blocks = []
    mobile_positions = set()
    for sample in samples:
        last_sample_blocks = sample["blocks"]
        for row in sample["blocks"]:
            detail = row.get("measurement")
            if detail is None and row["block"] != "minecraft:air":
                gaps.append("physical_extent_sample_missing")
            if detail and detail["block"] != "minecraft:air":
                observations[(position(detail), detail["block"], tuple(detail.get("bounds", [])), detail.get("wiring_role"))] = (detail, "snapshot", sample["world_time"])
            if row["block"] == "minecraft:moving_piston":
                mobile_positions.add(position(row))
            if row["block"] == "minecraft:moving_piston" and not row.get("runtime"):
                gaps.append("moving_piston_runtime_missing")
    for event in events:
        kind, detail = event["kind"], event["detail"]
        if kind == "measurement_block":
            if detail["block"] != "minecraft:air":
                observations[(position(detail), detail["block"], tuple(detail.get("bounds", [])), detail.get("wiring_role"))] = (detail, "intratick", event["world_time"])
        elif kind == "piston_received_power":
            key = position(event["position"])
            history = powers.setdefault(key, [])
            if not history or history[-1][1] != detail["powered"]:
                history.append((event["world_time"], detail["powered"], timestamp(event)))
        elif kind == "block_event_callback" and detail["block"] in ("minecraft:piston", "minecraft:sticky_piston"):
            callbacks = event
        elif kind == "piston_movement_sample":
            key = position(detail["destination"])
            if detail["sample"] == "start":
                movement = {"start": timestamp(event), "origin": position(detail["origin"]), "destination": key,
                            "block": detail["block"], "source": detail["source"], "extending": detail["extending"],
                            "callback": callbacks, "samples": [], "forced_finish": None, "forced_completion": None}
                movements.append(movement)
                active[key] = movement
            movement = active.get(key)
            if movement is None or movement["extending"] != detail["extending"]:
                gaps.append("movement_start_missing")
                continue
            movement["samples"].append({"bounds": detail.get("bounds"), "timestamp": timestamp(event), "progress": detail["progress"]})
            if detail["sample"] == "forced_finish":
                movement["forced_finish"] = timestamp(event)
            if detail["sample"] == "after_forced_finish" and detail["progress"] >= 1:
                movement["forced_completion"] = timestamp(event)
    door_positions = set(frame)
    for movement in movements:
        causal_positions.update((movement["origin"], movement["destination"]))
    for movement in movements:
        if not movement["source"] and (movement["origin"] in door_positions or movement["destination"] in door_positions):
            door_positions.update((movement["origin"], movement["destination"]))
            movement["door_block"] = True
        else:
            movement["door_block"] = False
    opened_pattern = final_geometry["expected_state"] == "open" and all(r["status"] == "satisfied" for r in final_geometry["criteria"] if r["id"] in ("frame_state", "continuable"))
    opened_bounds = {(position(row), row["block"], tuple(row.get("measurement", {}).get("bounds", []))) for row in last_sample_blocks} if opened_pattern else set()
    def fully_in_hallway(b):
        xs, ys = [p[0] for p in frame], [p[1] for p in frame]
        return bool(b and b[0] >= min(xs) and b[3] <= max(xs)+1 and b[1] >= min(ys) and b[4] <= max(ys)+1)
    # Roles follow the moved block. A piston head remains circuit even if it encloses the passage.
    exclusions, bounds, conditional_bounds, conditional_roles = [], [], [], []
    def include(row, origin_kind, at):
        if row is None:
            gaps.append("physical_extent_sample_missing")
            return
        block, point = row["block"], position(row)
        if block == "minecraft:air" or block == "minecraft:moving_piston":
            return
        reason = None
        if point != support and point in adapters:
            reason = "validated_external_adapter"
        elif point not in causal_positions:
            reason = "not_connected_to_input_in_complete_quiescent_protocol"
        elif composition_optional and point != support and point in door_positions and block in door_materials:
            reason = "door_material_not_required_by_open_composition"
        elif point != support and fully_in_hallway(row.get("bounds")) and (point,block,tuple(row.get("bounds", []))) not in opened_bounds:
            conditional_roles.append({"position": list(point), "block": block, "role": "hallway_contents", "reason": "excluded_except_open_state; intermediate_open_pattern_not_proven"})
            conditional_bounds.append(row["bounds"])
            return
        elif (point != support and roles.get(point, {}).get("role") == "physical_encadrement"
              and row.get("wiring_role") == "passive_material" and composition_optional):
            conditional_roles.append({"position": list(point), "block": block, "role": "physical_encadrement", "reason": "wiring_necessity_not_proven_by_snapshot"})
            if row.get("bounds"): conditional_bounds.append(row["bounds"])
            return
        if reason:
            exclusions.append({"position": list(point), "block": block, "reason": reason, "sample": origin_kind, "world_time": at})
        elif row.get("bounds"):
            bounds.append(row["bounds"])
        elif block != "minecraft:air":
            gaps.append("nonair_extent_missing:" + block)
    for row, origin_kind, at in observations.values():
        include(row, origin_kind, at)
    for movement in movements:
        if composition_optional and movement["door_block"] and movement["block"] in door_materials:
            exclusions.append({"position": list(movement["origin"]), "block": movement["block"], "reason": "moving_door_material_not_required_by_open_composition"})
        else:
            for sample in movement["samples"]:
                if sample["bounds"]:
                    if fully_in_hallway(sample["bounds"]) and (movement["destination"],movement["block"],tuple(sample["bounds"])) not in opened_bounds:
                        conditional_bounds.append(sample["bounds"])
                        conditional_roles.append({"position": list(movement["destination"]), "block": movement["block"], "role": "moving_hallway_contents", "reason": "nonopen_hallway_exclusion_state_not_proven"})
                    else:
                        bounds.append(sample["bounds"])
                else:
                    gaps.append("moving_extent_missing")
    if not composition_optional:
        gaps.append("open_composition_exclusion_not_established")
    # Every moving snapshot must have its matching intratick movement record.
    recorded = {m["destination"] for m in movements}
    if mobile_positions - recorded:
        gaps.append("mobile_position_without_intratick_provenance")
    gaps = sorted(set(gaps))
    lower = volume(bounds)
    observed = volume(bounds+conditional_bounds)
    if lower["dimensions"] != observed["dimensions"]:
        gaps.append("conditional_role_exclusion_changes_dimensions")
    dynamic = {"status": "indeterminate" if gaps else "measured", **observed, "unit": "block_volume",
               "gaps": gaps, "excluded": exclusions, "conditional_roles": conditional_roles,
               "minimum_envelope": lower["envelope"], "maximum_envelope": observed["envelope"],
               "envelope_status": "exact" if lower["envelope"] == observed["envelope"] else "bounded",
               "sources": sources(23868,24437,24616,30714,31084,31137,31171),
               "connection_policy": "Quiescent initial queues, complete vanilla read/write/event causal cone from one input, covered checkpoint memory. Untouched disconnected controls are excluded only in this bounded observed protocol.",
               "sample_policy": "Cumulative physical bounds over initial, all real tick states, effective writes and piston positions before/after advancement and forced finish."}
    if gaps:
        dynamic["observed_value"] = dynamic["value"]
        dynamic["value"] = None
    interactions = [e for e in events if e["kind"] == "input_interaction"]
    signals = [e for e in events if e["kind"] == "input_signal_change"]
    timing_gaps = [g for g in gaps if g not in ("open_composition_exclusion_not_established", "conditional_role_exclusion_changes_dimensions")]
    origin = interactions[0] if len(interactions) == 1 else None
    signal = signals[0] if signals else None
    if origin is None:
        timing_gaps.append("single_input_interaction_missing")
    if signal is None:
        timing_gaps.append("input_signal_arrival_missing")
    relevant = []
    opening = final_geometry["expected_state"] == "open"
    def intersects_hallway(b):
        xs, ys = [p[0] for p in frame], [p[1] for p in frame]
        return b and b[0] < max(xs)+1 and b[3] > min(xs) and b[1] < max(ys)+1 and b[4] > min(ys)
    for movement in movements:
        callback = movement["callback"]
        movement_gaps = []
        if not callback:
            movement_gaps.append("vanilla_movement_callback_missing")
        start = movement["start"]["world_time"]
        end, rule = start+2, "standard_extension" if movement["extending"] else "standard_retraction"
        pulse = None
        if not movement["extending"] and movement["forced_completion"] and movement["forced_completion"]["world_time"] == start:
            end, rule = start, "instant_retraction"
        if movement["extending"] and callback:
            history = powers.get(position(callback["position"]), [])
            rises = [edge for edge in history if edge[1] and edge[2]["operation_order"] <= movement["start"]["operation_order"]]
            if not rises:
                movement_gaps.append("received_piston_power_origin_missing")
            if rises:
                rise = rises[-1][0]
                falls = [edge for edge in history if not edge[1] and edge[0] >= rise]
                if falls:
                    pulse = falls[0][0]-rise
                    if pulse <= 2:
                        end, rule = start+pulse, "short_pulse_extension"
            if movement["forced_finish"] and pulse is None:
                movement_gaps.append("received_short_pulse_length_missing")
        if movement["forced_finish"] and rule.startswith("standard") and movement["forced_finish"]["world_time"] < end:
            movement_gaps.append("unclassified_early_finish")
        end = movement_end(start,rule,pulse)
        movement["end"] = {"world_time": end, "method": rule, "received_pulse_ticks": pulse,
                           "start_event": movement["start"], "gaps": movement_gaps}
        pertinent = (any(intersects_hallway(s["bounds"]) for s in movement["samples"]) if opening else movement["door_block"])
        movement["pertinent_to_door_time"] = pertinent
        if pertinent:
            if opening and not movement["door_block"]:
                movement_gaps.append("non_door_movement_hallway_pattern_effect_not_established")
            relevant.append(movement)
            timing_gaps.extend(movement_gaps)
    frame_status = next(r["status"] for r in final_geometry["criteria"] if r["id"] == "frame_state")
    if frame_status != "satisfied":
        timing_gaps.append("requested_hallway_pattern_not_established")
    if not relevant:
        timing_gaps.append("last_pertinent_movement_missing")
    end = max((m["end"]["world_time"] for m in relevant), default=None)
    last = max((m["start"]["world_time"] for m in relevant), default=None)
    rest_time = operation["initial"]["world_time"]+operation["transition"]["recognition_tick"] if operation["transition"]["recognition_tick"] is not None else None
    if end is not None and rest_time is not None and end > rest_time:
        timing_gaps.append("movement_end_after_rest_recognition")
    timing_gaps = sorted(set(timing_gaps))
    time_metric = {"status": "indeterminate" if timing_gaps else "measured", "unit": "game_ticks",
        "value": end-origin["world_time"] if end is not None and origin and not timing_gaps else None,
        "interaction": timestamp(origin) if origin else None, "signal_at_input_block": timestamp(signal) if signal else None,
        "adaptation_ticks": signal["world_time"]-origin["world_time"] if signal and origin else None,
        "door_response_ticks": end-signal["world_time"] if end is not None and signal and not timing_gaps else None,
        "completion_world_time": end, "last_pertinent_movement_start_world_time": last,
        "last_pertinent_movement_end_world_time": end,
        "last_circuit_movement_end_world_time": max((m["end"]["world_time"] for m in movements), default=None),
        "last_observed_construction_change_world_time": operation["initial"]["world_time"]+operation["transition"]["last_movement_tick"],
        "rest_recognition": {"world_time": rest_time, "tick_index": operation["transition"]["recognition_tick"], "phase": "end_tick"},
        "gaps": timing_gaps, "sources": sources(26513,26906,26998,27066,27128,27683 if opening else 28244)}
    return {"mode": input_declaration["mode"], "purpose": "reference" if input_declaration["mode"] == "repeater" else "direct_diagnostic",
            "dynamic_volume": dynamic, "opening_time" if opening else "closing_time": time_metric,
            "movements": movements, "transition_ticks": operation["ticks_executed"],
            "wall_seconds": operation["execution"]["wall_seconds"], "objectives_combined": False}


def summarize(entries, eligible):
    references = [e for e in entries if e["mode"] == "repeater"]
    bounds = [e["dynamic_volume"]["envelope"] for e in references if e["dynamic_volume"]["envelope"]]
    gaps = sorted({g for e in references for g in e["dynamic_volume"]["gaps"]})
    minimum = volume([e["dynamic_volume"].get("minimum_envelope", e["dynamic_volume"]["envelope"]) for e in references if e["dynamic_volume"].get("minimum_envelope", e["dynamic_volume"]["envelope"])])
    maximum = volume(bounds)
    if minimum["dimensions"] != maximum["dimensions"]:
        gaps.append("conditional_exclusion_changes_cumulative_dimensions")
    dynamic = {"status": "measured" if references and not gaps else "indeterminate", **maximum, "gaps": gaps, "minimum_envelope": minimum["envelope"], "maximum_envelope": maximum["envelope"], "sources": sources(23868)}
    if dynamic["status"] == "indeterminate":
        dynamic["observed_value"], dynamic["value"] = dynamic["value"], None
    result = {"dynamic_volume": dynamic, "transitions": entries, "objective_policy": "Separate volume and opening-time objectives; no fused score.",
              "record_eligibility": "not_verified", "interpretation": "alpha_diagnostic" if not eligible else "conforms_to_alpha_measurements"}
    for kind in ("opening_time", "closing_time"):
        metrics = [e[kind] for e in references if kind in e]
        result[kind] = {"status": "measured" if metrics and all(m["status"] == "measured" for m in metrics) else "indeterminate",
                       "value": max(m["value"] for m in metrics) if metrics and all(m["status"] == "measured" for m in metrics) else None,
                       "unit": "game_ticks", "aggregation": "slowest_observed_repeater_cycle", "sources": sources(27197,27327)}
    return result

