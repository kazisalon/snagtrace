from __future__ import annotations

from typing import Optional

from ..core import Detector, Fault, Span

_ARG_ERROR_KEYWORDS = (
    "jsondecodeerror",
    "validation",
    "truncat",
    "unexpected keyword",
    "missing required",
    "invalid literal",
    "expecting value",
)


class ArgSchemaDetector(Detector):
    """Flags tool calls with malformed, truncated, or schema-invalid arguments.

    Two independent checks, both deterministic:
      1. Truncation: token usage hit max_tokens and args failed to parse,
         the classic "truncated mid-JSON, agent retries blindly" failure.
      2. Schema violation: a registered tool's required arguments are
         missing or the wrong type.
    """

    name = "arg_schema"

    def __init__(
        self,
        schemas: Optional[dict[str, dict[str, type]]] = None,
        strict: bool = True,
    ):
        schemas = schemas or {}
        if not isinstance(schemas, dict):
            raise TypeError(f"schemas must be a dict, got {type(schemas).__name__}")
        for tool_name, schema in schemas.items():
            if not isinstance(schema, dict):
                raise TypeError(
                    f"schemas[{tool_name!r}] must be a dict of {{arg_name: type}}, "
                    f"got {type(schema).__name__}"
                )
            for arg_name, expected in schema.items():
                types = expected if isinstance(expected, tuple) else (expected,)
                if not all(isinstance(t, type) for t in types):
                    raise TypeError(
                        f"schemas[{tool_name!r}][{arg_name!r}] must be a type or "
                        f"tuple of types, got {expected!r}"
                    )
        self.schemas = schemas
        self.strict = strict

    def check(self, spans: list[Span]) -> list[Fault]:
        faults: list[Fault] = []
        for span in spans:
            if span.kind != "tool_call":
                continue

            truncated = (
                span.tokens is not None
                and span.max_tokens is not None
                and span.tokens >= span.max_tokens
                and span.args is None
            )
            if truncated:
                faults.append(
                    Fault(
                        step_id=span.step_id,
                        category="TOOL_ARGUMENT_ERROR",
                        confidence=0.95,
                        evidence=(
                            f"tool={span.tool!r} call hit max_tokens="
                            f"{span.max_tokens} and arguments failed to parse, "
                            "output was almost certainly truncated mid-JSON"
                        ),
                        detector=self.name,
                    )
                )
                continue

            if span.status == "error" and span.error:
                lowered = span.error.lower()
                if any(kw in lowered for kw in _ARG_ERROR_KEYWORDS):
                    faults.append(
                        Fault(
                            step_id=span.step_id,
                            category="TOOL_ARGUMENT_ERROR",
                            confidence=0.85,
                            evidence=f"tool={span.tool!r} raised: {span.error}",
                            detector=self.name,
                        )
                    )
                    continue

            schema = self.schemas.get(span.tool) if span.tool else None
            if schema and self.strict:
                args = span.args or {}
                missing = [k for k in schema if k not in args]
                wrong_type = [
                    k
                    for k, expected in schema.items()
                    if k in args and not isinstance(args[k], expected)
                ]
                if missing or wrong_type:
                    parts = []
                    if missing:
                        parts.append(f"missing={missing}")
                    if wrong_type:
                        parts.append(f"wrong_type={wrong_type}")
                    faults.append(
                        Fault(
                            step_id=span.step_id,
                            category="TOOL_ARGUMENT_ERROR",
                            confidence=0.9,
                            evidence=f"tool={span.tool!r} schema violation: {', '.join(parts)}",
                            detector=self.name,
                        )
                    )

        return faults
