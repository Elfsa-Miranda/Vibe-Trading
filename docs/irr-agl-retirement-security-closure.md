# IRR-AGL Retirement Security Closure

Date: 2026-07-08

Branch: `closure/irr-agl-retirement-hardening`

## Closure Statement

This branch is archived after retirement hardening. It is not recommended for
upstream revival. Known P0/P1 incident classes that are covered in this branch
have regression evidence. Residual risks are documented separately in
`docs/irr-agl-retirement-residual-risks.md`.

## Local Changes In Scope

- Archive docs:
  - `docs/irr-agl-retirement-postmortem.md`
  - `docs/irr-agl-retirement-threat-model.md`
  - `docs/irr-agl-retirement-security-closure.md`
  - `docs/irr-agl-retirement-residual-risks.md`
  - `docs/irr-agl-retirement-rollback-plan.md`
- Existing SRE recovery docs remain supporting evidence:
  - `docs/sre-recovery/00-registry-fact-interface-map.md`
  - `docs/sre-recovery/01-alpha-foundry-opt-in-boundary.md`
  - `docs/sre-recovery/protected-core-files.md`
- `.gitignore` now allows `docs/irr-agl-retirement-*.md` to be tracked while
  preserving the broad internal-doc ignore policy.

## Evidence Map

| Area | Evidence |
|---|---|
| Hot path registry safety | `agent/tests/smoke/test_session_runtime_critical_path.py` |
| Live mandate architecture boundary | `agent/tests/security/test_mandate_gate_architecture.py` |
| Host/CORS/auth/path param hardening | `agent/tests/test_security_auth_api.py` |
| Path traversal utilities | `agent/tests/test_path_safety.py`, `agent/tests/test_file_tool_sandbox_security.py` |
| Shell tool default-off | `agent/tests/test_tool_registry_security.py`, `agent/tests/test_runner_env.py` |
| Live mandate enforcement | `agent/tests/test_mandate_enforcement.py`, `agent/tests/test_killswitch_blocks_orders.py`, `agent/tests/test_sdk_order_gate.py` |
| MCP/swarm allowlist and injection controls | `agent/tests/test_swarm_m5_trust_model.py`, `agent/tests/test_swarm_runs_root_and_shell_tools.py`, MCP tests |
| Alpha Foundry default-off API | `agent/tests/contracts/test_alpha_foundry_openapi_snapshot.py` |
| Alpha Foundry API write/path/secret safety | `agent/tests/security/test_alpha_foundry_api_security.py` |
| Alpha Foundry research integrity | `agent/tests/alpha_foundry/**`, `agent/tests/security/test_alpha_foundry_*` |

## Commands Run

The following commands were run during the closure sweep:

```text
pytest agent/tests/contracts/test_alpha_foundry_openapi_snapshot.py agent/tests/security/test_alpha_foundry_api_security.py agent/tests/smoke/test_session_runtime_critical_path.py agent/tests/security/test_mandate_gate_architecture.py -q
```

Observed result:

```text
22 passed, 53 warnings
```

```text
pytest agent/tests/alpha_foundry -q
```

Observed result:

```text
101 passed
```

```text
pytest agent/tests/test_security_auth_api.py agent/tests/test_path_safety.py agent/tests/test_tool_registry_security.py agent/tests/test_runner_env.py -q
```

Observed result:

```text
79 passed, 5 warnings
```

```text
pytest agent/tests -q
```

Observed result:

```text
1 failed, 4892 passed, 6 skipped, 183 warnings
```

The single failure was
`agent/tests/alpha_foundry/test_performance.py::test_falsification_performance_smoke`.
The measured elapsed time was `5.255695500000002` seconds against a `5.0`
second threshold during the full suite. The same test passed when isolated:

```text
pytest agent/tests/alpha_foundry/test_performance.py::test_falsification_performance_smoke -q
```

Observed result:

```text
1 passed in 2.65s
```

The full performance file also passed when isolated:

```text
pytest agent/tests/alpha_foundry/test_performance.py -q
```

Observed result:

```text
2 passed in 2.61s
```

This is recorded as a residual performance-threshold risk, not hidden as a
green full-suite result.

```text
python -m ruff check agent/src/api/alpha_foundry_routes.py agent/tests/contracts/test_alpha_foundry_openapi_snapshot.py agent/tests/security/test_alpha_foundry_api_security.py
```

Observed result:

```text
All checks passed
```

`python -m ruff check agent/api_server.py ...` was also attempted and reported
pre-existing unused imports/re-export warnings in `agent/api_server.py`. Those
were not changed because this closure must not broaden into unrelated cleanup.

## Closure DoD Snapshot

| Item | Status | Evidence |
|---|---|---|
| `mode=off` is identity for future registry governance | Covered by regression guard | `test_session_runtime_critical_path.py` |
| Default session path does not instantiate registry governance | Covered | `test_session_runtime_critical_path.py` |
| Agent prompt can build with bare registry | Covered | `test_session_runtime_critical_path.py` |
| No protected core file change required | Covered by branch diff and protected-core doc | `docs/sre-recovery/protected-core-files.md` |
| Alpha Foundry API absent by default | Covered | `test_alpha_foundry_openapi_snapshot.py` |
| Alpha Foundry API opt-in is read-only | Covered | `test_alpha_foundry_api_security.py` |
| Host/CORS/auth hardening exists | Covered in existing suite | `test_security_auth_api.py` |
| Path traversal classes covered | Covered in existing suite | `test_path_safety.py`, API path-param tests |
| No live trading expansion | Covered by scope and tests | live/mandate tests |
| Quant future leakage checks exist | Covered | `agent/tests/alpha_foundry/redteam/test_future_data_leakage.py` |

## Explicit Non-Claims

- This closure does not claim all possible vulnerabilities are fixed.
- This closure does not claim IRR-AGL is suitable for upstream revival.
- This closure does not claim production live trading readiness.
- This closure does not replace upgrading vulnerable deployments to `0.1.10+`
  and rotating potentially exposed secrets.
- This closure does not finish every proposed future closure PR; it archives the
  current safety state and residual gaps honestly.
