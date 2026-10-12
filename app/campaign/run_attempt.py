"""One fresh server attempt, executed by the existing lifecycle launcher."""
import asyncio
from contextlib import AsyncExitStack
from dataclasses import asdict
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.campaign.plan import BUDGET, CALIBRATION_BUDGET, MODEL, PINS, PROVIDER, digest, load_secret, plan_hash, require_authorization
from app.harness.inspect_task import stonebench_task, encode
import app.harness.scripted
from inspect_ai import eval_async
from inspect_ai.event import ModelEvent
from inspect_ai.model import GenerateConfig, get_model, ModelOutput, ModelUsage, ChatCompletionChoice, ChatMessageAssistant
from inspect_ai.tool import ToolCall, ToolDef, mcp_server_http


def save(root, name, value):
    (root / name).write_text(encode(value), encoding="utf-8")


def provider_records(log):
    rows=[]
    for sample in log.samples or []:
        for event in sample.events:
            if not isinstance(event,ModelEvent):
                continue
            response=event.call.response if event.call and event.call.response else {}
            usage=response.get("usage") or {}
            request=event.call.request if event.call else {}
            choice=(response.get("choices") or [{}])[0]
            message=choice.get("message") or {}
            rows.append({"response_id":response.get("id"),"routing_metadata":response.get("openrouter_metadata"),
                "raw_provider_usage":usage or None,"provider_reported_cost":usage.get("cost"),
                "requested_max_tokens":request.get("max_tokens",request.get("max_completion_tokens")),
                "finish_reason":choice.get("finish_reason"),
                "usable_visible_or_tool_output":bool(message.get("content") or message.get("tool_calls")),
                "inspect_usage_cost_is_not_route_exact":True})
    return rows


async def validate_provider(rows):
    """One metadata read per completed generation; not another inference request."""
    import httpx
    gaps=[]
    if not rows:gaps.append("no_completed_provider_response")
    async with httpx.AsyncClient(timeout=30) as client:
        for row in rows:
            row["generation_metadata"] = None
            if row["response_id"]:
                try:
                    response=await client.get("https://openrouter.ai/api/v1/generation",
                        params={"id":row["response_id"]},headers={"Authorization":"Bearer "+os.environ["OPENROUTER_API_KEY"]})
                    response.raise_for_status()
                    data=response.json()["data"]
                    row["generation_metadata"]={name:data.get(name) for name in ("id","provider_name","total_cost",
                        "tokens_prompt","tokens_completion","native_tokens_prompt","native_tokens_completion",
                        "native_tokens_reasoning","cache_discount","finish_reason")}
                except Exception as exc:
                    row["metadata_error_type"]=type(exc).__name__
            metadata=row["generation_metadata"] or {}
            if metadata.get("provider_name") not in {"Makora","Xiaomi"}:gaps.append("provider_identity_unavailable_or_unexpected")
            if not isinstance(metadata.get("total_cost"),(int,float)):gaps.append("provider_cost_unavailable")
            usage=row["raw_provider_usage"] or {}
            if any(not isinstance(usage.get(name),int) for name in ("prompt_tokens","completion_tokens","total_tokens")):
                gaps.append("provider_token_usage_unavailable")
            elif usage["total_tokens"] != usage["prompt_tokens"]+usage["completion_tokens"]:
                gaps.append("provider_token_usage_inconsistent")
            if row["requested_max_tokens"] is None or (isinstance(usage.get("completion_tokens"),int) and usage["completion_tokens"]>row["requested_max_tokens"]):
                gaps.append("completion_bound_unavailable_or_exceeded")
    return {"accepted":not gaps,"gaps":sorted(set(gaps)),"scope":"observed_requests_not_universal_provider_guarantee"}


async def call(tools, name, **args):
    from app.harness.inspect_task import payload
    value = payload(await tools[name](**args))
    if value.get("status") != "ok":
        raise RuntimeError(f"{name} failed: {encode(value)}")
    return value


def assert_clean(snapshot, listing, description):
    state = snapshot["checkpoint_state"]
    if state["world_time"] != description["preparation_ticks"] or state["time_of_day"] != description["preparation_ticks"]:
        raise RuntimeError("Fresh clocks contain ticks outside declared initial preparation")
    if snapshot["input"] is not None or listing["checkpoints"]:
        raise RuntimeError("Fresh attempt retained input/checkpoints")
    raw = state["state"]
    if any(raw[name] for name in ("block_ticks", "fluid_ticks", "block_events")):
        raise RuntimeError("Fresh attempt retained pending queues/events")
    if any(block["block"] != "minecraft:air" or block.get("inventory") for block in raw["blocks"].values()):
        raise RuntimeError("Fresh observed zone has nonair/inventory state")
    if description["simulation_ticks"] != 0 or not description["frozen"]:
        raise RuntimeError("Fresh attempt contains useful simulation or failed to freeze")
    for name, expected in PINS.items():
        if name in description["environment"] and description["environment"][name] != expected:
            raise RuntimeError(f"Environment drift: {name}")


