"""Regression tests for bugs found during the fact-check pass:

1. CLI crashed with a raw traceback (instead of a clean exit-2 error) when
   given an invalid --loop-min-repeats, --loop-window, or --max-usd, or a
   write-protected/nonexistent --out path.
2. LoopDetector silently could never fire when window < min_repeats, and
   raised late (inside check(), via deque) instead of at construction for
   a non-positive window.
"""

import pytest

from snagtrace import LoopDetector
from snagtrace.report.cli import main


# --- CLI: bad options must exit cleanly, not crash ------------------------


def test_cli_rejects_non_positive_max_usd_cleanly(tmp_path, capsys):
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"step_id": 1, "tool": "x"}\n')
    exit_code = main(["report", str(trace), "--max-usd", "0"])
    assert exit_code == 2
    assert "invalid option" in capsys.readouterr().err


def test_cli_rejects_loop_min_repeats_below_two_cleanly(tmp_path, capsys):
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"step_id": 1, "tool": "x"}\n')
    exit_code = main(["report", str(trace), "--loop-min-repeats", "1"])
    assert exit_code == 2
    assert "invalid option" in capsys.readouterr().err


def test_cli_rejects_window_smaller_than_min_repeats_cleanly(tmp_path, capsys):
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"step_id": 1, "tool": "x"}\n')
    exit_code = main(["report", str(trace), "--loop-window", "2", "--loop-min-repeats", "3"])
    assert exit_code == 2
    assert "invalid option" in capsys.readouterr().err


def test_cli_bad_out_path_reports_clean_error_not_traceback(tmp_path, capsys):
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"step_id": 1, "tool": "x"}\n')
    bad_out = tmp_path / "no_such_dir" / "report.html"
    exit_code = main(["report", str(trace), "--out", str(bad_out)])
    assert exit_code == 2
    assert "could not write report" in capsys.readouterr().err


# --- LoopDetector: window/min_repeats validation --------------------------


def test_loop_detector_rejects_window_smaller_than_min_repeats():
    with pytest.raises(ValueError, match="window"):
        LoopDetector(window=2, min_repeats=3)


def test_loop_detector_rejects_non_positive_window():
    with pytest.raises(ValueError, match="window"):
        LoopDetector(window=0, min_repeats=2)
    with pytest.raises(ValueError, match="window"):
        LoopDetector(window=-1, min_repeats=2)


def test_loop_detector_accepts_window_equal_to_min_repeats():
    # boundary case: should not raise, and should still be able to fire
    detector = LoopDetector(window=3, min_repeats=3)
    assert detector.window == 3
