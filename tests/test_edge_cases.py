import json

import pytest

from snagtrace import ArgSchemaDetector, CostBudget, Doctor, LoopDetector, Span
from snagtrace.core import Fault
from snagtrace.report.cli import _load_spans, main


# --- Doctor / core -----------------------------------------------------


def test_diagnose_on_empty_trace():
    result = Doctor(detectors=[LoopDetector(), ArgSchemaDetector(), CostBudget(max_usd=1.0)]).diagnose([])
    assert result.is_healthy
    assert result.first_fault is None
    assert result.faults == []


def test_diagnose_with_no_detectors_is_always_healthy():
    result = Doctor(detectors=[]).diagnose([Span(step_id=1, tool="x")])
    assert result.is_healthy


def test_single_span_never_loops():
    result = Doctor(detectors=[LoopDetector(window=6, min_repeats=2)]).diagnose(
        [Span(step_id=1, tool="x", args={"a": 1})]
    )
    assert result.is_healthy


def test_first_fault_ties_broken_by_step_id_not_insertion_order():
    faults = [
        Fault(step_id=5, category="LOOP_FAILURE", confidence=0.9, evidence="e", detector="loop"),
        Fault(step_id=2, category="COST_RUNAWAY", confidence=1.0, evidence="e", detector="cost"),
    ]
    from snagtrace.core import DiagnosisResult

    result = DiagnosisResult(faults=faults)
    assert result.first_fault.step_id == 2


def test_span_to_dict_and_back_round_trips():
    span = Span(step_id=1, tool="search", args={"q": "x"}, cost_usd=0.5)
    restored = Span.from_dict(json.loads(json.dumps(span.to_dict())))
    assert restored == span


# --- LoopDetector boundaries --------------------------------------------


def test_loop_detector_rejects_min_repeats_below_two():
    with pytest.raises(ValueError):
        LoopDetector(min_repeats=1)


def test_loop_detector_exactly_at_boundary_does_not_flag_one_short():
    spans = [Span(step_id=i, tool="x", args={"a": 1}) for i in (1, 2)]
    faults = LoopDetector(window=6, min_repeats=3).check(spans)
    assert faults == []


def test_loop_detector_window_smaller_than_repeat_span_still_flags():
    # repeats fall within the window even if separated by other calls,
    # as long as the window covers all of them
    spans = [
        Span(step_id=1, tool="x", args={"a": 1}),
        Span(step_id=2, tool="y", args={"b": 1}),
        Span(step_id=3, tool="x", args={"a": 1}),
        Span(step_id=4, tool="x", args={"a": 1}),
    ]
    faults = LoopDetector(window=4, min_repeats=3).check(spans)
    assert len(faults) == 1
    assert faults[0].step_id == 4


# --- CostBudget boundaries -----------------------------------------------


def test_cost_budget_rejects_non_positive_max_usd():
    with pytest.raises(ValueError):
        CostBudget(max_usd=0)
    with pytest.raises(ValueError):
        CostBudget(max_usd=-1.0)


def test_cost_budget_flags_only_once_even_if_still_accumulating():
    spans = [Span(step_id=i, tool="x", cost_usd=1.0) for i in range(1, 10)]
    faults = CostBudget(max_usd=2.0).check(spans)
    assert len(faults) == 1


# --- ArgSchemaDetector edge cases -----------------------------------------


def test_arg_schema_ignores_non_tool_call_spans():
    span = Span(step_id=1, kind="message", tool=None, args=None)
    faults = ArgSchemaDetector().check([span])
    assert faults == []


def test_arg_schema_ignores_error_without_matching_keyword():
    span = Span(step_id=1, tool="search", args={"q": "x"}, status="error", error="ConnectionTimeout")
    faults = ArgSchemaDetector().check([span])
    assert faults == []


# --- CLI -------------------------------------------------------------------


def test_cli_missing_trace_file_reports_clean_error(tmp_path, capsys):
    missing = tmp_path / "does_not_exist.jsonl"
    exit_code = main(["report", str(missing)])
    assert exit_code == 2
    assert "no such file" in capsys.readouterr().err


def test_cli_malformed_json_line_reports_line_number(tmp_path, capsys):
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"step_id": 1, "tool": "x"}\n{not valid json\n')
    exit_code = main(["report", str(trace)])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert f"{trace}:2" in err


def test_cli_skips_blank_lines(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        '{"step_id": 1, "tool": "x", "args": {"a": 1}}\n\n'
        '{"step_id": 2, "tool": "x", "args": {"a": 1}}\n'
    )
    spans = _load_spans(str(trace))
    assert len(spans) == 2


def test_cli_returns_zero_on_healthy_trace(tmp_path, capsys):
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"step_id": 1, "tool": "x", "args": {"a": 1}}\n')
    exit_code = main(["report", str(trace)])
    assert exit_code == 0
    assert "no faults detected" in capsys.readouterr().out


def test_cli_returns_one_on_faulty_trace(tmp_path):
    trace = tmp_path / "trace.jsonl"
    lines = [json.dumps({"step_id": i, "tool": "x", "args": {"a": 1}}) for i in range(1, 4)]
    trace.write_text("\n".join(lines))
    exit_code = main(["report", str(trace), "--loop-min-repeats", "3"])
    assert exit_code == 1
