import threading
import warnings

import pytest

from snagtrace import Doctor, Fault, InvalidFaultError, InvalidSpanError, LoopDetector, Span
from snagtrace.core import Detector
from snagtrace.detectors.schema import ArgSchemaDetector


# --- Span / Fault validation ---------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"step_id": "not-an-int"},
        {"step_id": True},  # bool is technically an int subclass, must be rejected explicitly
        {"step_id": 1, "kind": "bogus"},
        {"step_id": 1, "status": "bogus"},
        {"step_id": 1, "cost_usd": -1.0},
        {"step_id": 1, "tokens": -1},
        {"step_id": 1, "args": "not-a-dict"},
    ],
)
def test_span_rejects_invalid_fields(kwargs):
    with pytest.raises(InvalidSpanError):
        Span(**kwargs)


def test_fault_rejects_out_of_range_confidence():
    with pytest.raises(InvalidFaultError):
        Fault(step_id=1, category="X", confidence=1.5, evidence="e", detector="d")
    with pytest.raises(InvalidFaultError):
        Fault(step_id=1, category="X", confidence=-0.1, evidence="e", detector="d")


def test_span_from_dict_ignores_unknown_fields_with_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        span = Span.from_dict({"step_id": 1, "tool": "x", "some_future_field": 123})
    assert span.step_id == 1
    assert any("some_future_field" in str(w.message) for w in caught)


def test_arg_schema_detector_rejects_bad_schema_spec():
    with pytest.raises(TypeError):
        ArgSchemaDetector(schemas={"charge_card": {"amount": "not-a-type"}})


# --- Doctor: detector isolation -------------------------------------------


class _ExplodingDetector(Detector):
    name = "exploding"

    def check(self, spans):
        raise RuntimeError("boom")


def test_diagnose_isolates_a_broken_detector_by_default():
    doc = Doctor(detectors=[LoopDetector(window=6, min_repeats=2), _ExplodingDetector()])
    spans = [Span(step_id=i, tool="x", args={"a": 1}) for i in (1, 2)]
    result = doc.diagnose(spans)  # strict=False by default

    assert result.has_detector_errors
    assert len(result.errors) == 1
    assert "exploding" in str(result.errors[0])
    # the healthy detector's result still made it through
    assert len(result.faults) == 1


def test_diagnose_strict_mode_raises_on_broken_detector():
    doc = Doctor(detectors=[_ExplodingDetector()])
    with pytest.raises(Exception):
        doc.diagnose([Span(step_id=1, tool="x")], strict=True)


# --- Doctor: thread safety -------------------------------------------------


def test_concurrent_feed_does_not_lose_or_corrupt_spans():
    doc = Doctor(detectors=[])
    n_threads, per_thread = 8, 200

    def worker(offset):
        for i in range(per_thread):
            doc.feed(Span(step_id=offset * per_thread + i, tool="x", args={"a": 1}))

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(doc.spans) == n_threads * per_thread
    assert len({s.step_id for s in doc.spans}) == n_threads * per_thread  # no duplicates/corruption


def test_feed_rejects_non_span_objects():
    doc = Doctor(detectors=[])
    with pytest.raises(InvalidSpanError):
        doc.feed({"step_id": 1})
