# Fixes Applied

## FOG-001 FactorOutputFrame Contract

- Files changed:
  - `agent/src/alpha_foundry/panels/interfaces.py`
  - `agent/src/alpha_foundry/factors/limit_liquidity.py`
  - `agent/src/alpha_foundry/factors/price_volume.py`
  - diagnostics/performance/demo/test fixtures
- Change: enforced v2.1 9-column FactorOutputFrame, including signal time, availability policy, and definition hash.
- RED evidence: strict panel contract failed before implementation update.
- GREEN evidence: `pytest agent/tests/alpha_foundry/panels -q`; `pytest agent/tests/alpha_foundry -q`.

## FOG-002 Future-Data Leakage

- Files changed:
  - `agent/src/alpha_foundry/factors/limit_liquidity.py`
  - `agent/src/alpha_foundry/factors/price_volume.py`
  - `agent/tests/alpha_foundry/redteam/test_future_data_leakage.py`
- Change: factor input validation rejects forbidden output fields and any `future_*` column before computation.
- GREEN evidence: `pytest agent/tests/alpha_foundry/redteam/test_future_data_leakage.py -q`.

## FOG-003 Forward Store Tamper Resistance

- Files changed:
  - `agent/src/alpha_foundry/forward/store.py`
  - `agent/tests/security/test_alpha_foundry_forward_store_security.py`
- Change: duplicate observation IDs, forged previous hashes, tampered JSONL lines, chain mismatch, symlink parents, and traversal paths are rejected.
- GREEN evidence: `pytest agent/tests/security/test_alpha_foundry_forward_store_security.py -q`; `pytest agent/tests/alpha_foundry/forward -q`.

## FOG-004 Markdown Secret/XSS Redaction

- Files changed:
  - `agent/src/reliability/redaction.py`
  - `agent/src/alpha_foundry/reports/render_markdown.py`
  - `agent/src/research_card/render_markdown.py`
  - `agent/tests/security/test_alpha_foundry_secret_redaction.py`
- Change: free-text secret substrings are redacted; report/card markdown escapes HTML and blocks `javascript:`.
- GREEN evidence: `pytest agent/tests/security/test_alpha_foundry_secret_redaction.py -q`.

## FOG-005 Security Test Coverage

- New files:
  - `agent/tests/security/test_alpha_foundry_api_security.py`
  - `agent/tests/security/test_alpha_foundry_forward_store_security.py`
  - `agent/tests/security/test_alpha_foundry_no_live_io.py`
  - `agent/tests/security/test_alpha_foundry_prompt_injection.py`
  - `agent/tests/security/test_alpha_foundry_scorecard_integrity.py`
  - `agent/tests/security/test_alpha_foundry_secret_redaction.py`
  - `agent/tests/alpha_foundry/redteam/test_future_data_leakage.py`
- GREEN evidence: `pytest agent/tests/security -q`; `pytest agent/tests/ -k "security or redteam or attack" -q`.
