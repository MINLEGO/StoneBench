"""Budget decisions use reported usage; forecasts are explicitly estimates."""
from dataclasses import asdict, dataclass, field
import math


@dataclass(frozen=True)
class Budget:
    total: int
    construction_output: int
    final_output: int
    final_reasoning: int
    margin: int
    final_calls: int = 8
    # shortcut: fixed 2 bytes/token divisor under-forecasts text below 2 bytes/token (real text is ~13), upgrade with per-model token calibration.
    bytes_per_token: int = 2
    # Model window in tokens, compared with the token estimate (a raw-byte limit stopped a run at 10% of the real window).
    context_window_tokens: int = 1000000

    def __post_init__(self):
        positive = {"total", "construction_output", "final_output", "final_calls", "bytes_per_token", "context_window_tokens"}
        for name, value in asdict(self).items():
            if type(value) is not int or value < (1 if name in positive else 0):
                raise ValueError(f"Invalid budget field {name}")
        if self.total <= self.final_output + self.final_reasoning + self.margin:
            raise ValueError("Total must leave room for final context and construction")

    @property
    def final_completion(self):
        # Reasoning is already part of provider completion usage, not a second debit.
        return self.final_output + self.final_reasoning

    def reserve(self, context_estimate):
        return context_estimate + self.final_completion + self.margin

    def fits_window(self, context_estimate, completion):
        return context_estimate + completion <= self.context_window_tokens


@dataclass
class Ledger:
    budget: Budget
    phase: str = "construction"
    known_tokens: int = 0
    usage_complete: bool = True
    calls: list = field(default_factory=list)
    final_calls: int = 0
    transition_reason: str | None = None
    lost: list = field(default_factory=list)
    last_context_bytes: int | None = None
    last_total_tokens: int | None = None
    last_input_tokens: int | None = None

    @property
    def total_tokens(self):
        return self.known_tokens if self.usage_complete and not self.lost else None

    @property
    def committed_tokens(self):
        # A request lost mid-response may still have been billed: its bound counts against the budget, never as usage.
        return self.known_tokens + sum(row["upper_bound_tokens"] for row in self.lost)

    def record_lost(self, upper_bound_tokens, wall_seconds, failure_type, started_utc, ended_utc):
        self.lost.append({"phase": self.phase, "upper_bound_tokens": upper_bound_tokens, "wall_seconds": wall_seconds,
                          "failure_type": failure_type, "started_utc": started_utc, "ended_utc": ended_utc})

    def finalize(self, reason):
        if self.phase == "construction":
            self.phase = "finalization"
            self.transition_reason = reason

    def before_call(self, context_bytes):
        if self.last_total_tokens is None or self.last_context_bytes is None:
            context_estimate = context_bytes
        else:
            # The previous reported total already counts its context and completion; only the growth is estimated.
            growth = max(0, context_bytes - self.last_context_bytes)
            context_estimate = self.last_total_tokens + math.ceil(growth / self.budget.bytes_per_token)
        observed_bytes_per_token = self.last_context_bytes / self.last_input_tokens if self.last_context_bytes and self.last_input_tokens else None
        self.last_context_bytes = context_bytes
        reserve = self.budget.reserve(context_estimate)
        forecast = context_estimate + self.budget.construction_output
        if not self.usage_complete:
            self.finalize("usage_unavailable")
        elif self.committed_tokens + forecast + reserve > self.budget.total:
            self.finalize("next_construction_call_would_enter_reserve")
        elif not self.budget.fits_window(context_estimate, self.budget.construction_output + self.budget.final_completion + self.budget.margin):
            # The final request must still fit the model window after one more construction call.
            self.finalize("next_construction_call_would_exceed_context_window")
        if self.phase == "finalization":
            self.final_calls += 1
        return {"phase": self.phase, "total_budget": self.budget.total,
                "used_tokens": self.total_tokens, "known_tokens_subtotal": self.known_tokens,
                "lost_requests": len(self.lost), "lost_upper_bound_tokens": self.committed_tokens - self.known_tokens,
                "reserve_estimate": reserve, "context_estimate": context_estimate,
                "context_bytes": context_bytes, "observed_bytes_per_token": observed_bytes_per_token,
                "next_construction_forecast": forecast, "transition_reason": self.transition_reason}

    def record(self, usage, wall_seconds):
        values = {name: getattr(usage, name) if name in usage.model_fields_set else None
                  for name in type(usage).model_fields} if usage is not None else None
        if values is None or values["total_tokens"] is None:
            self.usage_complete = False
            self.last_total_tokens = self.last_input_tokens = None
        else:
            self.known_tokens += values["total_tokens"]
            # Full input including cached tokens: the reported total minus the completion.
            self.last_total_tokens = values["total_tokens"]
            self.last_input_tokens = values["total_tokens"] - values["output_tokens"] if values["output_tokens"] is not None else None
        self.calls.append({"phase": self.phase, "usage": values, "wall_seconds": wall_seconds,
                           "known_tokens_subtotal": self.known_tokens,
                           "budget_exceeded_observed": self.known_tokens > self.budget.total})
        if not self.usage_complete:
            self.finalize("usage_unavailable")
        elif self.committed_tokens >= self.budget.total:
            self.finalize("observed_budget_exhausted")

    def can_continue(self):
        return ((not self.usage_complete or self.committed_tokens < self.budget.total)
                and (self.phase != "finalization" or self.final_calls < self.budget.final_calls))