class Rehearsal:
    """Incomplete stone/chest checkpoint exercises retention; it is not a solver."""
    def __init__(self, attempt, budget, mode):
        self.attempt, self.budget, self.mode = attempt, budget, mode
        self.index = 0
        self.context_bytes = []

    def __call__(self, messages, tools, config):
        self.context_bytes.append(len(encode({"messages": [item.model_dump(mode="json") for item in messages],
            "tools": [tool.model_dump(mode="json") for tool in tools]}).encode()))
        rows = [("describe_task", {}), ("describe_rules", {}), ("describe_blocks", {})]
        sequence = [rows,
            [("modify_blocks", {"blocks": [{"x":1024,"y":79,"z":1024,"block":"minecraft:stone"},
                {"x":1025,"y":79,"z":1024,"block":"minecraft:chest", "parameters":{"facing":"north"},
                 "inventory":[{"slot":0,"item":"minecraft:diamond","count":7}]},
                 {"x":1023,"y":79,"z":1024,"block":"minecraft:lever","parameters":{"face":"wall","facing":"west"}}], "notify_neighbors":True})],
            [("declare_input",{"device":"minecraft:lever","position":{"x":1023,"y":79,"z":1024},
                "orientation":"west","input_block":{"x":1024,"y":79,"z":1024}})],
            [("advance", {"ticks":3,"trace":True})],
            [("transition", {"max_ticks":20,"trace":True})],
            [("create_checkpoint", {})], [("list_checkpoints", {})]]
        if self.index < len(sequence):
            calls = sequence[self.index]
        elif self.index == len(sequence) and self.mode != "no_submission":
            checkpoint = next(json.loads(file.read_text(encoding="utf-8"))["checkpoint"]["checkpoint_id"]
                for file in self.attempt.root.glob("tool-*.json") if '"checkpoint":' in file.read_text(encoding="utf-8"))
            calls = [("submit_checkpoint", {"checkpoint_id":checkpoint})]
        else:
            calls = []
        self.index += 1
        # Controlled usage triggers real finalization after checkpoint publication.
        usage = ModelUsage(input_tokens=200, output_tokens=100, total_tokens=300, reasoning_tokens=90)
        if calls and calls[0][0] == "create_checkpoint":
            usage = ModelUsage(input_tokens=self.budget.total - 100000, output_tokens=100,
                               total_tokens=self.budget.total - 99900, reasoning_tokens=90)
        return ModelOutput(model="stonebench-scripted/campaign-rehearsal", usage=usage,
            choices=[ChatCompletionChoice(message=ChatMessageAssistant(content="Scripted rehearsal", tool_calls=
                [ToolCall(id=f"{self.index}-{i}",function=name,arguments=args) for i,(name,args) in enumerate(calls)] or None),
                stop_reason="tool_calls" if calls else "stop")])


