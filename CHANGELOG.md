# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project uses [SemVer](https://semver.org/).

## [0.1.0] - Unreleased

### Added
- `Doctor`, `Span`, `Fault`, `DiagnosisResult` core data model.
- `LoopDetector`: flags a repeated (agent, tool, args) signature within a sliding window.
- `ArgSchemaDetector`: flags truncated/malformed tool arguments and schema violations.
- `CostBudget`: flags the exact step where cumulative trace cost crosses a budget.
- `SnagTraceCallbackHandler`: LangChain/LangGraph callback adapter.
- CLI: `snagtrace report trace.jsonl`.
- Thread-safe `Doctor.feed`/`diagnose`, with per-detector fault isolation (`strict=False` by default).
- Input validation on `Span`/`Fault` construction, plus forward-compatible `Span.from_dict`.
- HTML report output with escaped, XSS-safe rendering of trace-derived content.

### Known limitations
- `Doctor.diagnose()` is a full O(n) rescan per call. See the Performance
  section in the README before calling it after every `feed()` on a
  long-running trace.
- Detectors are deliberately deterministic only. There is no LLM-assisted
  failure explanation yet, and no promise it is coming.
