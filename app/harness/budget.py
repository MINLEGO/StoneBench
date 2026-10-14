"""Budget decisions use reported usage; forecasts are explicitly estimates."""
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Budget:
    total: int
    construction_output: int
    final_output: int
    final_reasoning: int
    margin: int
    final_calls: int = 8

    def __post_init__(self):
        for name, value in asdict(self).items():
            if type(value) is not int or value < (1 if name in {"total", "construction_output", "final_output", "final_calls"} else 0):
                raise ValueError(f"Invalid budget field {name}")
        if self.total <= self.final_output + self.final_reasoning + self.margin:
            raise ValueError("Total must leave room for final context and construction")

    @property
    def final_completion(self):
        # Reasoning is already part of provider completion usage, not a second debit.
        return self.final_output + self.final_reasoning

    def reserve(self, context_estimate):
        return context_estimate + self.final_completion + self.margin


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

    def before_call(self, context_estimate):
        reserve = self.budget.reserve(context_estimate)
        forecast = context_estimate + self.budget.construction_output
        if not self.usage_complete:
            self.finalize("usage_unavailable")
        elif self.committed_tokens + forecast + reserve > self.budget.total:
            self.finalize("next_construction_call_would_enter_reserve")
        if self.phase == "finalization":
            self.final_calls += 1
        return {"phase": self.phase, "total_budget": self.budget.total,
                "used_tokens": self.total_tokens, "known_tokens_subtotal": self.known_tokens,
                "lost_requests": len(self.lost), "lost_upper_bound_tokens": self.committed_tokens - self.known_tokens,
                "reserve_estimate": reserve, "context_estimate": context_estimate,
                "next_construction_forecast": forecast, "transition_reason": self.transition_reason}

    def record(self, usage, wall_seconds):
        values = {name: getattr(usage, name) if name in usage.model_fields_set else None
                  for name in type(usage).model_fields} if usage is not None else None
        if values is None or values["total_tokens"] is None:
            self.usage_complete = False
        else:
            self.known_tokens += values["total_tokens"]
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
