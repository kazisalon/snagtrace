from __future__ import annotations

import numbers

from ..core import Detector, Fault, Span


class CostBudget(Detector):
    """Flags the exact step where cumulative trace cost crosses a budget.

    This is deliberately dumb on purpose. A runaway loop is cheap to detect
    by watching the bill, and catching it one step late is far better than
    the alternative, which is finding out eleven days later.
    """

    name = "cost_budget"

    def __init__(self, max_usd: float):
        if not isinstance(max_usd, numbers.Real) or isinstance(max_usd, bool):
            raise TypeError(f"max_usd must be a number, got {type(max_usd).__name__}")
        if max_usd <= 0:
            raise ValueError("max_usd must be positive")
        self.max_usd = max_usd

    def check(self, spans: list[Span]) -> list[Fault]:
        faults: list[Fault] = []
        cumulative = 0.0
        crossed = False
        for span in spans:
            cumulative += span.cost_usd
            if crossed:
                continue
            if cumulative >= self.max_usd:
                crossed = True
                faults.append(
                    Fault(
                        step_id=span.step_id,
                        category="COST_RUNAWAY",
                        confidence=1.0,
                        evidence=(
                            f"cumulative cost reached ${cumulative:.2f} at step "
                            f"{span.step_id}, over the ${self.max_usd:.2f} budget"
                        ),
                        detector=self.name,
                    )
                )
        return faults
