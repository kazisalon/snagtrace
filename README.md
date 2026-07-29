# snagtrace

Deterministic fault detection for AI agent execution traces. It catches
failures that don't need an LLM to detect: loops, malformed or truncated
tool arguments, and runaway cost. Each fault is localized to the exact
step, with a confidence score attached.

## Why deterministic first

Most agent observability tools (LangSmith, Langfuse, Arize Phoenix,
Braintrust, Weave) give you tracing and replay, but you still have to
already suspect a run failed and manually walk the trace to find the step
that caused it. Some tools market "automatic root cause analysis," but
none of them publish real accuracy numbers for it, and the closest
published research on this exact problem shows current methods get it
right well under half the time.

snagtrace doesn't try to solve that problem with another LLM judge. It
starts from the failure classes that are actually cheap and reliable to
detect without one: repeated actions, broken tool arguments, and cost that
crosses a budget. These also happen to be some of the most commonly
reported bugs in LangGraph, CrewAI, and similar agent frameworks.

## Install

```bash
pip install snagtrace
# or, for the LangChain/LangGraph callback adapter:
pip install snagtrace[langchain]
```

## Quick start

```python
from snagtrace import Doctor, Span, LoopDetector, ArgSchemaDetector, CostBudget

doctor = Doctor(detectors=[
    LoopDetector(window=6, min_repeats=3),
    ArgSchemaDetector(),
    CostBudget(max_usd=5.00),
])

# feed spans as your agent runs, or all at once from a saved trace
doctor.feed(Span(step_id=1, agent_id="researcher", tool="search", args={"q": "..."}))
doctor.feed(Span(step_id=2, agent_id="researcher", tool="search", args={"q": "..."}))

result = doctor.diagnose()
if not result.is_healthy:
    print(result.first_fault)
    # Fault(step_id=2, category='LOOP_FAILURE', confidence=0.8, ...)
```

## Wiring into LangChain / LangGraph

```python
from snagtrace.adapters import SnagTraceCallbackHandler

handler = SnagTraceCallbackHandler(doctor, agent_id="my_agent")
agent_executor.invoke({"input": "..."}, config={"callbacks": [handler]})

result = handler.diagnose()
```

See [`examples/langchain_example.py`](examples/langchain_example.py).

## CLI

```bash
snagtrace report trace.jsonl --max-usd 5.00 --out report.html
```

`trace.jsonl` is one `Span` (see `snagtrace.core.Span`) per line, as JSON.
Exit codes: `0` healthy, `1` fault(s) found, `2` couldn't run (bad file or
bad JSON, printed as a clean `path:line` message, not a traceback).

## Performance

`Doctor.diagnose()` rescans the whole trace every time it's called. Each
detector runs a fresh pass over every span you've fed so far. That's a
deliberate choice: detectors are stateless, which is what keeps them
thread-safe and easy to test. The trade-off is that calling `diagnose()`
after every single `feed()` on a long-running agent gets expensive fast:

| Pattern | Measured cost |
|---|---|
| One `diagnose()` call over a 100,000-span trace | ~0.4s |
| One `diagnose()` call over a 10,000-span trace | ~40ms |
| `diagnose()` after every `feed()`, 500-span trace | ~0.6s total |
| `diagnose()` after every `feed()`, 5,000-span trace | ~85s total |

If your trace can run into the thousands of steps, don't diagnose on every
feed. Diagnose on an interval instead (every 20 to 50 steps, or at natural
checkpoints), or just run it once at the end.

## Production notes

- **Thread-safe.** `Doctor.feed` and the LangChain callback adapter both
  use locks, so they're safe to call from concurrent agent/tool threads.
- **One broken detector can't take down a diagnosis.** By default,
  `Doctor.diagnose` isolates a detector that raises. The error is recorded
  on `result.errors` and logged, and every other detector still runs. Pass
  `strict=True` in CI or tests if you want it to raise immediately instead.
- **Input is validated at the boundary.** `Span` and `Fault` reject bad
  values (negative cost, out-of-range confidence, wrong types) at
  construction time with a clear error, instead of failing silently or
  crashing deep inside a detector.
- **Forward-compatible parsing.** `Span.from_dict` ignores unknown fields
  with a warning instead of raising, so a trace from a newer adapter
  doesn't break an older snagtrace install.
- **Bounded memory in the adapter.** The LangChain callback handler caps
  in-flight tool calls at 10,000. Past that it evicts the oldest and logs a
  warning, since the scenario it exists to catch (a runaway agent)
  shouldn't also make the tool itself leak memory.
- **No secrets in reports.** The HTML report escapes all trace-derived
  content, since tool arguments and evidence strings are untrusted input
  once a trace could come from an agent run you don't fully control.

## Detectors (v0.1)

| Detector | Category | What it catches |
|---|---|---|
| `LoopDetector` | `LOOP_FAILURE` | Same (agent, tool, args) signature repeating within a sliding window, including two-agent delegation ping-pong |
| `ArgSchemaDetector` | `TOOL_ARGUMENT_ERROR` | Truncated tool-call arguments (hit `max_tokens`, failed to parse), validation-error tool responses, or schema violations against a registered tool signature |
| `CostBudget` | `COST_RUNAWAY` | The exact step where cumulative trace cost crosses a budget |

All three are plain structural checks over the span list. No LLM call, no
API key, fully reproducible, and every `Fault` carries the evidence that
produced it.

## What this isn't

This isn't a tool that explains every possible agent failure. Planning
mistakes, reasoning errors, and memory drift are real problems, but they
need something closer to an LLM judge to catch, and today's methods for
that aren't accurate enough to trust as ground truth. That kind of
detector might show up later as an explicitly opt-in, confidence-scored
addition, but it won't be the default.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
