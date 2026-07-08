# Security Red-Team Report

## Scope

Local-only red-team audit of Alpha Foundry v2.1. No external network, no broker, no real LLM, no live orders, and no destructive host probing.

## Attack Surfaces Tested

| Surface | Attack | Expected defense | Test |
|---|---|---|---|
| Factor input | `next_close`, `execution_return`, `future_*` injected into factor compute | Reject before formula execution | `agent/tests/alpha_foundry/redteam/test_future_data_leakage.py` |
| Factor output | polluted FactorOutputFrame with labels/returns or missing v2.1 fields | Strict contract failure | `agent/tests/alpha_foundry/panels/test_panel_contracts.py` |
| Forward store | duplicate observation ID | Reject append | `agent/tests/security/test_alpha_foundry_forward_store_security.py` |
| Forward store | forged previous hash | Reject append | same |
| Forward store | modified JSONL line after write | Reject read with hash mismatch | same |
| Forward store path | traversal or symlink parent | Reject store path | same |
| API | POST/PUT/PATCH/DELETE on read-only Alpha Foundry paths | 404/405 and no state change | `agent/tests/security/test_alpha_foundry_api_security.py` |
| API path | encoded traversal and local/file URI strings | safe not-found/validation, no stack/secret/file content | same |
| Prompt injection | assistant summary says to upgrade to production-ready and change trial count | Research Card keeps scorecard conclusion and TrialLedger-derived count | `agent/tests/security/test_alpha_foundry_prompt_injection.py` |
| Scorecard override | requested production-ready with non-PSD risk model | invalid with exact hard failures | `agent/tests/security/test_alpha_foundry_scorecard_integrity.py` |
| Markdown | script tag, `javascript:`, inline fake token/API key | escaped and redacted | `agent/tests/security/test_alpha_foundry_secret_redaction.py` |
| Live IO | static scan for network/LLM/broker/shell snippets in Alpha Foundry code/demos | no offenders | `agent/tests/security/test_alpha_foundry_no_live_io.py` |

## Results

- `pytest agent/tests/security -q`: `10 passed`
- `pytest agent/tests/ -k "security or redteam or attack" -q`: `154 passed`
- No live broker, no shell execution, no external network, no LLM calls were used for these tests.

## Security Conclusion

The red-team audit found real weaknesses before fixes. After fixes, tested Alpha Foundry attack surfaces fail closed or reject unsafe input. Remaining risks are documented as non-blocking because they are scope/maturity limits rather than passing-test contradictions.
