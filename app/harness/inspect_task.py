"""Native Inspect execution with a local, irreversible tool guard."""
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import time

from tenacity import RetryError

from inspect_ai import Task
from inspect_ai.agent import AgentState, agent, as_solver, react
from inspect_ai.dataset import Sample
from inspect_ai.event import ModelEvent
from inspect_ai.log import transcript
from inspect_ai.util import LimitExceededError
from inspect_ai.model import ChatMessageUser, GenerateConfig, get_model
from inspect_ai.scorer import Score, scorer
from inspect_ai.solver import solver
from inspect_ai.tool import Tool, ToolDef, ToolError, mcp_server_http, tool

from . import audit
from .budget import Budget, Ledger

READ_TOOLS = frozenset({"describe_task", "describe_blocks", "describe_block", "describe_rules", "read_blocks", "read_region",
    "read_artifact", "compare_traces", "check_geometry", "list_checkpoints", "verification_snapshot",
    "verify_checkpoint", "verification_status", "cancel_verification"})
WRITE_TOOLS = frozenset({"modify_blocks", "advance", "transition", "declare_input", "prepare_input",
    "act_input", "create_checkpoint", "restore_checkpoint"})
PROMPT = """Construct the task's regular DOOR using the discovered StoneBench MCP tools.
Read the task, rules and diagnostic limits. List block ids with describe_blocks; call describe_block only for a block whose details you need. Game ticks and wall time are separate.
Save immutable checkpoints only at established rest; incomplete constructions may be saved.
Work in short loops: decide only the next small step, place it with modify_blocks, observe the real result
(advance or transition, read_region, check_geometry), then correct. Do not design the whole door in your head:
reasoning that was never tested in the world is unreliable and counts against your budget. A simple door that
you built and observed is worth more than an optimal design that exists only in thought. Once something
stands at rest, save a checkpoint, then improve it.
The harness reports phase and budget before each model call. Reported tokens include construction
and finalization (including reasoning). Forecasts are estimates. In finalization you may consult,
verify independent copies and select an existing checkpoint, but cannot mutate, actuate, advance
or restore the working world. Call submit_checkpoint with exactly the checkpoint_id you choose,
even if incomplete. No explicit valid selection means no submission; prose is not a selection.
Verification reports, not your own assessment, determine conformity. Never invent a checkpoint ID.
"""


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=lambda item: item.model_dump(mode="json"))


def payload(result):
    if isinstance(result, str):
        return json.loads(result)
    texts = [item.text for item in result if getattr(item, "type", None) == "text"]
    if len(texts) != 1:
        raise ToolError("Expected a single JSON StoneBench MCP result")
    return json.loads(texts[0])


