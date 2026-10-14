"""Nonsecret pinned campaign inputs and provisional offline cost forecast."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

from app.harness.budget import Budget
from app.harness.inspect_task import PROMPT

TASKS = tuple(f"{size}x{size}-{objective}" for size in range(2, 6) for objective in ("volume", "speed"))
MODEL = "openrouter/openai/gpt-6-luna"
# OpenRouter lists the base endpoint (tag `openai`) beside `openai/flex` and `openai/fast` variants with other prices and
# availability; the observed cost of every response is checked, and the serving endpoint stays in the OpenRouter log.
PROVIDER = {"order": ["openai"], "only": ["openai"], "allow_fallbacks": False}
PROVIDER_NAME = "OpenAI"
BUDGET = Budget(total=2000000, construction_output=32768, final_output=8192,
                final_reasoning=57344, margin=32768, final_calls=8)
CALIBRATION_BUDGET = Budget(total=400000, construction_output=32768, final_output=8192,
                           final_reasoning=57344, margin=32768, final_calls=2)
# Waits before each resend of an identical request after a transient provider/transport failure (connection loss,
# timeout, 429, 5xx). Calibration never resends: it must show the provider's raw behaviour.
GENERATION_RETRY_WAITS = (10, 30)
# No reasoning parameter is sent: the provider default is preserved (xiaomi/mimo-v2.6-flash ignored a 8,000-token cap and
# its documented effort levels do not change real effort, so that model was abandoned on 2026-10-14).
REASONING_REQUEST = None
SECRET_FILE = Path(r"C:\Users\minle\Documents\projets\StoneBench\.runtime\openrouter.env")
PINS = {"minecraft": "1.21.11", "yarn": "1.21.11+build.3", "fabric_loader": "0.19.5",
        "inspect_ai": "0.3.278", "mcp": "1.26.0", "controller": "0.1.0", "protocol": "alpha-issue12-13",
        "tick_execution": "sprint", "seed": 731928, "generator": "flat_air", "random_tick_speed": 0,
        "mob_spawning": False, "advance_weather": False, "players_allowed": False,"openai":"3.29.0"}


def digest(data):
    return sha256(data).hexdigest()


def plan():
    # No cache discount assumed. Reasoning is completion, never a second charge.
    return {"schema": 1, "status": "provisional_offline_not_provider_calibrated", "tasks": list(TASKS),
            "model": MODEL, "provider": PROVIDER, "pins": PINS, "budget": asdict(BUDGET),
            "reasoning_request":REASONING_REQUEST,
            "max_context_bytes":524288,"stop_on_missing_usage":True,
            "generation_retry_waits_seconds":list(GENERATION_RETRY_WAITS),
            "retry_accounting":"a request lost without a response is never counted as usage: total_tokens becomes null, its context+completion bound counts against the budget",
            "calibration_budget": asdict(CALIBRATION_BUDGET), "prompt": PROMPT,
            "input_usd_per_million": {"openai": .10},
            "completion_usd_per_million": .50, "cache_discount_assumed": False,
            "forecast": {"tokens_per_attempt": BUDGET.total, "campaign_tokens": BUDGET.total * len(TASKS),
                "worst_split_usd_per_attempt": 1.0, "worst_split_campaign_usd": 8.0,
                "example_input_fraction": .8, "example_completion_fraction": .2,
                "example_openai_usd_per_attempt": .36,
                "example_openai_campaign_usd": 2.88,
                "calibration_worst_split_usd": .2,
                "conditional_one_inflight_excess_tokens_per_attempt":1114112,
                "conditional_campaign_plus_excess_usd":12.456448,
                "conditional_calibration_plus_excess_usd":.757056,
                "conditional_campaign_plus_excess_and_calibration_usd":13.213504,
                "limitations": "Token total is an observed stop threshold, not a hard monetary cap. One in-flight request, hidden input overhead, retries and provider bound violations can exceed it; actual usage/cost fields remain authoritative."}}


def plan_hash():
    return digest(json.dumps(plan(), sort_keys=True).encode())


def require_authorization(path, mode, *, task_ids=None, task_id=None):
    approved = json.loads(Path(path).read_text(encoding="utf-8"))
    if approved.get("plan_sha256") != plan_hash() or approved.get("scope") != mode or approved.get("authorized_by_user") is not True:
        raise ValueError("Paid scope requires explicit user authorization of this exact plan hash")
    # Calibration cannot silently unlock the eight-task campaign.
    if mode not in {"calibration", "paid"}:
        raise ValueError("Unknown paid scope")
    if mode=="paid":
        allowed=approved.get("task_ids")
        if not isinstance(allowed,list) or not allowed or any(not isinstance(item,str) or item not in TASKS for item in allowed) or len(set(allowed))!=len(allowed):
            raise ValueError("Paid authorization requires an explicit unique task_ids subset")
        if task_ids is not None and list(task_ids)!=allowed:
            raise ValueError("Paid selection must exactly match authorized task_ids")
        if task_id is not None and task_id not in allowed:
            raise ValueError("Direct paid attempt task is outside authorized task_ids")
        if task_ids is None and task_id is None:
            raise ValueError("Paid authorization requires a concrete selected task")


def load_secret(path=SECRET_FILE):
    import os
    key = None
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            if key is not None:
                raise ValueError("Duplicate OPENROUTER_API_KEY entry")
            key = line.split("=", 1)[1].strip()
    if not key:
        raise ValueError("OPENROUTER_API_KEY missing or empty")
    os.environ["OPENROUTER_API_KEY"] = key
    return True
