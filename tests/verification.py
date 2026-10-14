"""End-to-end checkpoint verification against independent real Minecraft copies."""
import json
import os
import signal
import asyncio
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verification_protocol import first_difference
from app.harness import audit
import integration


class VerificationRuntimeIntegration(integration.StoneBenchRuntimeIntegration):
    async def test_real_mcp_server_contract(self):
        await self._connect()
        evidence = {"scenarios": [], "source_preservation": []}
        try:
            first, second = self.sessions
            starts = [await self.call(session, "start_attempt", {"task_id": integration.TASK_ID}) for session in self.sessions]
            for start in starts:
                self.assert_ok(start)
            names = {tool.name for tool in (await first.list_tools()).tools}
            self.assertTrue({"verify_checkpoint", "verification_snapshot", "__test_verification_fixture",
                             "__test_verification_config", "__test_verification_mutate",
                             "verification_status", "cancel_verification"}.issubset(names), names)

            checkpoint = await self.prepare_powered_checkpoint(first)
            checkpoint_id = checkpoint["checkpoint_id"]
            failure_before = await self.call(first, "verification_snapshot")
            self.assert_ok(await self.call(first, "__test_verification_config", {"scenario": "publication_failure"}))
            rejected = await self.call(first, "verify_checkpoint", {"checkpoint_id": checkpoint_id})
            self.assertEqual(rejected["status"], "error", rejected)
            self.assertIn("verification_publication_failed", json.dumps(rejected), rejected)
            failure_after = await self.call(first, "verification_snapshot")
            self.assertIsNone(first_difference(self.frozen_snapshot(failure_before), self.frozen_snapshot(failure_after)))
            usable = await self.call(first, "advance", {"ticks": 1, "trace": True})
            self.assert_ok(usable)
            self.assertEqual(usable["ticks_executed"], 1, usable)
            evidence["publication_failure"] = {"diagnostic": rejected["error"], "working_difference": None,
                                               "subsequent_advance_ticks": usable["ticks_executed"]}
            before = await self.call(first, "verification_snapshot")
            self.assert_ok(before)
            evidence["checkpoint"] = checkpoint

            scenarios = (
                ("none", "first_return_to_state0", 1, "satisfied"),
                ("recurrence2", "first_return_to_state0", 2, "satisfied"),
                ("no_return5", "no_return_after_five_cycles", 5, "failed"),
            )
            for scenario, stop_cause, cycles, recurrence_status in scenarios:
                report = await self.verify(first, checkpoint_id, scenario)
                self.assertEqual(report["stop_cause"], stop_cause, self.report_context(report))
                self.assertEqual(report["cycles_executed"], cycles, self.report_context(report))
                recurrence = self.report_criterion(report, "recurrence")
                self.assertEqual(recurrence["status"], recurrence_status, self.report_context(report))
                self.assert_boundaries_ran_in_minecraft(first, report)
                if scenario == "none":
                    # The usual completed answer fits the harness's direct-result threshold (larger multi-cycle reports are paged there).
                    self.assertLess(self.completed_sizes["none"], 16384, self.completed_sizes)
                    self.assert_mode_equivalence(report, "satisfied")
                    self.assertEqual(report["verdict"], "conforms_to_alpha", self.report_context(report))
                elif scenario == "recurrence2":
                    comparisons = report["recurrence_comparisons"]
                    self.assertEqual([row["equal"] for row in comparisons], [False, True], comparisons)
                    self.assert_mode_equivalence(report, "satisfied")
                    self.assertIn("inventory", comparisons[0]["first_difference"]["field"])
                else:
                    self.assertEqual([row["equal"] for row in report["recurrence_comparisons"]],
                                     [False, False, False, False, False], self.report_context(report))
                    self.assertIn("inventory", report["first_difference"]["field"])
                evidence["scenarios"].append(self.evidence_summary(report))

            for scenario in ("direct_block", "direct_inventory", "direct_internal"):
                report = await self.verify(first, checkpoint_id, scenario)
                self.assertEqual(report["cycles_executed"], 1, self.report_context(report))
                self.assertEqual(self.report_criterion(report, "recurrence")["status"], "satisfied", self.report_context(report))
                self.assertEqual(self.report_criterion(report, "mode_equivalence_closed")["status"], "failed", self.report_context(report))
                self.assertIsNotNone(report["first_difference"], self.report_context(report))
                evidence["scenarios"].append(self.evidence_summary(report))

            bad_open = await self.verify(first, checkpoint_id, "bad_open")
            open_boundary = self.boundary(self.local(first, bad_open)[0], "repeater", 1, "open")
            self.assertEqual(self.criterion_status(open_boundary["geometry"], "frame_state"), "failed", self.report_context(bad_open))
            fault = next(row for row in bad_open["faults"] if row["id"] == "frame_state")  # the agent's own view of that same fault
            self.assertEqual((fault["status"], fault["mode"], fault["cycles"], fault["boundary"]), ("failed", "repeater", [1], "open"))
            self.assertTrue(fault["expected"] and fault["diagnostic"] and "observed" in fault)
            self.assertEqual(self.report_criterion(bad_open, "frame_state")["status"], "failed")
            self.assertTrue(bad_open["faults"] and all(row["status"] in ("failed", "indeterminate") for row in bad_open["faults"]))
            self.assertEqual(bad_open["stop_cause"], "invalid_repeater_boundary", self.report_context(bad_open))
            self.assertEqual(bad_open["verdict"], "failed", self.report_context(bad_open))
            evidence["scenarios"].append(self.evidence_summary(bad_open))

            after = await self.call(first, "verification_snapshot")
            self.assert_ok(after)
            difference = first_difference(self.frozen_snapshot(before), self.frozen_snapshot(after))
            evidence["source_preservation"].append({"before_after_difference": difference})
            self.assertIsNone(difference, "Verification must preserve the complete frozen working snapshot")

            powered_checkpoint = await self.prepare_powered_checkpoint(second)
            powered_report = await self.verify(second, powered_checkpoint["checkpoint_id"], "none")
            self.assertEqual(powered_report["verdict"], "conforms_to_alpha", self.report_context(powered_report))
            self.assertEqual(powered_report["cycles_executed"], 1, self.report_context(powered_report))
            self.assertEqual(powered_report["stop_cause"], "first_return_to_state0", self.report_context(powered_report))
            self.assert_boundaries_ran_in_minecraft(second, powered_report)
            self.assert_mode_equivalence(powered_report, "satisfied")
            evidence["powered_checkpoint"] = {
                "checkpoint_id": powered_checkpoint["checkpoint_id"],
                "active_input": powered_checkpoint["active_input"],
                "verification": self.evidence_summary(powered_report),
            }

            watchdog = await self.verify(first, checkpoint_id, "publish_watchdog")
            self.assertEqual(watchdog["verdict"], "infrastructure_error", self.report_context(watchdog))
            self.assertFalse(watchdog["conforms_to_alpha"])
            self.assertEqual(watchdog["stop_cause"], "individual_phase_watchdog", self.report_context(watchdog))
            self.assertIn("test_final_publication", json.dumps(watchdog["infrastructure_error"]))
            roots = [Path(item) for item in os.environ["STONEBENCH_SERVER_ROOTS"].split(";")]
            job_root = next(root / "stonebench/verifications" / watchdog["request_id"] for root in roots
                            if (root / "stonebench/verifications" / watchdog["request_id"]).exists())
            gate = json.loads((job_root / "publication-gate.json").read_text(encoding="utf-8"))
            self.assertEqual(gate["provisional_verdict"], "conforms_to_alpha")
            marker = json.loads((job_root / "cancel.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["reason"], "individual_phase_watchdog:test_final_publication")
            await asyncio.sleep(.5)
            for name in ("result.json", "late-worker-result.json"):
                if (job_root / name).exists():
                    final = json.loads((job_root / name).read_text(encoding="utf-8"))
                    self.assertEqual(final["verdict"], "infrastructure_error", final)
                    self.assertFalse(final["conforms_to_alpha"])
            evidence["publication_watchdog"] = self.evidence_summary(watchdog)
            evidence["publication_watchdog"]["gate"] = gate
            evidence["publication_watchdog"]["durable_stop"] = marker

            cancelled = await self.cancel_worker_during_boot(first, checkpoint_id)
            evidence["worker_cancellation"] = cancelled
            interrupted = await self.interrupt_worker(first, checkpoint_id)
            evidence["worker_interruption"] = interrupted
        finally:
            evidence["completed_status_bytes"] = getattr(self, "completed_sizes", {})
            evidence["response_bytes_max"] = {name: max(sizes) for name, sizes in getattr(self, "response_sizes", {}).items()}
            output = Path(os.environ.get("STONEBENCH_VERIFICATION_EVIDENCE", ".runtime/verification-summary.json"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            await self.stack.aclose()

    async def verify(self, session, checkpoint_id, scenario):
        configured = await self.call(session, "__test_verification_config", {"scenario": scenario})
        self.assert_ok(configured)
        before = await self.call(session, "verification_snapshot")
        self.assert_ok(before)
        started = await self.call(session, "verify_checkpoint", {"checkpoint_id": checkpoint_id})
        self.assert_ok(started)
        job = started.get("verification")
        self.assertIsInstance(job, dict, started)
        self.assertEqual(job.get("status"), "running", started)
        request_id = job.get("request_id")
        self.assertTrue(request_id, started)
        report = await self.wait_for_verification(session, request_id)
        self.__dict__.setdefault("completed_sizes", {})[scenario] = self.response_sizes["verification_status"][-1]
        self.assertIn(report.get("verdict"), {"conforms_to_alpha", "failed", "indeterminate", "infrastructure_error"}, self.report_context(report))
        self.assertTrue(report.get("working_construction_preserved"), self.report_context(report))
        self.assertFalse(report.get("working_differences"), self.report_context(report))
        after = await self.call(session, "verification_snapshot")
        self.assert_ok(after)
        difference = first_difference(self.frozen_snapshot(before), self.frozen_snapshot(after))
        self.assertIsNone(difference, f"{scenario} changed the frozen source world: {difference}")
        await self.assert_agent_view(session, report)
        report["_source_preservation_difference"] = difference
        return report

    async def wait_for_verification(self, session, request_id, timeout=2400):
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            result = await self.call(session, "verification_status", {"request_id": request_id})
            self.assert_ok(result)
            status = result.get("verification")
            self.assertIsInstance(status, dict, result)
            if "verdict" in status:
                return status
            self.assertIn(status.get("status"), {"running", "cancelling"}, result)
            progress = status.get("progress")
            if progress is not None:
                self.assertTrue(progress.get("phase"), result)
                self.assertIsInstance(progress.get("progress_sequence"), int, result)
                self.assertGreaterEqual(progress.get("phase_remaining_seconds", -1), 0, result)
            await asyncio.sleep(0.25)
        self.fail(f"Verification {request_id} did not finish within {timeout} seconds")

    def server_root(self, session):
        return Path(os.environ["STONEBENCH_SERVER_ROOTS"].split(";")[self.sessions.index(session)])

    def local(self, session, report):
        """The complete local report, bound and cross-checked against the MCP status (audit.load raises on any disagreement)."""
        local = audit.load(self.server_root(session), report["request_id"], report["checkpoint_id"], report)
        return local["report"], local

    async def assert_agent_view(self, session, report):
        """What an agent can learn from a completed verification, and what it cannot."""
        self.assertEqual(report["status"], "completed")
        for key in ("verdict", "conforms_to_alpha", "stop_cause", "criteria", "faults", "boundaries",
                    "working_construction_preserved", "working_differences", "working_after"):
            self.assertIn(key, report, key)
        self.assertEqual(integration.source_leaks(report), [], "The completed status exposes rule sources")
        self.assertNotIn("full_report", report)
        for key in ("copies", "checkpoint_provenance", "preparations", "adapter_preparation", "direct_preparation", "audit", "test_plan"):
            self.assertNotIn(key, report, key)
        self.assertTrue(all(row["status"] and "mandatory" in row and set(row) == {"id", "mandatory", "status"} for row in report["criteria"]))
        self.assertEqual(len({row["id"] for row in report["criteria"]}), len(report["criteria"]))
        for row in report["boundaries"]:
            self.assertEqual(set(row), {"mode", "cycle", "expected_state", "trace_complete", "ticks_executed", "rest", "snapshot"})
        full, local = self.local(session, report)  # raises if the concise form disagrees with completed.json
        self.assertEqual(full["audit"]["request_id"], report["request_id"])
        self.assertEqual(full["status"], "completed")
        if full["criteria"]:
            self.assertTrue(all(row["sources"] for row in full["criteria"]), "The local report keeps the sources")
            self.assertTrue(integration.source_leaks(full))
            self.assertEqual({row["id"] for row in full["criteria"]}, {row["id"] for row in report["criteria"]})
        else:
            self.assertEqual(report["criteria"], [])
        self.assertEqual(len(full["boundaries"]), len(report["boundaries"]))
        self.assertEqual(len([row for row in full["criteria"] if row["mandatory"] and row["status"] != "satisfied"]),
                         sum(len(row.get("cycles", [None])) for row in report["faults"]))  # one entry per fault, listing its cycles
        if full.get("measurements", {}).get("transitions"):
            self.assertTrue(all(row["movements"] for row in full["measurements"]["transitions"]))
            self.assertEqual(len(full["measurements"]["transitions"]), len(report["measurements"]["transitions"]))
            self.assertFalse(any("movements" in row or "sources" in row for row in report["measurements"]["transitions"]))
        for reference in [report["working_after"]] + [row["snapshot"] for row in report["boundaries"]]:  # artifacts of the report stay readable
            page = await self.call(session, "read_artifact", {"artifact_id": reference["artifact_id"], "offset": 0, "limit": 1})
            self.assert_ok(page)
            self.assertEqual(len(page["entries"]), 1, reference)
            self.assertEqual(integration.source_leaks(page), [])
        if full["boundaries"]:  # construction traces and diffs are still readable, and no readable artifact is the report
            trace = full["boundaries"][0]["operation"]["trace"]
            page = await self.call(session, "read_artifact", {"artifact_id": trace["artifact_id"], "offset": 0, "limit": 2})
            self.assert_ok(page)
            self.assertTrue(page["entries"])
        kinds = {json.loads(path.read_text(encoding="utf-8"))["kind"] for path in (self.server_root(session) / "stonebench/artifacts").glob("*.meta")}
        self.assertNotIn("verification_report", kinds)
        # Neither the status nor a second look through cancel_verification can reach the report or its sources.
        again = await self.call(session, "cancel_verification", {"request_id": report["request_id"]})
        self.assertEqual(again["verification"], report)
        self.assertEqual((await self.call(session, "verification_status", {"request_id": report["request_id"]}))["verification"], report)

    @staticmethod
    def frozen_snapshot(snapshot):
        return {key: snapshot[key] for key in ("checkpoint_state", "construction", "input")}

    async def prepare_powered_checkpoint(self, session):
        fixture = await self.call(session, "__test_verification_fixture", {"scenario": "powered"})
        self.assert_ok(fixture)
        declaration = {key: fixture[key] for key in ("device", "position", "orientation", "input_block")}
        self.assertEqual(fixture.get("active_at_setup"), False, fixture)
        initial = await self.call(session, "transition", {"max_ticks": 36000, "trace": True})
        self.assert_ok(initial)
        self.assertEqual(initial["transition"]["status"], "terminated", initial)
        opened = await self.call(session, "check_geometry", {"expected_state": "open"})
        self.assert_ok(opened)
        self.assertEqual(self.criterion_status(opened, "frame_state"), "satisfied", opened)
        declared = await self.call(session, "declare_input", declaration)
        self.assert_ok(declared)
        self.assertEqual(declared["device"], "minecraft:lever", declared)
        self.assertEqual(declared["orientation"], "west", declared)
        toggled = await self.call(session, "transition", {"max_ticks": 36000, "trace": True, "interact": True})
        self.assert_ok(toggled)
        self.assertEqual(toggled["transition"]["status"], "terminated", toggled)
        closed = await self.call(session, "check_geometry", {"expected_state": "closed"})
        self.assert_geometry_checkpoint_ready(closed)
        rest = await self.call(session, "transition", {"max_ticks": 36000, "trace": True})
        self.assert_ok(rest)
        self.assertEqual(rest["transition"]["status"], "terminated", rest)
        created = await self.call(session, "create_checkpoint")
        self.assert_ok(created)
        self.assertTrue(created["rest_established"], created)
        snapshot = await self.call(session, "verification_snapshot")
        self.assert_ok(snapshot)
        driver = snapshot["input"]["driver"]
        position = f'{driver["x"]},{driver["y"]},{driver["z"]}'
        powered = snapshot["checkpoint_state"]["state"]["blocks"][position]["parameters"]["powered"]
        self.assertEqual(powered, "true", snapshot)
        return {**created["checkpoint"], "active_input": powered}

    async def cancel_worker_during_boot(self, session, checkpoint_id):
        roots = [Path(item) for item in os.environ.get("STONEBENCH_SERVER_ROOTS", "").split(";") if item]
        source_root = next((root for root in roots if (root / "stonebench" / "checkpoints" / checkpoint_id).exists()), None)
        self.assertIsNotNone(source_root, "The test launcher must expose its own server roots for safe worker interruption")
        config = await self.call(session, "__test_verification_config", {"scenario": "none"})
        self.assert_ok(config)
        before = await self.call(session, "verification_snapshot")
        self.assert_ok(before)
        ticks_before = (await self.call(session, "describe_task"))["simulation_ticks"]
        started = await self.call(session, "verify_checkpoint", {"checkpoint_id": checkpoint_id})
        self.assert_ok(started)
        job = started.get("verification")
        self.assertEqual(job.get("status"), "running", started)
        request_id = job.get("request_id")
        self.assertTrue(request_id, started)
        request_dir = source_root / "stonebench" / "verifications" / request_id
        worker_root = request_dir / "repeater"
        pid_file = worker_root / "server.pid"
        ready_file = worker_root / "stonebench" / "ready"
        deadline = asyncio.get_running_loop().time() + 90
        during_boot = False
        heartbeat_seen = False
        while asyncio.get_running_loop().time() < deadline:
            progress = await self.call(session, "verification_status", {"request_id": request_id})
            self.assert_ok(progress)
            state = progress.get("verification")
            if "verdict" in state:
                self.fail(f"Verification completed before its independent server boot: {state}")
            heartbeat = state.get("progress")
            if heartbeat is not None:
                self.assertTrue(heartbeat.get("phase"), progress)
                self.assertIsInstance(heartbeat.get("progress_sequence"), int, progress)
                heartbeat_seen = True
            if pid_file.exists() and not ready_file.exists() and heartbeat_seen:
                during_boot = True
                break
            if ready_file.exists():
                break
            await asyncio.sleep(0.05)
        self.assertTrue(during_boot, f"Independent repeater server did not expose its boot phase: {request_dir}")
        self.assertTrue(heartbeat_seen, "Running verification must expose an owner heartbeat with phase progress")
        blocked = await self.call(session, "advance", {"ticks": 1})
        self.assertEqual(blocked["status"], "error", "The source world must reject simulation during verification")
        ticks_after_rejected_advance = (await self.call(session, "describe_task"))["simulation_ticks"]
        self.assertEqual(ticks_after_rejected_advance, ticks_before)
        cancellation = await self.call(session, "cancel_verification", {"request_id": request_id})
        self.assert_ok(cancellation)
        self.assertEqual(cancellation["verification"]["status"], "cancelling", cancellation)
        report = await self.wait_for_verification(session, request_id, timeout=120)
        self.assertNotEqual(report["verdict"], "conforms_to_alpha", self.report_context(report))
        self.assertEqual(report["verdict"], "infrastructure_error", self.report_context(report))
        self.assertTrue(report.get("working_construction_preserved"), self.report_context(report))
        self.assertFalse(report.get("working_differences"), self.report_context(report))
        await self.assert_agent_view(session, report)
        after = await self.call(session, "verification_snapshot")
        self.assert_ok(after)
        difference = first_difference(self.frozen_snapshot(before), self.frozen_snapshot(after))
        self.assertIsNone(difference, f"Cancellation changed the frozen source world: {difference}")
        return {"request_id": request_id, "phase": "independent_repeater_boot", "source_advance_rejected": True,
                "cancellation_status": cancellation["verification"]["status"], "verdict": report["verdict"],
                "stop_cause": report["stop_cause"], "source_preservation_difference": difference}

    async def interrupt_worker(self, session, checkpoint_id):
        roots = [Path(item) for item in os.environ.get("STONEBENCH_SERVER_ROOTS", "").split(";") if item]
        source_root = next((root for root in roots if (root / "stonebench" / "checkpoints" / checkpoint_id).exists()), None)
        self.assertIsNotNone(source_root, "The test launcher must expose its own server roots for safe worker interruption")
        config = await self.call(session, "__test_verification_config", {"scenario": "none"})
        self.assert_ok(config)
        before = await self.call(session, "verification_snapshot")
        self.assert_ok(before)
        started = await self.call(session, "verify_checkpoint", {"checkpoint_id": checkpoint_id})
        self.assert_ok(started)
        job = started.get("verification")
        self.assertEqual(job.get("status"), "running", started)
        request_id = job.get("request_id")
        self.assertTrue(request_id, started)
        pid_file = source_root / "stonebench" / "verifications" / request_id / "repeater" / "server.pid"
        deadline = asyncio.get_running_loop().time() + 90
        while asyncio.get_running_loop().time() < deadline and not pid_file.exists():
            progress = await self.call(session, "verification_status", {"request_id": request_id})
            self.assert_ok(progress)
            state = progress.get("verification")
            if "verdict" in state:
                self.fail(f"Verification completed before its test-owned worker PID appeared: {state}")
            await asyncio.sleep(0.05)
        if not pid_file.exists():
            self.fail("Timed out waiting for this request's independent repeater worker PID")
        pid = int(pid_file.read_text(encoding="ascii").strip())
        os.kill(pid, signal.SIGTERM)
        report = await self.wait_for_verification(session, request_id, timeout=120)
        self.assertEqual(report["verdict"], "infrastructure_error", self.report_context(report))
        self.assertIn(report["stop_cause"], {"verification_interrupted", "infrastructure_failure"}, self.report_context(report))
        self.assertIsNotNone(report["infrastructure_error"], report)
        await self.assert_agent_view(session, report)
        self.assertTrue(report.get("working_construction_preserved"), self.report_context(report))
        self.assertFalse(report.get("working_differences"), self.report_context(report))
        after = await self.call(session, "verification_snapshot")
        self.assert_ok(after)
        difference = first_difference(self.frozen_snapshot(before), self.frozen_snapshot(after))
        self.assertIsNone(difference, f"Worker interruption changed the frozen source world: {difference}")
        return {"request_id": request_id, "interrupted_worker_pid": pid,
                "verdict": report["verdict"], "stop_cause": report["stop_cause"],
                "infrastructure_error": report["infrastructure_error"],
                "source_preservation_difference": difference}

    def assert_boundaries_ran_in_minecraft(self, session, report):
        """The independent-copy evidence (copies, operations, geometry rows) comes from the complete local report: MCP no longer carries it."""
        context = self.report_context(report)
        full, _ = self.local(session, report)
        self.assertIsNone(report.get("infrastructure_error"), context)
        self.assertTrue(report.get("worker_artifacts_available_via_mcp"), context)
        self.assertEqual(len(full["copies"]), 2, context)
        self.assertEqual({copy["mode"] for copy in full["copies"]}, {"repeater", "direct"}, context)
        self.assertEqual(len({copy["server_root"] for copy in full["copies"]}), 2, context)
        self.assertEqual(len({copy["mcp_port"] for copy in full["copies"]}), 2, context)
        self.assertTrue(all(copy["restoration"]["status"] == "equal" for copy in full["copies"]), context)
        self.assertTrue(0 < report["transition_ticks"] <= 432000, context)
        required = {("repeater", 1, "open"), ("repeater", 1, "closed"),
                    ("direct", 1, "open"), ("direct", 1, "closed")}
        available = {(row["mode"], row["cycle"], row["expected_state"]) for row in report["boundaries"]}
        self.assertTrue(required.issubset(available), context)
        for key in required:
            shown = self.boundary(report, *key)
            self.assertEqual(shown["rest"]["status"], "terminated", context)  # rest evidence in the agent's own view
            self.assertGreater(shown["ticks_executed"], 0, context)
            row = self.boundary(full, *key)
            operation = row["operation"]
            self.assertEqual(operation["transition"]["status"], "terminated", context)
            self.assertEqual(operation["ticks_executed"], shown["ticks_executed"], context)
            self.assertGreater(operation["ticks_executed"], 0, context)
            self.assertLessEqual(operation["ticks_executed"], 36000, context)
            self.assertTrue(row["trace_complete"], context)
            if key[2] == "closed":
                self.assert_geometry_checkpoint_ready(row["geometry"], context)
            else:
                self.assertEqual(self.criterion_status(row["geometry"], "frame_state"), "satisfied", context)
            if key[2] == "closed":
                self.assertEqual(self.criterion_status(row["geometry"], "regular_arrangement"), "satisfied", context)
                self.assertEqual(self.criterion_status(row["geometry"], "door_composition"), "satisfied", context)

    def assert_geometry_checkpoint_ready(self, geometry, context=None):
        self.assert_ok(geometry)
        required = ("frame_state", "regular_arrangement", "door_composition", "encadrement",
                    "continuable", "input", "no_entities")
        statuses = {identifier: self.criterion_status(geometry, identifier) for identifier in required}
        self.assertEqual(statuses, {identifier: "satisfied" for identifier in required},
                         context or json.dumps({"expected_state": geometry.get("expected_state"),
                                                "criteria": [{key: row.get(key) for key in ("id", "status", "diagnostic")}
                                                             for row in geometry.get("criteria", [])
                                                             if row.get("id") in required]},
                                               ensure_ascii=False, default=str))

    def assert_mode_equivalence(self, report, status):
        for identifier in ("mode_equivalence_open", "mode_equivalence_closed"):
            self.assertEqual(self.report_criterion(report, identifier)["status"], status, self.report_context(report))

    def boundary(self, report, mode, cycle, expected_state):
        return next(row for row in report["boundaries"]
                    if row["mode"] == mode and row["cycle"] == cycle and row["expected_state"] == expected_state)

    def report_criterion(self, report, identifier):
        return next(row for row in report["criteria"] if row["id"] == identifier)

    def criterion_status(self, report, identifier):
        return next(row["status"] for row in report["criteria"] if row["id"] == identifier)

    def evidence_summary(self, report):
        return {key: report.get(key) for key in (
            "request_id", "checkpoint_id", "verdict", "cycles_executed", "stop_cause",
            "transition_ticks", "recurrence_comparisons", "first_difference", "criteria",
            "faults", "boundaries", "worker_artifacts_available_via_mcp", "infrastructure_error",
        )}

    def report_context(self, report):
        criteria = [{key: row.get(key) for key in ("id", "status", "diagnostic")}
                    for row in report.get("criteria", []) if row.get("status") != "satisfied"]
        summary = {key: report.get(key) for key in (
            "request_id", "verdict", "cycles_executed", "stop_cause", "first_difference",
            "infrastructure_error", "limits")}
        summary["non_satisfied_criteria"] = criteria
        summary["faults"] = report.get("faults")
        return json.dumps(summary, ensure_ascii=False, default=str)


if __name__ == "__main__":
    unittest.main(defaultTest="VerificationRuntimeIntegration", verbosity=2)
