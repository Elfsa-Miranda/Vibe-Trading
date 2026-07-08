# Phase Traceability Matrix

Judgment is based on code path review plus acceptance commands. Commit names alone were not treated as proof.

| Phase | Commit | Main implementation evidence | Acceptance evidence | Audit judgment |
|---|---:|---|---|---|
| P0 Focus/data audit | `69c1f6f` | `agent/scripts/dump_alpha_foundry_inventory.py`, `agent/tests/alpha_foundry/test_alpha_foundry_inventory_smoke.py` | `python agent/scripts/dump_alpha_foundry_inventory.py` passed; `pytest agent/tests/alpha_foundry -q` includes smoke | Pass |
| P1 Hypothesis registry + TrialLedger stub | `073317a` | `agent/src/alpha_foundry/hypothesis/*`, `agent/src/alpha_foundry/overfit/trial_ledger.py` | Full alpha suite and prior targeted `hypothesis`/`overfit` runs passed | Pass |
| P2 Factor contracts + panels | `b9d5a8f` | `agent/src/alpha_foundry/panels/*`, `agent/src/alpha_foundry/factors/base.py` | Initially partial: old FactorOutputFrame had 6 columns. Fixed to v2.1 9-column contract; `pytest agent/tests/alpha_foundry/panels -q` and full alpha passed | Pass after audit fix |
| P3 Limit liquidity factors | `50e950b` | `agent/src/alpha_foundry/factors/limit_liquidity.py`, `limit_liquidity_specs.yaml` | Factor tests, red-team future-data tests, full alpha passed | Pass after audit fix |
| P4 Price-volume factors | `1bbb503` | `agent/src/alpha_foundry/factors/price_volume.py`, `price_volume_specs.yaml` | Factor tests, red-team future-data tests, full alpha passed | Pass after audit fix |
| P5 Financial quality PIT gate | `45d9785` | `agent/src/alpha_foundry/factors/financial_quality.py`, `financial_quality_specs.yaml` | Full alpha passed; inventory reports adapter-only gate and no alpha claim without available_at proof | Pass with designed limitation |
| P6 Falsification diagnostics | `ac38573` | `agent/src/alpha_foundry/diagnostics/*`, TrialLedger append in falsification | `pytest agent/tests/alpha_foundry/diagnostics -q`; performance smoke passed | Pass |
| P7 Multiple testing disclosure | `8fe9b70` | `agent/src/alpha_foundry/overfit/multiple_testing.py`, `trial_matrix.py`, `pbo.py` | `pytest agent/tests/alpha_foundry/overfit -q`; full alpha passed | Pass with MVP statistical-method limitation |
| P8 Portfolio optimizer MVP | `15154f2` | `agent/src/alpha_foundry/portfolio/*` | `pytest agent/tests/alpha_foundry/portfolio -q`; portfolio performance smoke passed | Pass as MVP, not production optimizer |
| P9 Forward tracking | `2f51b0a` | `agent/src/alpha_foundry/forward/*` | Initially partial: append-only store lacked tamper/duplicate/chain/path guards. Fixed; forward and security tests passed | Pass after audit fix |
| P10 Scorecard/card integration | `2b15a48` | `agent/src/reliability/quant/*`, `agent/src/research_card/*`, `agent/src/alpha_foundry/reports/*` | Reliability/quant/research_card tests passed; prompt/scorecard tamper tests passed | Pass after redaction fix |
| P11 API/UI surface gate | `b324860` | `agent/src/api/alpha_foundry_routes.py`, OpenAPI fixture, frontend AlphaFoundryPanel | `python agent/scripts/check_api_structure.py`, OpenAPI snapshot, vitest, build passed | Pass with fixture-backed API limitation |
| P12 Demos/final package | `8fc115c` | five `agent/examples/alpha_foundry_demos/*/runner.py` paths and snapshots | five dry-runs output `snapshot_match`; demo tests and full regression passed | Pass |

## Key Corrections Made During Audit

- P2: FactorOutputFrame is now exactly v2.1 contract columns: `date`, `symbol`, `factor_id`, `factor_value`, `as_of`, `signal_time`, `available_at`, `data_availability_policy`, `factor_definition_hash`.
- P3/P4: Factor input computation now rejects `next_close`, `execution_return`, and any `future_*` columns before formula execution.
- P9: Forward JSONL store now rejects duplicate IDs, forged previous hashes, tampered lines, symlink/path traversal, and chain mismatch.
- P10/P11/P12: Free-text report/card rendering now escapes HTML, blocks `javascript:`, and redacts inline token/key material.

## Final Phase-Level Conclusion

The listed commits were not accepted blindly. The final audited state is `Pass with non-blocking residual risks`: core acceptance, regression, security, frontend, and demo commands pass, while known limitations remain documented in `08-residual-risk-register.md`.
