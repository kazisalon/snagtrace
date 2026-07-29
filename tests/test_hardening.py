"""Regression tests for the senior-review hardening pass:

1. Detector constructors accepted wrong *types* (not just bad values) and
   failed late/confusingly (e.g. a raw TypeError from a comparison) instead
   of a clear error at construction.
2. LoopDetector's signature hashing could raise on pathological `args`
   (e.g. a circular reference) instead of degrading gracefully.
3. ArgSchemaDetector's `schemas` structure wasn't validated. A non-dict
   schemas value, or a non-dict per-tool schema, raised a confusing
   AttributeError instead of a clear TypeError at construction.
4. diagnose() is O(n) per call, so this includes a perf regression guard
   to make sure that doesn't silently get worse.
"""

import time

import pytest

from snagtrace import CostBudget, Doctor, LoopDetector, Span
from snagtrace.detectors.schema import ArgSchemaDetector


# --- Constructor type validation -------------------------------------------


@pytest.mark.parametrize("bad_window", ["6", 6.0, None])
def test_loop_detector_rejects_non_int_window(bad_window):
    with pytest.raises(TypeError, match="window"):
        LoopDetector(window=bad_window, min_repeats=2)


@pytest.mark.parametrize("bad_min_repeats", ["3", 3.0, None])
def test_loop_detector_rejects_non_int_min_repeats(bad_min_repeats):
    with pytest.raises(TypeError, match="min_repeats"):
        LoopDetector(window=6, min_repeats=bad_min_repeats)


@pytest.mark.parametrize("bad_max_usd", ["5.00", None, [5.0]])
def test_cost_budget_rejects_non_numeric_max_usd(bad_max_usd):
    with pytest.raises(TypeError, match="max_usd"):
        CostBudget(max_usd=bad_max_usd)


def test_cost_budget_rejects_bool_max_usd():
    # bool is an int subclass, so True/False sneaking in as 1/0 would be a
    # silent footgun, not a sensible cost budget.
    with pytest.raises(TypeError):
        CostBudget(max_usd=True)


def test_arg_schema_detector_rejects_non_dict_schemas():
    with pytest.raises(TypeError, match="schemas"):
        ArgSchemaDetector(schemas=["not", "a", "dict"])


def test_arg_schema_detector_rejects_non_dict_per_tool_schema():
    with pytest.raises(TypeError, match="charge_card"):
        ArgSchemaDetector(schemas={"charge_card": "not-a-dict"})


# --- LoopDetector signature hashing robustness -----------------------------


def test_loop_detector_handles_circular_reference_in_args_gracefully():
    circular: dict = {"q": "x"}
    circular["self"] = circular  # a real circular reference

    spans = [Span(step_id=i, tool="search", args=circular) for i in (1, 2, 3)]
    faults = LoopDetector(window=6, min_repeats=3).check(spans)  # must not raise

    assert len(faults) == 1
    assert faults[0].category == "LOOP_FAILURE"


def test_loop_detector_still_distinguishes_different_normal_args():
    spans = [Span(step_id=i, tool="search", args={"q": f"q{i}"}) for i in (1, 2, 3)]
    faults = LoopDetector(window=6, min_repeats=3).check(spans)
    assert faults == []


# --- Performance regression guard ------------------------------------------


def test_diagnose_over_10k_spans_completes_quickly():
    detectors = [LoopDetector(window=6, min_repeats=3), ArgSchemaDetector(), CostBudget(max_usd=1e9)]
    spans = [
        Span(step_id=i, tool="search", args={"q": f"q-{i % 50}"}, cost_usd=0.0001)
        for i in range(1, 10_001)
    ]
    doctor = Doctor(detectors=detectors)

    start = time.perf_counter()
    doctor.diagnose(spans)
    elapsed = time.perf_counter() - start

    # generous bound (measured ~40ms in development). This guards against a
    # future change accidentally making a detector quadratic in trace length,
    # it is not meant to be a tight perf assertion
    assert elapsed < 2.0, f"diagnose() over 10k spans took {elapsed:.2f}s, expected well under 2s"
