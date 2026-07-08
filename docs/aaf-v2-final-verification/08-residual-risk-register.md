# Residual Risk Register

| ID | Risk | Severity | Status | Mitigation |
|---|---|---:|---|---|
| RR-001 | Alpha Foundry API surface is fixture-backed/deterministic rather than querying a persistent artifact store | Medium | Accepted for v2.1 | Marked read-only contract/UI gate; future phase should wire artifact-store-backed lookup |
| RR-002 | Financial quality factor track is adapter/PIT gate only without real vendor `available_at` provenance | Medium | Accepted | Inventory and tests cap claims; no strong alpha claim allowed without availability proof |
| RR-003 | Multiple-testing PBO/DSR support is MVP/deterministic, not a production statistical research platform | Medium | Accepted | TrialLedger and family statistics are real; do not claim full production inference |
| RR-004 | Portfolio optimizer is constrained MVP, not production optimizer | Medium | Accepted | Risk model PSD/benchmark/cap/T+1 gates tested; docs avoid production claim |
| RR-005 | Performance smoke is local CI style, not nightly real-store benchmark | Low | Accepted | Performance tests pass locally; future nightly can add real-store thresholds |
| RR-006 | No real external network, broker, live order, or LLM penetration test was performed | Medium | Accepted by scope | Static no-live-IO scan and local route tests only; external testing requires separate authorization |
| RR-007 | Existing repository warnings include FastAPI deprecations, pandas FutureWarnings, and frontend chunk-size warning | Low | Accepted | Non-blocking; captured in final test output |

## Release Blocking Risks

None remain after the audit fixes and final test run.
