# Release Decision

## Decision

`PASS WITH NON-BLOCKING RISKS`

## Basis

- The Phase 0-12 commit chain exists and was audited against the local `AGENTS.MD` and `execplan.md`.
- Commit names were not treated as proof; final acceptance used code review, red-team tests, demo dry-runs, frontend contract checks, and full backend regression.
- Four substantive implementation gaps were found and fixed during audit:
  - FactorOutputFrame v2.1 column mismatch.
  - future-data input leakage.
  - forward JSONL tamper/path weaknesses.
  - markdown XSS/secret leakage.
- Security test coverage was added where the security directory previously had no active Alpha Foundry source tests.
- Final commands pass:
  - Alpha Foundry: `99 passed`
  - Security: `10 passed`
  - Red-team selector: `154 passed`
  - Old behavior regression: `4772 passed, 6 skipped`
  - Frontend vitest/build: passed
  - Five demos: `snapshot_match`

## Conditions

- Do not push `AGENTS.MD` or `execplan.md`; they are local operator instructions and remain untracked/ignored.
- Do not market the MVP portfolio optimizer, PBO/DSR helpers, or fixture-backed API surface as production infrastructure.
- Future work should wire Alpha Foundry read APIs to persistent artifacts and add real-store/nightly performance runs.

## Maintainer Summary

The repository is acceptable for the A-Share Alpha Foundry v2.1 hardened milestone after the audit fixes in this branch. Residual risks are documented and non-blocking for this release scope.
