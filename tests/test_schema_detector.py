from snagtrace import Span
from snagtrace.detectors.schema import ArgSchemaDetector


def test_flags_truncated_json_argument():
    span = Span(
        step_id=14,
        tool="write_file",
        args=None,
        tokens=16384,
        max_tokens=16384,
        status="ok",
    )
    faults = ArgSchemaDetector().check([span])
    assert len(faults) == 1
    assert faults[0].category == "TOOL_ARGUMENT_ERROR"
    assert faults[0].step_id == 14
    assert faults[0].confidence >= 0.9


def test_ignores_complete_call_near_token_limit():
    span = Span(
        step_id=1,
        tool="write_file",
        args={"path": "a.txt", "content": "ok"},
        tokens=16384,
        max_tokens=16384,
        status="ok",
    )
    faults = ArgSchemaDetector().check([span])
    assert faults == []


def test_flags_error_status_with_validation_keyword():
    span = Span(
        step_id=5,
        tool="lookup",
        args={"id": 1},
        status="error",
        error="ValidationError: missing required field 'name'",
    )
    faults = ArgSchemaDetector().check([span])
    assert len(faults) == 1
    assert faults[0].category == "TOOL_ARGUMENT_ERROR"


def test_flags_missing_required_schema_field():
    span = Span(step_id=2, tool="charge_card", args={"amount": 10})
    detector = ArgSchemaDetector(schemas={"charge_card": {"amount": (int, float), "currency": str}})
    faults = detector.check([span])
    assert len(faults) == 1
    assert "missing" in faults[0].evidence


def test_flags_wrong_type_schema_field():
    span = Span(step_id=3, tool="charge_card", args={"amount": "ten", "currency": "usd"})
    detector = ArgSchemaDetector(schemas={"charge_card": {"amount": (int, float), "currency": str}})
    faults = detector.check([span])
    assert len(faults) == 1
    assert "wrong_type" in faults[0].evidence
