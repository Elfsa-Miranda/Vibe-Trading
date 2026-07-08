# A-Share Alpha Foundry v2.1 Rollback Plan

Rollback should be done by reverting the relevant phase commit on the integration branch. Do not remove local operator instruction files; `AGENTS.MD` and `execplan.md` are ignored local files and are not part of rollback.

## Phase 12 Rollback

Revert the Phase 12 commit or remove these paths:

```text
agent/examples/alpha_foundry_demos/
agent/tests/alpha_foundry/demos/
docs/aaf-v2-final-acceptance.md
docs/aaf-v2-known-limitations.md
docs/aaf-v2-rollback-plan.md
docs/aaf-v2-demo-index.md
```

Expected effect: removes deterministic demo package and final acceptance docs.
Core Alpha Foundry modules remain from earlier phases. API exposure is opt-in
and must remain absent by default.

## Upstream Slice Map

Do not land the full local integration as one upstream PR. Preserve reviewable
boundaries:

```text
PR 1: A-share alpha_foundry docs and inventory only.
PR 2: pure schema plus deterministic fixtures.
PR 3: tradability masks.
PR 4: one factor family with tests.
PR 5: diagnostics only.
```

Research Card, scorecard policy, reliability bridges, API/UI, performance,
demos, portfolio, forward tracking, and migration are deferred until the pure
Alpha Foundry package has been accepted.

## Earlier Local Phase Rollback Map

```text
Phase 11: remove opt-in Alpha Foundry read-only API router, frontend RunDetail panels, OpenAPI snapshots, and frontend fixtures.
Phase 10: remove local report builder and any deferred Research Card/MethodologyFactSet/scorecard bridges if they were explicitly enabled.
Phase 9: remove forward tracking plan, append-only observation store, and kill-rule evaluator.
Phase 8: remove constrained portfolio optimizer MVP, risk model snapshot, and execution/capacity simulation layer.
Phase 7: remove multiple-testing disclosure and TrialLedger family-statistics integration.
Phase 6: remove factor falsification reports and diagnostic gates.
Phase 5: remove financial quality PIT factor gate.
Phase 4: remove price-volume mechanism factor family.
Phase 3: remove limit-liquidity mechanism factor family.
Phase 2: remove FactorSpec, FactorFormulaSpec, FactorOutputFrame, NeutralizationConfig, and tradability mask contracts.
Phase 1: remove alpha hypothesis registry and TrialLedger stub.
Phase 0: remove baseline audit document only.
```

## Validation After Rollback

Run the narrow tests for the removed phase first, then run shared smoke tests:

```text
pytest agent/tests/alpha_foundry -q
pytest agent/tests/ -q --ignore=agent/tests/alpha_foundry
cd frontend
npx vitest run --reporter=verbose
npm run build
```

If rolling back Phase 11 or later, also verify no orphan API route remains, no
frontend import references deleted Alpha Foundry components, and the default
OpenAPI spec contains no `/research/alpha-foundry/` paths.

## Safety Checks

- Do not use `git reset --hard` unless explicitly requested.
- Do not stage or commit `AGENTS.MD` or `execplan.md`.
- Do not push rollback branches until the staged diff has been reviewed.
- Preserve existing legacy fixtures; migration tests must continue reading old artifacts.
- Keep `VIBE_TRADING_ALPHA_FOUNDRY_MODE` defaulting to `off`.
- Do not attach `observe`, `warn`, or `enforce` to legacy runtime paths unless a
  later reviewed PR adds an explicit opt-in adapter.
