from snagtrace import CostBudget, Doctor, LoopDetector, Span


def test_doctor_diagnose_picks_earliest_fault_as_first():
    doc = Doctor(detectors=[LoopDetector(window=6, min_repeats=3), CostBudget(max_usd=1.0)])
    spans = [
        Span(step_id=1, tool="search", args={"q": "x"}, cost_usd=0.5),
        Span(step_id=2, tool="search", args={"q": "x"}, cost_usd=0.5),  # cumulative 1.0 -> budget fault here
        Span(step_id=3, tool="search", args={"q": "x"}, cost_usd=0.0),  # 3rd repeat -> loop fault here
    ]
    result = doc.diagnose(spans)
    assert len(result.faults) == 2
    assert result.first_fault.step_id == 2
    assert result.first_fault.category == "COST_RUNAWAY"


def test_doctor_feed_accumulates_spans():
    doc = Doctor(detectors=[LoopDetector(window=6, min_repeats=2)])
    doc.feed(Span(step_id=1, tool="x", args={"a": 1}))
    doc.feed(Span(step_id=2, tool="x", args={"a": 1}))
    result = doc.diagnose()
    assert len(result.faults) == 1


def test_healthy_trace_has_no_first_fault():
    doc = Doctor(detectors=[LoopDetector()])
    result = doc.diagnose([Span(step_id=1, tool="x", args={"a": 1})])
    assert result.is_healthy
    assert result.first_fault is None
