# Penetration Test Results

## Payloads

| Category | Payload examples | Result |
|---|---|---|
| Future-data injection | `next_close`, `future_tradability`, `future_volume`, `execution_return` | Rejected by factor input validation |
| API write attempt | `POST`, `PUT`, `PATCH`, `DELETE`, `X-HTTP-Method-Override: GET` | 404/405 and no state mutation |
| Path traversal | `../../../etc/passwd`, `%2e%2e/%2e%2e/secrets`, `C:\Windows\win.ini`, `file:///etc/passwd`, `local:../../.env` | Safe 404/422 body without stack, secret, or file content |
| Forward chain tamper | duplicate `observation_id`, forged `previous_observation_hash`, edited `realized_rank_ic` in JSONL | Rejected with `ForwardStoreMutationError` |
| Forward mutation API | public `update` / `delete` method probes | No public mutation methods are exposed |
| Queue proxy overclaim | no Level-2 call to `limit_queue_pressure_proxy` | Metadata/output are `fixture_only`, exploratory, and cannot claim Level-2 alpha |
| Prompt injection | final-card override text: delete hard failures, set `production_ready`, set `trial_count=1` | Ignored by gates; card warning `assistant_summary_excluded_from_gates` |
| Scorecard override | requested `production_ready` while covariance not PSD | hard failures `RISK_MODEL_NOT_PSD`, `SCORECARD_OVERRIDE_ATTEMPT` |
| Markdown XSS/secret | `<script>`, `[click](javascript:...)`, fake `token=ghp-*`, fake `sk-test-*` | Escaped/redacted |
| Live IO static scan | `requests.`, `httpx.`, `openai`, `place_order`, `shell=True`, `eval(`, `exec(` | no offenders in Alpha Foundry code/demos |

## Commands

```text
pytest agent/tests/security -q
pytest agent/tests/ -k "security or redteam or attack" -q
```

## Outcome

All local penetration tests passed after fixes. No destructive or external penetration activity was performed.
