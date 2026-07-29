from snagtrace import Span
from snagtrace.detectors.budget import CostBudget


def test_flags_step_where_budget_is_crossed():
    spans = [
        Span(step_id=1, tool="call", cost_usd=1.0),
        Span(step_id=2, tool="call", cost_usd=1.0),
        Span(step_id=3, tool="call", cost_usd=1.0),  # cumulative = 3.0, crosses 2.5
        Span(step_id=4, tool="call", cost_usd=1.0),
    ]
    faults = CostBudget(max_usd=2.5).check(spans)
    assert len(faults) == 1
    assert faults[0].step_id == 3
    assert faults[0].category == "COST_RUNAWAY"
    assert faults[0].confidence == 1.0


def test_no_fault_under_budget():
    spans = [Span(step_id=i, tool="call", cost_usd=0.1) for i in range(1, 5)]
    faults = CostBudget(max_usd=5.0).check(spans)
    assert faults == []