class Attempt:
    def __init__(self, budget: Budget, artifact_dir: Path, tool_output_bytes=16384,
                 max_context_bytes=None, stop_on_missing_usage=False, server_root=None, generation_retry_waits=()):
        self.server_root = server_root
        # One entry per resend of the same request after a transient transport/provider failure; empty means never resend.
        self.generation_retry_waits = tuple(generation_retry_waits)
        self.ledger = Ledger(budget)
        self.root = Path(artifact_dir)
        self.root.mkdir(parents=True, exist_ok=False)
        self.output_bytes = tool_output_bytes
        if type(tool_output_bytes) is not int or tool_output_bytes < 1024:
            raise ValueError("tool_output_bytes must be an integer >=1024")
        self.selected = None
        self.tools = {}
        self.lock = asyncio.Lock()
        self.sequence = 0
        self.report = None
        self.catalog = []
        self.verification_jobs = set()
        self.max_context_bytes = max_context_bytes
        self.stop_on_missing_usage = stop_on_missing_usage

    def event(self, kind, **values):
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(encode({"kind": kind, "phase": self.ledger.phase, **values}) + "\n")

    def retain(self, name, result):
        self.sequence += 1
        data = encode(result).encode("utf-8")
        file = f"tool-{self.sequence:06d}.json"
        (self.root / file).write_bytes(data)
        self.event("tool_result", tool=name, artifact=file, sha256=sha256(data).hexdigest(), bytes=len(data))
        if len(data) <= self.output_bytes:
            return data.decode("utf-8")
        # Full data is retained and can be paged, rather than silently truncated.
        return encode({"result_output_bounded": True, "artifact": file, "bytes": len(data),
                       "sha256": sha256(data).hexdigest(),
                       "instruction": "Use read_harness_artifact with explicit offset/limit to recover this full result."})

    async def invoke(self, name, arguments):
        async with self.lock:
            self.event("tool_call", tool=name, arguments=arguments)
            if name not in self.tools or (self.ledger.phase == "finalization" and name not in READ_TOOLS):
                self.event("tool_refused", tool=name, reason="finalization_guard" if name in self.tools else "unknown_tool")
                raise ToolError(f"{name} refused in {self.ledger.phase}; working world unchanged by this refused call")
            started = time.monotonic()
            try:
                result = await self.tools[name](**arguments)
                value = payload(result)
            except Exception as exc:
                self.event("tool_error", tool=name, error=str(exc), wall_seconds=time.monotonic() - started)
                raise
            if name == "verify_checkpoint" and value.get("status") == "ok":
                job = value.get("verification", {})
                if job.get("request_id"):
                    self.verification_jobs.add(job["request_id"])
            self.event("tool_completed", tool=name, wall_seconds=time.monotonic() - started,
                       ticks_executed=value.get("ticks_executed"), status=value.get("status"),
                       operation_id=value.get("operation_id"), mutated=value.get("mutated"))
            return self.retain(name, value)

    def wrap(self, original):
        definition = ToolDef(original)
        self.tools[definition.name] = original
        self.catalog.append({"name": definition.name, "description": definition.description,
                             "parameters": definition.parameters.model_dump(mode="json")})
        async def execute(**kwargs):
            return await self.invoke(definition.name, kwargs)
        return ToolDef(execute, name=definition.name, description=definition.description,
                       parameters=definition.parameters, parallel=False, max_output=0).as_tool()

    def local_tools(self):
        @tool
        def submit_checkpoint():
            async def execute(checkpoint_id: str) -> str:
                """Select exactly one existing immutable checkpoint for final scoring.

                Args:
                    checkpoint_id: Exact existing checkpoint ID explicitly chosen by you.
                """
                if self.selected is not None:
                    raise ToolError("A checkpoint has already been explicitly selected")
                try:
                    listing = payload(await self.tools["list_checkpoints"]())
                    checkpoints = listing["checkpoints"]
                    if listing.get("status") != "ok" or not any(row["checkpoint_id"] == checkpoint_id for row in checkpoints):
                        raise ToolError("checkpoint_id does not name an existing published checkpoint")
                except Exception as exc:
                    self.event("submission_invalid", checkpoint_id=checkpoint_id, error=str(exc))
                    raise ToolError(str(exc)) from exc
                self.ledger.finalize("explicit_checkpoint_submission")
                self.selected = checkpoint_id
                self.event("submission_selected", checkpoint_id=checkpoint_id)
                return encode({"status": "selected", "checkpoint_id": checkpoint_id})
            return execute

        @tool
        def read_harness_artifact():
            async def execute(artifact: str, offset: int = 0, limit: int = 4096) -> str:
                """Read a bounded byte page of a full retained tool result.

                Args:
                    artifact: Exact tool-NNNNNN.json result reference.
                    offset: Nonnegative byte offset.
                    limit: Byte count from 1 to 4096.
                """
                import re
                if not re.fullmatch(r"tool-\d{6}\.json", artifact) or offset < 0 or not 1 <= limit <= 4096:
                    raise ToolError("Invalid artifact/page")
                data = (self.root / artifact).read_bytes()
                import base64
                return encode({"artifact": artifact, "offset": offset, "size": len(data),
                               "next_offset": offset + limit if offset + limit < len(data) else None,
                               "encoding": "base64_utf8_bytes", "data": base64.b64encode(data[offset:offset+limit]).decode()})
            return execute
        return [submit_checkpoint(), read_harness_artifact()]

    async def scoring_call(self, name, **arguments):
        if name not in READ_TOOLS:
            raise RuntimeError("Scorer cannot mutate the working world")
        started = time.monotonic()
        self.event("scoring_tool_call", tool=name, arguments=arguments)
        response = payload(await self.tools[name](**arguments))
        self.event("scoring_tool_completed", tool=name, status=response.get("status"),
            ticks_executed=response.get("ticks_executed"), mutated=response.get("mutated"),
            operation_id=response.get("operation_id"), wall_seconds=time.monotonic() - started)
        return response

    async def wait_job(self, request_id):
        while True:
            response = await self.scoring_call("verification_status", request_id=request_id)
            if response.get("status") != "ok" or "verdict" in response.get("verification", {}):
                return response
            await asyncio.sleep(.25)

    async def verify_selected(self):
        if self.selected is None:
            return {"status": "no_submission", "checkpoint_id": None}
        # A submitted selection may arrive while the agent's independent copy still runs.
        for request_id in self.verification_jobs:
            await self.wait_job(request_id)
        started = await self.scoring_call("verify_checkpoint", checkpoint_id=self.selected)
        self.retain("score_verify_checkpoint", started)
        if started.get("status") != "ok":
            return {"status": "verification_error", "checkpoint_id": self.selected, "diagnostic": started}
        request = started["verification"]["request_id"]
        # Existing supervisor enforces independent phase/liveness watchdogs; no global tick/time quota.
        response = await self.wait_job(request)
        report = response.get("verification", {})
        if response.get("status") != "ok":
            return {"status": "verification_error", "checkpoint_id": self.selected, "diagnostic": response}
        self.retain("score_verification_report", response)
        if report.get("checkpoint_id") != self.selected:
            raise RuntimeError("Verifier returned a different checkpoint identity")
        # The positive/negative decision comes from the complete local audit, never from the MCP response alone.
        try:
            if self.server_root is None:
                raise audit.AuditError("No local server root configured for the audit")
            local = audit.load(self.server_root, request, self.selected, report)
        except audit.AuditError as exc:
            self.event("audit_rejected", checkpoint_id=self.selected, request_id=request, error=str(exc))
            return {"status": "audit_error", "checkpoint_id": self.selected, "verification": report, "audit": {"error": str(exc)}}
        self.event("audit_read", **{key: local[key] for key in ("attempt_id", "request_id", "checkpoint_id", "manifest_sha256", "sha256", "complete", "missing")})
        return {"status": "submitted", "checkpoint_id": self.selected, "verification": report,
                # `verification` is what the agent saw; the complete local report (provenance, raw transitions, measurements) is the scorer's own record.
                "audit": {key: local[key] for key in ("attempt_id", "request_id", "checkpoint_id", "manifest_sha256", "path", "sha256", "complete", "missing", "report")},
                "audit_positive": audit.positive(local)}


