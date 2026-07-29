from snagtrace import Span
from snagtrace.detectors.loop import LoopDetector


def make_span(step_id, agent_id="a", tool="search", args=None):
    return Span(step_id=step_id, agent_id=agent_id, tool=tool, args=args or {"q": "x"})


def test_flags_repeated_identical_calls():
    spans = [make_span(i) for i in range(1, 5)]  # 4 identical calls
    faults = LoopDetector(window=6, min_repeats=3).check(spans)
    assert len(faults) == 1
    assert faults[0].category == "LOOP_FAILURE"
    assert faults[0].step_id == 3  # localized to the 3rd (min_repeats-th) occurrence


def test_does_not_flag_varied_calls():
    spans = [make_span(i, args={"q": f"query-{i}"}) for i in range(1, 5)]
    faults = LoopDetector(window=6, min_repeats=3).check(spans)
    assert faults == []


def test_only_flags_once_per_signature():
    spans = [make_span(i) for i in range(1, 8)]
    faults = LoopDetector(window=6, min_repeats=3).check(spans)
    assert len(faults) == 1


def test_delegation_ping_pong_between_two_agents():
    spans = [
        make_span(1, agent_id="analyzer", tool="handoff", args={"to": "verifier"}),
        make_span(2, agent_id="verifier", tool="handoff", args={"to": "analyzer"}),
        make_span(3, agent_id="analyzer", tool="handoff", args={"to": "verifier"}),
        make_span(4, agent_id="verifier", tool="handoff", args={"to": "analyzer"}),
        make_span(5, agent_id="analyzer", tool="handoff", args={"to": "verifier"}),
    ]
    faults = LoopDetector(window=6, min_repeats=3).check(spans)
    categories = {f.category for f in faults}
    assert "LOOP_FAILURE" in categories
