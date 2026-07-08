# IRR-AGL Retirement Residual Risks

Date: 2026-07-08

## Residual Risk Position

There is no absolute claim that every possible vulnerability is fixed. The
professional closure claim is narrower:

- known incident classes in scope have regression coverage or explicit
  documentation;
- high-risk default paths are fail-closed or opt-in;
- unknown or unproven classes are listed here instead of being hidden.

## Residual Risks

| Risk | Severity | Current Status | Required Future Closure |
|---|---:|---|---|
| Reintroduction of a `ToolRegistry` wrapper | High | No production wrapper found now | Any future wrapper requires conformance tests and `mode=off` identity |
| Public `.inner` escape hatch in a future wrapper | High | No active retired wrapper in hot path | If wrapper is revived, add `test_registry_escape_hatches.py` before use |
| Unified identifier containment across every id class | High | API path params and path utilities covered; not every listed id has a single shared helper | Add `agent/src/security/paths.py` or equivalent only in a focused PR |
| CircuitBreaker / rate limiter TOCTOU | Medium | Not proven by a dedicated closure test | Add concurrent atomicity tests before relying on those state machines |
| RuntimeContext caller-forged authority | High | Not proven as a global invariant in this closure | Add tests rejecting caller authority fields for live/budget/risk state |
| Evidence outbox and verifier reconstruction | Medium | Alpha Foundry exact-match covered; broad IRR evidence verifier not proven | Add degraded/partial/outbox tests if evidence stack is retained |
| Full frontend consistency | Medium | No frontend files touched in this closure | Run frontend vitest/build before any UI-facing archive release |
| Broad secret redaction across every listed surface | Medium | Existing redaction and Alpha Foundry secret tests exist; exhaustive all-surface scan not proven | Add `test_secret_redaction_all_surfaces.py` for retained surfaces |
| Scorecard policy no-code-execution | Medium | Current Alpha Foundry scorecard tests exist; no broad malicious policy loader test added | Add a dedicated eval/exec/dynamic-import negative test if policy config becomes user-editable |
| External advisory posture | High | Documented; not remediated by this branch alone | Operators must run `0.1.10+`, rotate secrets if exposed, and bind API safely |
| Full-suite performance threshold under load | Low | Full `pytest agent/tests -q` had one timing failure at `5.2557s < 5.0s` while the same performance test passed isolated | Treat strict wall-clock thresholds as noisy on shared Windows runners; adjust only in a focused performance-test PR |

## Operational Residuals

- Windows LF/CRLF warnings are present when Git touches some files. They are not
  security findings.
- `agent/api_server.py` has pre-existing lint noise for unused imports and
  re-exported symbols. This closure does not clean that file to avoid widening
  the diff.
- Existing IRR reliability modules remain in `agent/src/reliability/**` as local
  artifacts. They must not be interpreted as a revived governance architecture.
- The Alpha Foundry research package exists locally, but its API and sensitive
  integrations are opt-in and should not be proposed upstream as one full-stack
  landing.

## Operator Guidance

For any deployment that may have run a version before `0.1.10`:

- upgrade to `0.1.10+`;
- rotate API, LLM, broker, and data-source secrets if exposure is plausible;
- bind local APIs to `127.0.0.1` unless remote deployment is explicitly secured;
- configure explicit CORS origins;
- keep shell tools disabled unless there is a documented operator need;
- monitor suspicious Host/Origin headers and unexpected subprocess execution.

## Archive Warning

This branch should be archived as a historical safety asset. The next active
work should start from current main without reviving IRR-AGL or wrapping
`ToolRegistry`.