def unwrap_failure(exc):
    # With Inspect's own retries off, tenacity wraps the provider's exception in a RetryError.
    return exc.last_attempt.exception() if isinstance(exc, RetryError) else exc


def transient_failure(exc):
    """Only the provider's own transient classification (connection loss, timeouts, 429, 5xx) is resent."""
    cause = unwrap_failure(exc)
    return isinstance(cause, Exception) and bool(get_model().api.should_retry(cause))


@agent
def budgeted_generation(attempt: Attempt, config: GenerateConfig):
    async def execute(state: AgentState, tools: list[Tool]):
        schema = [{"name": ToolDef(item).name, "description": ToolDef(item).description,
                   "parameters": ToolDef(item).parameters.model_dump(mode="json")} for item in tools]
        context_bytes = len(encode({"messages": [item.model_dump(mode="json") for item in state.messages],
                                    "tool_schemas": schema}).encode("utf-8")) + 1024
        if attempt.max_context_bytes is not None and context_bytes > attempt.max_context_bytes:
            attempt.event("context_guard_stop", context_bytes=context_bytes, max_context_bytes=attempt.max_context_bytes)
            raise ToolError("Serialized context exceeds campaign client byte guard; no provider request sent")
        status = attempt.ledger.before_call(context_bytes)
        notice = "StoneBench phase/budget: " + encode(status)
        if attempt.ledger.phase == "finalization":
            notice += " Finalization now: consult/verify copies and call submit_checkpoint with your chosen existing ID. No mutation/restore/advance permitted."
        state.messages.append(ChatMessageUser(content=notice))
        bound = attempt.ledger.budget.final_completion if attempt.ledger.phase == "finalization" else attempt.ledger.budget.construction_output
        attempt.event("before_generation", **status, max_tokens=bound)
        history_start = len(transcript().events)
        failures = 0
        while True:
            started = time.monotonic()
            started_utc = datetime.now(timezone.utc).isoformat()
            try:
                state.output = await get_model().generate(state.messages, tools=tools,
                    config=config.model_copy(update={"max_tokens": bound, "parallel_tool_calls": False}))
                break
            except LimitExceededError as exc:
                # Inspect records the completed ModelEvent before its token limit raises.
                completed = [event.output for event in transcript().events[history_start:]
                             if isinstance(event, ModelEvent) and event.output is not None]
                usage = completed[-1].usage if completed else None
                attempt.ledger.record(usage, time.monotonic() - started)
                attempt.event("generation_usage", **attempt.ledger.calls[-1], inspect_limit=exc.type,
                    completion_bound_exceeded_observed=usage is not None and usage.output_tokens > bound)
                raise
            except BaseException as exc:
                if failures < len(attempt.generation_retry_waits) and transient_failure(exc):
                    # The provider may have accepted and billed this request: charge its bound, report no usage.
                    wait = attempt.generation_retry_waits[failures]
                    attempt.ledger.record_lost(status["context_estimate"] + bound, time.monotonic() - started, type(unwrap_failure(exc)).__name__,
                                               started_utc, datetime.now(timezone.utc).isoformat())
                    attempt.event("generation_request_lost", **attempt.ledger.lost[-1], retry_in_seconds=wait)
                    failures += 1
                    await asyncio.sleep(wait)
                    continue
                completed = [event.output for event in transcript().events[history_start:]
                             if isinstance(event, ModelEvent) and event.output is not None]
                usage = completed[-1].usage if completed else None
                attempt.ledger.record(usage, time.monotonic() - started)
                attempt.event("generation_failed", **attempt.ledger.calls[-1], failure_type=type(exc).__name__)
                raise
        attempt.ledger.record(state.output.usage, time.monotonic() - started)
        attempt.event("generation_usage", **attempt.ledger.calls[-1], stop_reason=state.output.stop_reason,
                      completion_bound_exceeded_observed=state.output.usage is not None and state.output.usage.output_tokens > bound)
        state.messages.append(state.output.message)
        return state
    return execute


