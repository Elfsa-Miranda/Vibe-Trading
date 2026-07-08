# Execplan Gap Analysis

## Gaps Found And Closed

| ID | Gap | Impact | Fix | Evidence |
|---|---|---|---|---|
| FOG-001 | FactorOutputFrame implementation and fixtures used a 6-column frame while `AGENTS.MD`/`execplan.md` require 9 v2.1 columns | Clean factor contract was weaker than the authoritative spec | Updated `FACTOR_OUTPUT_COLUMNS`, factor builders, demos, and tests to require `signal_time`, `data_availability_policy`, `factor_definition_hash` | `pytest agent/tests/alpha_foundry/panels -q`; full alpha passed |
| FOG-002 | Factor compute accepted future/label-like input columns such as `next_close` | Potential future-data leakage into factor formulas | `limit_liquidity` and `price_volume` input preparation now rejects forbidden output columns and `future_*` inputs | `pytest agent/tests/alpha_foundry/redteam/test_future_data_leakage.py -q` |
| FOG-003 | Forward JSONL append-only store did not reject duplicate observation IDs, forged chain heads, tampered lines, or traversal paths | Forward tracking could be rewritten or read from unsafe paths | Added path validation, duplicate detection, previous-hash verification, stored-line hash validation, and per-plan chain checks | `pytest agent/tests/security/test_alpha_foundry_forward_store_security.py -q` |
| FOG-004 | Markdown report/card rendering allowed free-text HTML, `javascript:`, and inline key/token material | XSS/secret leakage in evidence exports | Added free-text secret redaction and HTML escaping in report/card renderers | `pytest agent/tests/security/test_alpha_foundry_secret_redaction.py -q` |
| FOG-005 | `agent/tests/security` initially had no active source tests for Alpha Foundry red-team scope | Security acceptance had no executable evidence | Added security tests for API write/path traversal, forward store, prompt injection, scorecard override, no live IO, and markdown redaction | `pytest agent/tests/security -q`; red-team selector passed |

## Non-Blocking Gaps Or Scope Limits

- P5 financial quality remains an adapter/PIT gate until real vendor `available_at` provenance is wired; inventory correctly reports adapter-only status.
- P7 multiple-testing PBO/DSR support is deterministic MVP style; it discloses trials and prevents best-trial hiding, but does not claim a full production statistics platform.
- P8 portfolio optimizer is constrained MVP and explicitly not production optimizer.
- P11 API surface is deterministic fixture-backed read-only surface; it verifies contracts/UI compatibility, not persistent artifact-store querying.
- External network, broker, LLM, and live order paths were not exercised by design; no real attack, no real broker, and no real network calls were performed.

## False Comfort Avoided

The phase commit chain alone was insufficient. Acceptance was only granted after replaying tests, adding red-team tests, forcing failures for discovered gaps, applying fixes, and rerunning full regression.
