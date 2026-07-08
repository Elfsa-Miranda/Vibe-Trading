# Functional Acceptance Report

## Final Commands

| Area | Command | Result |
|---|---|---:|
| Alpha Foundry full suite | `pytest agent/tests/alpha_foundry -q` | `101 passed in 11.43s` |
| Security tests | `pytest agent/tests/security -q` | `13 passed, 5 warnings in 2.56s` |
| Red-team selector | `pytest agent/tests/ -k "security or redteam or attack" -q` | `157 passed, 4725 deselected, 5 warnings in 17.78s` |
| Reliability | `pytest agent/tests/reliability -q` | `25 passed in 2.31s` |
| Research Card | `pytest agent/tests/research_card -q` | `3 passed in 0.51s` |
| Quant policy | `pytest agent/tests/quant -q` | `25 passed in 0.54s` |
| Old behavior regression | `pytest agent/tests/ -q --ignore=agent/tests/alpha_foundry` | `4775 passed, 6 skipped, 135 warnings in 383.60s` |
| Performance smoke | `pytest agent/tests/alpha_foundry/test_performance.py -q` | `2 passed in 2.25s` |
| OpenAPI contract | `pytest agent/tests/contracts/test_alpha_foundry_openapi_snapshot.py -q` | `3 passed, 5 warnings in 1.42s` |
| API structure | `python agent/scripts/check_api_structure.py` | `incremental_compatible` |
| Inventory | `python agent/scripts/dump_alpha_foundry_inventory.py` | passed; `network_calls_performed=false` |
| Frontend tests | `cd frontend; npx vitest run --reporter=verbose` | `28 files passed, 240 tests passed` |
| Frontend build | `cd frontend; npm run build` | passed with existing chunk-size warning |

## Demo Acceptance

Commands:

```text
python agent/examples/alpha_foundry_demos/naive_limit_momentum_trap/runner.py --dry-run
python agent/examples/alpha_foundry_demos/failed_limit_breakout_candidate/runner.py --dry-run
python agent/examples/alpha_foundry_demos/public_alpha_crowding_trap/runner.py --dry-run
python agent/examples/alpha_foundry_demos/orthogonal_portfolio_increment/runner.py --dry-run
python agent/examples/alpha_foundry_demos/forward_decay_kill/runner.py --dry-run
pytest agent/tests/alpha_foundry/demos -q
```

Result:

```text
snapshot_match naive_limit_momentum_trap
snapshot_match failed_limit_breakout_candidate
snapshot_match public_alpha_crowding_trap
snapshot_match orthogonal_portfolio_increment
snapshot_match forward_decay_kill
4 passed in 3.90s
```

## Acceptance Decision

Functional acceptance is met after audit fixes. The accepted scope is the v2.1 hardened Alpha Foundry chain, not a production live optimizer or external broker/market-data service.