async def run():
    task_id, mode = os.environ["STONEBENCH_CAMPAIGN_TASK"], os.environ["STONEBENCH_CAMPAIGN_MODE"]
    if mode not in {"rehearsal", "calibration", "paid"}:
        raise ValueError("Unknown campaign mode")
    if mode != "rehearsal":
        require_authorization(os.environ["STONEBENCH_CAMPAIGN_AUTHORIZATION"],mode)
    root = Path(os.environ["STONEBENCH_CAMPAIGN_ATTEMPT"])
    root.mkdir(parents=True, exist_ok=False)
    budget = CALIBRATION_BUDGET if mode == "calibration" else BUDGET
    status = {"task_id": task_id, "mode": mode, "status": "infrastructure_error", "plan_sha256": plan_hash(),
        "selected_checkpoint_id":None,"result":{"status":"no_submission","checkpoint_id":None}}
    try:
        for package in ("inspect_ai", "mcp", "openai"):
            if version(package) != PINS[package]:
                raise RuntimeError(f"Version drift: {package}")
        server_root = Path(os.environ["STONEBENCH_SERVER_ROOTS"].split(";")[0])
        status["server_root"] = str(server_root)
        url = f"http://127.0.0.1:{os.environ['STONEBENCH_MCP_PORTS'].split(',')[0]}/mcp"
        async with mcp_server_http(url=url, timeout=2450) as connection:
            discovered = await connection.tools()
            tools = {ToolDef(item).name: item for item in discovered}
            if any(name.startswith("__test") for name in tools):
                raise RuntimeError("Campaign requires production tool catalogue")
            start = await call(tools, "start_attempt", task_id=task_id, budget_tokens=budget.total)
            description = await call(tools, "describe_task")
            empty_positions=description["task"]["expected_frame"]+[{"x":1024,"y":79,"z":1024},
                {"x":1025,"y":79,"z":1024},{"x":1023,"y":79,"z":1024}]
            # The residue control is across a chunk edge. Read_region prepares
            # its coverage frozen; read_blocks deliberately never does that.
            await call(tools,"read_region",min={"x":1023,"y":79,"z":1024},max={"x":1025,"y":79,"z":1024})
            sampled_air=await call(tools,"read_blocks",positions=empty_positions)
            snapshot = await call(tools, "verification_snapshot")
            listing = await call(tools, "list_checkpoints")
            catalogue = [{"name":ToolDef(item).name,"description":ToolDef(item).description,
                          "parameters":ToolDef(item).parameters.model_dump(mode="json")} for item in discovered]
            save(root,"initial.json", {"start":start,"description":description,"snapshot":snapshot,"checkpoints":listing,
                "sampled_air":sampled_air,"catalogue":catalogue,"catalogue_sha256":digest(encode(catalogue).encode()),"reset_checked":False})
            assert_clean(snapshot, listing, description)
            save(root,"reset-check.json",{"checked":True,"preparation_ticks":description["preparation_ticks"],
                "world_time":snapshot["checkpoint_state"]["world_time"],"sampled_positions":empty_positions})
        config = GenerateConfig(temperature=0, parallel_tool_calls=False, max_retries=0, cache_prompt=False,
            extra_headers={"X-OpenRouter-Metadata":"enabled"})
        task, attempt = stonebench_task(url, budget, root / "harness", task_id=task_id, config=config, initialize=False,
            max_context_bytes=524288,stop_on_missing_usage=True)
        if mode == "calibration":
            # At most two provider calls in a read-only phase with the actual schema/context.
            attempt.ledger.finalize("provider_calibration_read_only")
        if mode == "rehearsal":
            script = Rehearsal(attempt,budget,"no_submission" if task_id == "5x5-speed" else "selected")
            model = get_model("stonebench-scripted/campaign-rehearsal",script=script)
        else:
            # Only inherited environment auth; no secret in model args/logs/archive.
            load_secret()
            model = get_model(MODEL,provider=PROVIDER,max_retries=0,reasoning_enabled=True)
        logs = await eval_async(task, model=model, log_dir=str(root / "inspect-logs"), log_format="json",
            log_model_api=True, ctl_server=False, max_samples=1,max_tasks=1,retry_on_error=0)
        log = logs[0]
        if attempt.report is None:
            attempt.report={"status":"no_submission" if attempt.selected is None else "verification_error",
                "checkpoint_id":attempt.selected,"inspect_status":log.status}
            save(attempt.root,"result.json",attempt.report)
        status.update(status=log.status, result=attempt.report, selected_checkpoint_id=attempt.selected,
            total_tokens=attempt.ledger.total_tokens, known_tokens_subtotal=attempt.ledger.known_tokens,
            calls=attempt.ledger.calls, error=log.error.model_dump(mode="json") if log.error else None)
        status["provider_records"] = provider_records(log)
        status["tool_catalogue_sha256"] = digest(encode(catalogue).encode())
        if mode != "rehearsal":
            status["provider_validation"] = await validate_provider(status["provider_records"])
            if mode == "calibration":
                checks=status["provider_validation"].copy()
                contexts=[json.loads(line) for line in (attempt.root/"events.jsonl").read_text(encoding="utf-8").splitlines()
                    if json.loads(line)["kind"]=="before_generation"]
                if len(attempt.ledger.calls)>2:checks["gaps"].append("more_than_two_calibration_calls")
                if not attempt.ledger.usage_complete:checks["gaps"].append("missing_usage")
                if attempt.ledger.known_tokens>budget.total:checks["gaps"].append("calibration_total_exceeded")
                if any(row["finish_reason"]=="length" and not row["usable_visible_or_tool_output"] for row in status["provider_records"]):
                    checks["gaps"].append("reasoning_exhausted_completion_without_usable_response")
                for estimate,reported in zip(contexts,attempt.ledger.calls):
                    actual=(reported["usage"] or {}).get("input_tokens")
                    if actual is None or actual>estimate["context_estimate"]+budget.margin:
                        checks["gaps"].append("input_context_forecast_not_covered_by_margin")
                checks["accepted"]=not checks["gaps"]
                status["calibration_validation"]=checks
        if mode == "rehearsal":
            if log.status != "success" or (task_id == "5x5-speed" and attempt.report["status"] != "no_submission"):
                raise RuntimeError("Rehearsal native Inspect result failed")
            status["offline_context_bytes"] = script.context_bytes
            status["offline_context_is_not_provider_usage"] = True
            # Leave explicit residue so next task's fresh startup proves isolation.
            async with mcp_server_http(url=url, timeout=2450) as connection:
                tools = {ToolDef(item).name:item for item in await connection.tools()}
                residue = await call(tools,"verification_snapshot")
                if residue["checkpoint_state"]["world_time"] <= 0:
                    raise RuntimeError("Isolation control did not leave nonzero clocks")
                if residue["input"] is None:
                    raise RuntimeError("Isolation control did not leave declared input")
                save(root,"residue.json",residue)
        save(root,"status.json",status)
        if log.status != "success":
            raise RuntimeError("Inspect attempt failed; retained status has diagnostics")
    except BaseException as exc:
        status["failure_type"] = type(exc).__name__
        # Provider exception bodies can echo request context; do not persist arbitrary repr.
        save(root,"status.json",status)
        raise


if __name__ == "__main__":
    asyncio.run(run())
