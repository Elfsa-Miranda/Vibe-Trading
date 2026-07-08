# A-Share Alpha Foundry v2.1 Final Acceptance

Date: 2026-07-08

This package completes the A-Share Alpha Foundry under IRR-AGL v2.1 hardened phase set through deterministic demos, read-only surfaces, scorecard/research-card integration, and regression coverage.

## Scope Closed

- Mechanism hypothesis registry with deterministic formula specs and PIT availability metadata.
- PIT-safe `FactorOutputFrame` contract with the exact nine v2.1 allowed columns.
- A-share tradability masks for suspension, limit states, ST, new listing, T+1, and execution feasibility.
- Mechanism factor families for limit liquidity, price-volume behavior, and financial quality PIT gates.
- Factor falsification diagnostics with deterministic hard failure codes and TrialLedger participation.
- Multiple-testing disclosure driven by TrialLedger counts and family statistics.
- Orthogonal alpha combination and constrained portfolio MVP with PSD risk model and constraint checks.
- Forward paper tracking with frozen plan hashes and append-only observations.
- Scorecard, Research Card, MethodologyFactSet, read-only API, frontend fixture panels, and evidence closure integration.
- Five deterministic demo traps/candidates that call production builders and compare dry-run output against snapshots.

## Phase 12 Demo Acceptance

All demo runners were executed with `--dry-run`; each loaded fixtures, ran production computation/builders, compared against `expected_output.json`, and avoided persistent store writes.

```text
python agent/examples/alpha_foundry_demos/naive_limit_momentum_trap/runner.py --dry-run
snapshot_match naive_limit_momentum_trap

python agent/examples/alpha_foundry_demos/failed_limit_breakout_candidate/runner.py --dry-run
snapshot_match failed_limit_breakout_candidate

python agent/examples/alpha_foundry_demos/public_alpha_crowding_trap/runner.py --dry-run
snapshot_match public_alpha_crowding_trap

python agent/examples/alpha_foundry_demos/orthogonal_portfolio_increment/runner.py --dry-run
snapshot_match orthogonal_portfolio_increment

python agent/examples/alpha_foundry_demos/forward_decay_kill/runner.py --dry-run
snapshot_match forward_decay_kill
```

## Automated Test Results

```text
pytest agent/tests/alpha_foundry/demos -q
4 passed

pytest agent/tests/alpha_foundry/test_performance.py -k "falsification" -q
1 passed, 1 deselected

pytest agent/tests/alpha_foundry/test_performance.py -k "portfolio" -q
1 passed, 1 deselected

pytest agent/tests/alpha_foundry -q
93 passed

pytest agent/tests/ -q --ignore=agent/tests/alpha_foundry
4762 passed, 6 skipped, 135 warnings

cd frontend
npx vitest run --reporter=verbose
28 files passed, 240 tests passed

cd frontend
npm run build
passed
```

The warnings are pre-existing framework/dependency warnings and factor `pct_change` FutureWarnings; they did not indicate Phase 12 regressions.

## Safety And Evidence Checks

- No write API was added for Alpha Foundry; Phase 11 routes are read-only.
- No live trading capability was expanded.
- No LLM path can upgrade conclusion level, hard failures, or research-card gates.
- EOD-only limit queue proxy demos remain exploratory and carry proxy/crowding warnings.
- Best-trial-only reporting is rejected; TrialLedger count and selected trial metadata are disclosed.
- Forward observations are append-only; no public update/delete mutation API is exposed.
- `AGENTS.MD` and `execplan.md` are local operator instructions only. They are ignored and were not staged or committed.

## Local Instruction File Guard

```text
git check-ignore -v -- AGENTS.MD execplan.md
.gitignore:86:AGENTS.md        AGENTS.MD
.git/info/exclude:12:execplan.md        execplan.md
```

## Acceptance Statement

The current implementation satisfies the A-Share Alpha Foundry v2.1 hardened phase acceptance in a deterministic, testable, and rollback-friendly form. The portfolio layer remains an MVP constrained optimizer, and forward tracking remains paper-only; neither is represented as production trading infrastructure.
