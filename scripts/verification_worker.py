"""Run the alpha protocol on independent Minecraft processes, never the working world."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
import uuid
from contextlib import ExitStack
from checkpoint_restore import validate, digest, file_map, write_json
from verification_protocol import construction, first_difference, criteria, compliant, verdict, VERSION


class Workers:
    def __init__(self):
        self.lock = threading.Lock()
        self.processes = []
        self.cancelled = False
        self.closed = False
        self.cancel_reason = None
        self.phase = "request_validation"
        self.phase_deadline = time.monotonic() + 420
        self.progress_sequence = 0

    def progress(self, phase, timeout):
        if self.closed:
            raise RuntimeError("Verification cancelled")
        self.phase = phase
        self.phase_deadline = time.monotonic() + timeout
        self.progress_sequence += 1

    def state(self):
        return {"phase": self.phase, "progress_sequence": self.progress_sequence,
                "phase_remaining_seconds": max(0, self.phase_deadline-time.monotonic()),
                "cancelled": self.cancelled, "owned_pids": [p.pid for p in self.processes]}

    def launch(self, command, root, stdout, stderr):
        with self.lock:
            if self.closed:
                raise RuntimeError("Verification interrupted before worker launch")
            process = subprocess.Popen(command, cwd=root, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                       text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.processes.append(process)
            return process

    def stop(self, reason=None):
        with self.lock:
            self.closed = True
            if reason:
                self.cancelled = True
                self.cancel_reason = reason
            for process in self.processes:
                if process.poll() is None:
                    try:
                        process.stdin.write("stop\n")
                        process.stdin.flush()
                        process.wait(timeout=30)
                    except (OSError, subprocess.TimeoutExpired):
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=30)
                if not process.stdin.closed:
                    process.stdin.close()


def rpc(port, name, arguments=None, timeout=420):
    body = json.dumps({"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/call",
                       "params": {"name": name, "arguments": arguments or {}}}).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", body,
                                    {"Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if "error" in payload:
        raise RuntimeError(f"Worker MCP error: {payload['error']}")
    report = payload["result"]["structuredContent"]
    if report["status"] != "ok":
        raise RuntimeError(f"Worker operation failed: {report}")
    return report


def artifact(root, reference):
    identifier = str(uuid.UUID(reference["artifact_id"]))
    path = root / "stonebench/artifacts" / (identifier + ".jsonl")
    if path.is_symlink() or digest(path) != reference["sha256"] or path.stat().st_size != reference["bytes"]:
        raise RuntimeError("Trace artifact bytes/hash mismatch")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if len(rows) != reference["count"] or not reference["complete"]:
        raise RuntimeError("Truncated/incomplete trace artifact")
    return rows


def trace_complete(root, operation):
    rows = artifact(root, operation["trace"])
    if len(rows) != operation["ticks_executed"]:
        raise RuntimeError("Real tick trace count mismatch")
    events = []
    for tick, row in enumerate(rows, 1):
        if row["tick_index"] != tick or row["phase"] != "end_tick" or row["simulation_index"] != operation["initial"]["simulation_index"] + tick:
            raise RuntimeError("Real tick trace continuity mismatch")
        if row["world_time"] != operation["initial"]["world_time"] + tick:
            raise RuntimeError("Trace clock skipped a game tick")
        coverage = row["state"]["coverage"]
        if not row["complete"] or coverage["status"] != "observed" or not coverage["chunks_ready"]:
            return False
        for key in ("blocks",):
            artifact(root, row["state"][key])
        for key in ("events", "adapter_blocks", "construction_blocks"):
            entries = artifact(root, row[key])
            if key == "events":
                events.extend(entries)
    if events != artifact(root, operation["intratick_events"]):
        raise RuntimeError("Intratick trace events were lost or reordered")
    return True


def diagnostic(identifier, status, expected, observed, detail):
    return {"id": identifier, "mandatory": True, "status": status, "expected": expected, "observed": observed,
            "diagnostic": detail, "sources": [{"source": "https://github.com/MINLEGO/StoneBench/issues/4",
                "revision_id": "body_sha256:3d1e0b8b087ab007a377d35ed678c8b0faf99cdaafc2b6c53db846ff61422870",
                "locator": "Implementation Decisions / Protocole de conformite"}]}


def run(source, request_directory, java, execution, test, workers, base_mcp, base_game):
    # Import here: checkpoint_server imports this module only after defining lease guards.
    from checkpoint_server import supervisor_lease, ensure_previous_child_absent
    source, directory = Path(source).resolve(), Path(request_directory).resolve()
    def call(port, name, arguments=None):
        timeout = 2450 if name == "transition" else 420
        workers.progress(f"mcp:{port}:{name}", timeout)
        result = rpc(port, name, arguments, timeout)
        workers.progress("archive_and_compare", 420)
        return result
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    report = {"request_id": request["request_id"], "checkpoint_id": request["checkpoint_id"],
              "manifest_sha256": request["manifest_sha256"], "protocol_version": VERSION,
              "minecraft_version": "1.21.11", "criteria": [], "cycles_executed": 0, "boundaries": [],
              "copies": [], "first_difference": None, "transition_ticks": 0,
              "limits": {"per_transition_ticks": 36000, "derived_transition_ticks": 432000,
                         "independent_global_tick_quota": None, "boot_watchdog_seconds": 180,
                         "transition_process_watchdog_seconds": 2400},
              "comparison_policy": "Exact construction blocks/inventories/typed NBT/runtime/ordered queues. Only implicit empty air sampling records omitted. Absolute clocks and external adapters archived separately; no internal deadline/priority/order normalization.",
              "measurements": {"dynamic_volume": None, "opening_time": None, "closing_time": None,
                               "status": "not_verified", "extension": "issue_13", "transition_ticks": []}}
    start = time.monotonic()
    try:
        if request.get("test_plan") and not test:
            raise RuntimeError("Test-only verification fault refused in production")
        if request.get("test_plan"):
            report["test_plan"] = request["test_plan"]
            report["injected_control_not_natural_recurrence"] = request["test_plan"]["scenario"] not in ("none", "positive")
        checkpoint, manifest, context = validate(source, request)
        if context["rest"]["status"] != "terminated":
            raise RuntimeError("Checkpoint lacks a real terminated transition")
        report["checkpoint_provenance"] = manifest["provenance"]
        geometry_args = {k: v for k, v in request["arguments"].items() if k.startswith("frame_")}
        with ExitStack() as stack:
            def copy(mode, offset):
                workers.progress(f"copy_and_hash:{mode}", 420)
                root = directory / mode
                root.mkdir()
                stack.enter_context(supervisor_lease(root))
                ensure_previous_child_absent(root)
                for port in (base_mcp + offset, base_game + offset):
                    with socket.socket() as listener:
                        listener.bind(("127.0.0.1", port))
                for name in ("fabric-server.jar", "server.properties", "eula.txt", "libraries", "versions", ".fabric", "mods"):
                    path = source / name
                    if path.exists():
                        if path.is_dir():
                            shutil.copytree(path, root / name)
                        else:
                            shutil.copy2(path, root / name)
                properties = (root / "server.properties").read_text(encoding="utf-8")
                lines = [line for line in properties.splitlines() if not line.startswith(("server-port=", "enable-rcon=", "enable-query="))]
                (root / "server.properties").write_text("\n".join(lines + [f"server-port={base_game + offset}", "enable-rcon=false", "enable-query=false"]) + "\n", encoding="utf-8")
                control = root / "stonebench"
                target = control / "checkpoints" / request["checkpoint_id"]
                target.parent.mkdir(parents=True)
                shutil.copytree(checkpoint, target)
                shutil.copytree(target / "world", root / "world")
                expected = {k.removeprefix("world/"): v for k, v in manifest["files"].items() if k.startswith("world/")}
                if file_map(root / "world") != expected:
                    raise RuntimeError("Independent copy world SHA-256 mismatch")
                shutil.copy2(source / "stonebench/attempt.json", control / "attempt.json")
                validate(source, request)
                validate(root, request)
                (control / "restore-history" / request["request_id"]).mkdir(parents=True)
                write_json(control / "resume.json", dict(request, status="verification_copy_boot"))
                write_json(control / "child-starting.json", {"supervisor_pid": os.getpid(), "status": "child_launch_pending"})
                out = stack.enter_context((root / "stdout.log").open("xb"))
                err = stack.enter_context((root / "stderr.log").open("xb"))
                command = [java, "-Xms256M", "-Xmx1G", f"-Dstonebench.port={base_mcp + offset}",
                           f"-Dstonebench.tickExecution={execution}", "-Dstonebench.supervised=true"]
                if test:
                    command.append("-Dstonebench.test=true")
                command += ["-jar", "fabric-server.jar", "nogui"]
                process = workers.launch(command, root, out, err)
                stack.callback(workers.stop)
                (root / "server.pid").write_text(str(process.pid), encoding="ascii")
                (control / "child-starting.json").unlink()
                deadline = time.monotonic() + 180
                workers.progress(f"boot:{mode}", 180)
                while not (control / "ready").exists():
                    if process.poll() is not None or workers.cancelled:
                        raise RuntimeError("Independent verification worker exited/interrupted during boot")
                    if time.monotonic() > deadline:
                        raise TimeoutError("Independent copy boot watchdog; not a construction failure")
                    time.sleep(.1)
                port = base_mcp + offset
                loaded = call(port, "describe_task")["restoration"]
                report["copies"].append({"mode": mode, "server_root": str(root), "mcp_port": port,
                    "game_port": base_game + offset, "pid": process.pid, "restoration": loaded})
                if loaded["status"] != "equal" or loaded["preparation_game_ticks"] != 0:
                    raise RuntimeError("Independent copy tick0 restoration differs/indeterminate")
                return root, port

            root, port = copy("repeater", 0)
            initial = call(port, "verification_snapshot")
            closed = call(port, "check_geometry", dict(geometry_args, expected_state="closed"))
            preconditions = criteria(closed, closed, context["rest"], True, manifest["provenance"].get("memory_coverage", {}))
            report["criteria"] += preconditions
            if not compliant(preconditions):
                report["stop_cause"] = "checkpoint_preconditions"
                row = next(row for row in preconditions if row["mandatory"] and row["status"] != "satisfied")
                report["first_difference"] = {"field": "criteria." + row["id"], "expected": row["expected"],
                    "observed": row["observed"], "status": row["status"], "boundary": "state0"}
            else:
                first = {}
                def boundary(mode, cycle, expected, worker_root, worker_port):
                    operation = call(worker_port, "transition", {"max_ticks": 36000, "trace": True, "interact": True})
                    report["transition_ticks"] += operation["ticks_executed"]
                    report["measurements"]["transition_ticks"].append({"mode": mode, "cycle": cycle, "state": expected,
                        "ticks": operation["ticks_executed"], "wall_seconds": operation["execution"]["wall_seconds"],
                        "last_movement_tick": operation["transition"]["last_movement_tick"], "recognition_tick": operation["transition"]["recognition_tick"]})
                    complete = trace_complete(worker_root, operation)
                    rest_report = operation["transition"]
                    scenario = request.get("test_plan", {}).get("scenario", "none")
                    inject = (scenario in ("recurrence2", "no_return5") and expected == "closed" or
                              scenario.startswith("direct_") and mode == "direct" or
                              scenario == "bad_open" and mode == "repeater" and cycle == 1 and expected == "open")
                    fault = None
                    post_fault = None
                    if inject:
                        fault = call(worker_port, "__test_verification_mutate", {"scenario": scenario, "cycle": cycle, "mode": mode, "boundary": expected})
                        remaining = 36000 - operation["ticks_executed"]
                        if remaining < 1:
                            raise RuntimeError("Injected boundary has no remaining real ticks inside transition limit")
                        post_fault = call(worker_port, "transition", {"max_ticks": remaining, "trace": True})
                        report["transition_ticks"] += post_fault["ticks_executed"]
                        complete = trace_complete(worker_root, post_fault) and complete
                        rest_report = post_fault["transition"]
                    snapshot = call(worker_port, "verification_snapshot")
                    geometry = call(worker_port, "check_geometry", dict(geometry_args, expected_state=expected))
                    rows = criteria(geometry, closed, rest_report, complete, manifest["provenance"].get("memory_coverage", {}))
                    report["criteria"] += rows
                    entry = {"mode": mode, "cycle": cycle, "expected_state": expected, "operation": operation,
                             "snapshot": snapshot, "geometry": geometry, "criteria": rows, "trace_complete": complete,
                             "injected_fault": fault, "post_fault_rest": post_fault}
                    report["boundaries"].append(entry)
                    if not compliant(rows) and report["first_difference"] is None:
                        row = next(row for row in rows if row["mandatory"] and row["status"] != "satisfied")
                        report["first_difference"] = {"field": "criteria." + row["id"], "expected": row["expected"],
                            "observed": row["observed"], "status": row["status"], "mode": mode, "cycle": cycle,
                            "boundary": expected, "first_tick": snapshot["world_time"]}
                    return snapshot, compliant(rows)

                def adapt(worker_root, worker_port, mode, initial_snapshot):
                    declaration = initial_snapshot["input"]
                    driver = declaration["driver"]
                    position = f"{driver['x']},{driver['y']},{driver['z']}"
                    active = initial_snapshot["checkpoint_state"]["state"]["blocks"][position]["parameters"]["powered"] == "true"
                    preparation = {"mode": mode, "operations": [], "game_ticks": 0, "clock_before": initial_snapshot["world_time"]}
                    def settle(interact):
                        step = call(worker_port, "transition", {"max_ticks": 36000, "trace": True, "interact": interact})
                        preparation["operations"].append(step)
                        preparation["game_ticks"] += step["ticks_executed"]
                        if step["transition"]["status"] != "terminated" or not trace_complete(worker_root, step):
                            raise RuntimeError("Adapter preparation rest/coverage could not be established")
                    changing = declaration["mode"] != mode
                    if active and changing:
                        settle(True)
                    if declaration["mode"] == "repeater" and mode == "direct":
                        rows = [dict(point, block="minecraft:air") for point in declaration["adapter_positions"]]
                        original = declaration["position"]
                        rows = [row for row in rows if any(row[axis] != original[axis] for axis in ("x", "y", "z"))]
                        rows.append(dict(original, block=declaration["device"], parameters={"face": "wall", "facing": declaration["orientation"]}))
                        preparation["operations"].append(call(worker_port, "modify_blocks", {"blocks": rows, "notify_neighbors": True}))
                        args = {key: declaration[key] for key in ("device", "position", "orientation", "input_block")}
                        preparation["operations"].append(call(worker_port, "declare_input", args))
                    preparation["operations"].append(call(worker_port, "prepare_input", {"mode": mode}))
                    if active and changing:
                        settle(True)
                    final = call(worker_port, "verification_snapshot")
                    difference = first_difference(construction(initial_snapshot), construction(final))
                    preparation["clock_after"] = final["world_time"]
                    preparation["construction_preserved"] = difference is None
                    preparation["first_difference"] = difference
                    report.setdefault("preparations", []).append(preparation)
                    if difference:
                        raise RuntimeError("Adapter preparation did not return to exact state0: " + str(difference))
                    return preparation
                prepared = adapt(root, port, "repeater", initial)
                report["adapter_preparation"] = prepared
                difference = first_difference(construction(initial), construction(call(port, "verification_snapshot")))
                if difference or not prepared["construction_preserved"]:
                    raise RuntimeError("Adapter changed state0 construction: " + str(difference))
                returned = False
                for cycle in range(1, 6):
                    opened, opening_ok = boundary("repeater", cycle, "open", root, port)
                    shut, closing_ok = boundary("repeater", cycle, "closed", root, port)
                    report["cycles_executed"] = cycle
                    if cycle == 1:
                        first = {"open": opened, "closed": shut}
                    difference = first_difference(construction(initial), construction(shut))
                    report.setdefault("recurrence_comparisons", []).append({"cycle": cycle, "equal": difference is None, "first_difference": difference})
                    if not opening_ok or not closing_ok:
                        report["stop_cause"] = "invalid_repeater_boundary"
                        break
                    if difference is None:
                        returned = True
                        report["stop_cause"] = "first_return_to_state0"
                        break
                    if cycle == 5:
                        report["stop_cause"] = "no_return_after_five_cycles"
                        report["first_difference"] = difference
                recurrence_status = "satisfied" if returned else "failed" if report["stop_cause"] == "no_return_after_five_cycles" else "indeterminate"
                report["criteria"].append(diagnostic("recurrence", recurrence_status, "First exact return within five cycles", report.get("recurrence_comparisons"), report["stop_cause"]))
                direct_root, direct_port = copy("direct", 1)
                direct_initial = call(direct_port, "verification_snapshot")
                if first_difference(initial["checkpoint_state"], direct_initial["checkpoint_state"]):
                    raise RuntimeError("Independent direct and repeater tick0 states differ")
                report["direct_preparation"] = adapt(direct_root, direct_port, "direct", direct_initial)
                for state in ("open", "closed"):
                    actual, _ = boundary("direct", 1, state, direct_root, direct_port)
                    difference = first_difference(construction(first[state]), construction(actual))
                    report["criteria"].append(diagnostic("mode_equivalence_" + state, "failed" if difference else "satisfied", "Exact first-cycle construction state, durations may differ", difference, "Global clocks and external adapters separately archived"))
                    if difference and report["first_difference"] is None:
                        report["first_difference"] = dict(difference, mode="direct", boundary=state, first_tick=actual["world_time"])
            validate(source, request)
    except Exception as error:
        report["infrastructure_error"] = {"kind": type(error).__name__, "diagnostic": str(error)}
        if workers.cancel_reason:
            report["infrastructure_error"]["owner_stop_reason"] = workers.cancel_reason
        report["stop_cause"] = "verification_interrupted" if workers.cancelled else "infrastructure_failure"
    finally:
        workers.stop()
        try:
            destination = source / "stonebench/artifacts"
            destination.mkdir(exist_ok=True)
            for mode in ("repeater", "direct"):
                for path in (directory / mode / "stonebench/artifacts").glob("*"):
                    if not path.is_file() or path.is_symlink():
                        raise RuntimeError("Unsafe worker artifact")
                    target = destination / path.name
                    if target.exists():
                        if digest(target) != digest(path):
                            raise RuntimeError("Immutable artifact identity collision")
                    else:
                        shutil.copyfile(path, target)
                    if digest(target) != digest(path):
                        raise RuntimeError("Imported artifact SHA-256 mismatch")
            report["worker_artifacts_available_via_mcp"] = True
        except Exception as error:
            report["infrastructure_error"] = {"kind": type(error).__name__, "diagnostic": str(error)}
        report["wall_seconds"] = time.monotonic() - start
        if workers.cancelled or (directory / "cancel.json").exists():
            report.setdefault("infrastructure_error", {"kind": "cancelled", "diagnostic": workers.cancel_reason or "Cancellation accepted before worker publication"})
            report["stop_cause"] = "verification_interrupted"
        report["verdict"] = verdict(report)
        report["conforms_to_alpha"] = report["verdict"] == "conforms_to_alpha"
        report["traces_retained"] = True
        # A lost-owner result may already have been finalized by the controller.
        # Preserve it and keep any late worker evidence separately.
        if test and request.get("test_plan", {}).get("scenario") == "publish_watchdog":
            # Pause after the provisional verdict: the real owner deadline must
            # leave a durable marker before the final publication veto.
            with workers.lock:
                workers.phase = "test_final_publication"
                workers.phase_deadline = time.monotonic() + .2
                workers.progress_sequence += 1
            write_json(directory / "publication-gate.json", {"provisional_verdict": report["verdict"]})
            deadline = time.monotonic() + 10
            while not (directory / "cancel.json").exists() and time.monotonic() < deadline:
                time.sleep(.05)
        with workers.lock:
            if workers.cancelled or (directory / "cancel.json").exists():
                marker = json.loads((directory / "cancel.json").read_text(encoding="utf-8")) if (directory / "cancel.json").exists() else {}
                reason = marker.get("reason", workers.cancel_reason or "user_cancelled")
                report["infrastructure_error"] = {"kind": "phase_timeout" if reason.startswith("individual_phase_watchdog:") else "cancelled", "diagnostic": reason}
                report["stop_cause"] = "individual_phase_watchdog" if reason.startswith("individual_phase_watchdog:") else "verification_interrupted"
                report["verdict"] = "infrastructure_error"
                report["conforms_to_alpha"] = False
            write_json(directory / ("late-worker-result.json" if (directory / "result.json").exists() else "result.json"), report)
