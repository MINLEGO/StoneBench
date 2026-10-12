"""Nonsecret pinned campaign inputs and provisional offline cost forecast."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

from app.harness.budget import Budget
from app.harness.inspect_task import PROMPT

TASKS = tuple(f"{size}x{size}-{objective}" for size in range(2, 6) for objective in ("volume", "speed"))
MODEL = "openrouter/xiaomi/mimo-v2.6-flash"
PROVIDER = {"order": ["makora/fp8", "xiaomi/fp8"], "only": ["makora/fp8", "xiaomi/fp8"],
            "allow_fallbacks": False, "quantizations": ["fp8"]}
BUDGET = Budget(total=2000000, construction_output=32768, final_output=8192,
                final_reasoning=57344, margin=32768, final_calls=8)
CALIBRATION_BUDGET = Budget(total=400000, construction_output=32768, final_output=8192,
                           final_reasoning=57344, margin=32768, final_calls=2)
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
            "reasoning_request":{"enabled":True},
            "max_context_bytes":524288,"stop_on_missing_usage":True,
            "calibration_budget": asdict(CALIBRATION_BUDGET), "prompt": PROMPT,
            "input_usd_per_million": {"makora/fp8": .13, "xiaomi/fp8": .14},
            "completion_usd_per_million": .28, "cache_discount_assumed": False,
            "forecast": {"tokens_per_attempt": BUDGET.total, "campaign_tokens": BUDGET.total * len(TASKS),
                "worst_split_usd_per_attempt": .56, "worst_split_campaign_usd": 4.48,
                "example_input_fraction": .8, "example_completion_fraction": .2,
                "example_makora_usd_per_attempt": .32, "example_xiaomi_usd_per_attempt": .336,
                "example_makora_campaign_usd": 2.56, "example_xiaomi_campaign_usd": 2.688,
                "calibration_worst_split_usd": .112,
                "conditional_one_inflight_excess_tokens_per_attempt":1114112,
                "conditional_campaign_plus_excess_usd":6.97561088,
                "conditional_campaign_plus_excess_and_calibration_usd":7.08761088,
                "limitations": "Token total is an observed stop threshold, not a hard monetary cap. One in-flight request, hidden input overhead, retries and provider bound violations can exceed it; actual usage/cost fields remain authoritative."}}


def plan_hash():
    return digest(json.dumps(plan(), sort_keys=True).encode())


def require_authorization(path, mode):
    approved = json.loads(Path(path).read_text(encoding="utf-8"))
    if approved.get("plan_sha256") != plan_hash() or approved.get("scope") != mode or approved.get("authorized_by_user") is not True:
        raise ValueError("Paid scope requires explicit user authorization of this exact plan hash")
    # Calibration cannot silently unlock the eight-task campaign.
    if mode not in {"calibration", "paid"}:
        raise ValueError("Unknown paid scope")


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