def stonebench_task(mcp_url: str, budget: Budget, artifact_dir: Path, task_id="2x2-volume",
                    config: GenerateConfig | None = None, initialize=True, prompt=PROMPT,
                    max_context_bytes=None, stop_on_missing_usage=False, server_root=None, generation_retry_waits=()):
    """One task, one attempt, one server; create a fresh Task for each attempt.

    `server_root` is the server's local directory; the scorer reads its complete verification audit there.
    Without it a selected checkpoint cannot score positively."""
    config = config or GenerateConfig()
    if config.extra_headers and config.extra_headers != {"X-OpenRouter-Metadata": "enabled"}:
        raise ValueError("Only nonsecret OpenRouter response metadata may be requested through recorded headers; authentication belongs in provider environment")
    if not isinstance(prompt, str):
        raise ValueError("Alpha harness requires a text prompt")
    attempt = Attempt(budget, artifact_dir, max_context_bytes=max_context_bytes,
                      stop_on_missing_usage=stop_on_missing_usage, server_root=server_root,
                      generation_retry_waits=generation_retry_waits)
    server = mcp_server_http(url=mcp_url, name="stonebench", timeout=2450)

    @solver
    def execute_attempt():
        async def solve(state, generate):
            async with server:
                discovered = await server.tools()
                definitions = {ToolDef(item).name: item for item in discovered}
                if initialize:
                    started = payload(await definitions["start_attempt"](task_id=task_id, budget_tokens=budget.total))
                    attempt.retain("start_attempt", started)
                    if started.get("status") != "ok":
                        raise RuntimeError("Cannot initialize StoneBench attempt")
                tools = [attempt.wrap(item) for name, item in definitions.items() if name in READ_TOOLS | WRITE_TOOLS]
                local = attempt.local_tools()
                tools.extend(local)
                attempt.catalog.extend({"name": ToolDef(item).name, "description": ToolDef(item).description,
                    "parameters": ToolDef(item).parameters.model_dump(mode="json")} for item in local)
                async def on_continue(agent_state):
                    return (attempt.selected is None and attempt.ledger.can_continue()
                        and (not attempt.stop_on_missing_usage or attempt.ledger.usage_complete)
                        and bool(agent_state.output.message.tool_calls))
                native = react(tools=tools, prompt=prompt, submit=False, model=budgeted_generation(attempt, config), on_continue=on_continue)
                try:
                    state = await as_solver(native)(state, generate)
                finally:
                    state.metadata["stonebench"] = {"selected_checkpoint_id": attempt.selected,
                        "total_tokens": attempt.ledger.total_tokens, "known_tokens_subtotal": attempt.ledger.known_tokens,
                        "phase": attempt.ledger.phase, "calls": attempt.ledger.calls,
                        "lost_requests": attempt.ledger.lost, "generation_retry_waits": list(attempt.generation_retry_waits)}
                    (attempt.root / "run.json").write_text(encode({"inspect_version": version("inspect_ai"), "mcp_version": version("mcp"),
                        "prompt": prompt, "tool_catalogue": attempt.catalog, "budget": asdict(budget),
                        "generation_config": config.model_dump(mode="json"), "model": str(get_model()),
                        "max_context_bytes": attempt.max_context_bytes, "stop_on_missing_usage": attempt.stop_on_missing_usage,
                        **state.metadata["stonebench"]}), encoding="utf-8")
            return state
        return solve

    @scorer(metrics=[])
    def selected_checkpoint():
        async def score(state, target):
            async with server:
                attempt.tools = {ToolDef(item).name: item for item in await server.tools() if ToolDef(item).name in READ_TOOLS | WRITE_TOOLS}
                try:
                    attempt.report = await attempt.verify_selected()
                except Exception as exc:
                    attempt.event("scoring_error", error=str(exc), checkpoint_id=attempt.selected)
                    attempt.report = {"status": "verification_error", "checkpoint_id": attempt.selected,
                                      "diagnostic": str(exc)}
            (attempt.root / "result.json").write_text(encode(attempt.report), encoding="utf-8")
            return Score(value=int(attempt.report.get("audit_positive") is True), answer=attempt.selected,
                         explanation=attempt.report["status"], metadata=attempt.report)
        return score

    task = Task(dataset=[Sample(input=f"Build StoneBench {task_id}; read describe_task first.", id=task_id)],
                solver=execute_attempt(), scorer=selected_checkpoint(), token_limit=budget.total,
                metadata={"budget": asdict(budget), "inspect_version": version("inspect_ai"), "mcp_url": mcp_url})
    return task, attempt
