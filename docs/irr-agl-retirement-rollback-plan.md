# IRR-AGL Retirement Rollback Plan

Date: 2026-07-08

## Rollback Scope

This closure is intentionally document-heavy and runtime-light. Rollback should
not require touching `AgentLoop`, `SessionService`, `ToolRegistry`, or live
broker safety files.

## Files Added For Retirement Archive

```text
docs/irr-agl-retirement-postmortem.md
docs/irr-agl-retirement-threat-model.md
docs/irr-agl-retirement-security-closure.md
docs/irr-agl-retirement-residual-risks.md
docs/irr-agl-retirement-rollback-plan.md
```

## Supporting Files From Prior SRE Closure

```text
docs/sre-recovery/00-registry-fact-interface-map.md
docs/sre-recovery/01-alpha-foundry-opt-in-boundary.md
docs/sre-recovery/protected-core-files.md
agent/tests/smoke/test_session_runtime_critical_path.py
agent/tests/security/test_mandate_gate_architecture.py
```

## Rollback Command

If this retirement archive commit must be reverted as a unit:

```text
git revert <retirement-closure-commit>
```

If reverting manually, remove only the retirement archive docs and the narrow
`.gitignore` allowlist line:

```text
!docs/irr-agl-retirement-*.md
```

Do not use `git reset --hard` unless explicitly approved by the operator.

## Verification After Rollback

Run:

```text
pytest agent/tests/smoke/test_session_runtime_critical_path.py agent/tests/security/test_mandate_gate_architecture.py -q
pytest agent/tests/contracts/test_alpha_foundry_openapi_snapshot.py agent/tests/security/test_alpha_foundry_api_security.py -q
pytest agent/tests/test_security_auth_api.py -q
```

Expected behavior:

- default session runtime still uses plain `ToolRegistry`;
- Alpha Foundry API remains absent by default;
- Host/CORS/auth tests still pass;
- no IRR-AGL governance object appears in default runtime paths.

## Archive Tag Guidance

Do not create a public release tag for this branch. If an operator needs a tag,
use an internal archive tag only and include this warning:

```text
internal archive tag only; not recommended for upstream release
```

## Upstream Policy

This branch is not an upstream merge plan. If maintainers want any surviving
piece, split it into small independent PRs:

```text
PR 0: postmortem and threat model only
PR 1: off-mode identity and session smoke
PR 2: registry conformance and escape-hatch tests
PR 3: Host/Origin/CORS/auth and shell boundary
PR 4: identifier containment
PR 5: live mandate and MCP exposure invariants
PR 6: evidence, scorecard, and secret consistency
PR 7: quant integrity closure
PR 8: final archive docs
```

Do not submit a giant "fix all vulnerabilities" PR.
