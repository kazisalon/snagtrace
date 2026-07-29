"""Regression fixtures modeling real incidents reported against agent
frameworks in the wild, so a detector regression is caught against a
known-real failure, not just a synthetic one.
"""

from snagtrace import ArgSchemaDetector, CostBudget, Doctor, LoopDetector, Span


def test_truncated_write_file_retry_storm():
    """LangGraph #7138: a write_file call truncated at max_tokens produced
    malformed JSON arguments, and the agent retried 249 times without ever
    learning the cause was truncation, not a bad file path."""
    spans = [
        Span(step_id=1, tool="write_file", args=None, tokens=16384, max_tokens=16384, status="ok")
    ]
    spans += [
        Span(step_id=i, tool="write_file", args=None, tokens=16384, max_tokens=16384, status="ok")
        for i in range(2, 250)
    ]

    doc = Doctor(detectors=[ArgSchemaDetector(), LoopDetector(window=6, min_repeats=3)])
    result = doc.diagnose(spans)

    assert result.first_fault.step_id == 1
    assert result.first_fault.category == "TOOL_ARGUMENT_ERROR"


def test_two_agent_ping_pong_cost_runaway():
    """An Analyzer/Verifier pair handing a task back and forth for days,
    reported as an ~$47k bill before anyone noticed."""
    spans = []
    for i in range(1, 41):
        agent = "analyzer" if i % 2 else "verifier"
        target = "verifier" if i % 2 else "analyzer"
        spans.append(
            Span(
                step_id=i,
                agent_id=agent,
                tool="handoff",
                args={"to": target, "task": "review"},
                cost_usd=50.0,
            )
        )

    doc = Doctor(
        detectors=[
            LoopDetector(window=6, min_repeats=3),
            CostBudget(max_usd=500.0),
        ]
    )
    result = doc.diagnose(spans)

    assert not result.is_healthy
    # the budget trips long before the loop detector would otherwise
    # accumulate enough same-agent repeats to fire on its own
    assert result.first_fault.category in {"COST_RUNAWAY", "LOOP_FAILURE"}
    assert result.first_fault.step_id <= 10
