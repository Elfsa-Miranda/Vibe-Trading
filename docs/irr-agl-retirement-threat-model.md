# IRR-AGL Retirement Threat Model

Date: 2026-07-08

Scope: retired IRR-AGL governance, Alpha Foundry opt-in surfaces, default
session/runtime safety, live mandate gates, API auth/origin boundaries, evidence
artifacts, and research-integrity outputs.

## Security Objective

The objective is not to prove IRR-AGL is safe to revive. The objective is to
prove the retired branch can be archived without accidentally changing default
runtime behavior or weakening known live/API/security boundaries.

## Trust Boundaries

| Boundary | Trusted Source | Untrusted Input |
|---|---|---|
| Tool registry | server-side `ToolRegistry` construction | user prompt, remote MCP names, governance mode text |
| Live mandate | authoritative mandate store and kill switch | caller-provided mandate or live state JSON |
| API auth | `API_AUTH_KEY`, server-side request validation | Host, Origin, peer-IP-only trust |
| File paths | server-defined roots and safe path helpers | path params, ids, filenames, cache keys |
| Shell tools | explicit operator env and auth | default API/session/MCP exposure |
| Evidence | typed reports and append-only/local artifacts | LLM-generated conclusions, free-text hard failures |
| Quant research | PIT data, deterministic specs, diagnostics joins | future labels inside factor compute, proxy overclaims |

## Primary Threats

| Threat | Impact | Closure Control |
|---|---|---|
| Registry replacement in default session path | session runtime crash or policy bypass | tests assert `SessionService` and `AgentLoop` do not import/call registry wrappers |
| `mode=off` changes object identity | disabled feature still changes behavior | future `govern_registry(..., mode="off")` must return original object by identity |
| Raw `.inner` or raw R4/R5 tool escape | policy deny can be bypassed | current live safety is tool-boundary based; residual risk documents no retired wrapper should expose raw internals |
| Proposal id path traversal | forged live mandate | path-param validation and existing mandate security tests; external `0.1.10` advisory noted |
| Persistent memory path traversal | write/read outside memory root | existing path utility tests cover path traversal classes; broader id containment remains residual |
| DNS rebinding / Host spoof | local API auth bypass | Host middleware, CORS wildcard rejection, auth tests |
| Shell endpoint exposure | RCE and secret exfiltration | shell tools disabled by default and require explicit opt-in |
| Secret leakage | tokens in traces/cards/API/UI | redaction tests and Alpha Foundry secret-surface tests |
| Evidence inconsistency | card/API/UI disagree on hard failures | exact-match Alpha Foundry tests; broader retired evidence verifier remains residual |
| Quant future leakage | false alpha claims | Alpha Foundry red-team and factor contract tests |

## Required Default Invariants

- Default session runtime uses plain `ToolRegistry`.
- Default Alpha Foundry mode is `off`.
- Alpha Foundry API is mounted only when both:
  - `VIBE_TRADING_ALPHA_FOUNDRY_MODE != off`
  - `VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API=1`
- No default Research Card, scorecard, API/UI, or reliability bridge attaches to
  legacy runs.
- R4/R5 denial must not execute an inner live/write tool.
- Shell tools are unavailable unless explicitly enabled.
- User-controlled ids must be constrained before path use.
- LLM output cannot raise conclusion level, hard failure state, or live
  authority.

## Out Of Scope For Retirement

- Designing a new governance architecture.
- Proving production-live readiness.
- Completing every proposed closure PR in one large changeset.
- Replacing upstream `v0.1.10+` security hardening with this branch.

## Residual Threat Classes

The following require future focused PRs if the retired branch is kept alive:

- full registry conformance for any reintroduced wrapper;
- unified identifier containment for every id class listed in the closure spec;
- CircuitBreaker/rate limiter atomicity under high concurrency;
- RuntimeContext authority hardening if caller-provided dict authority is
  accepted anywhere;
- evidence outbox/verifier reconstruction beyond Alpha Foundry fixtures;
- frontend-wide secret and hard-failure exact-match verification if UI surfaces
  are touched.
