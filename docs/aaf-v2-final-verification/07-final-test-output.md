# Final Test Output

## Environment

- Python: `Python 3.13.9`
- Dependency snapshot: `docs/aaf-v2-final-verification/pip-freeze.txt`
- Frontend package manager command used: `npm`

## Backend

```text
pytest agent/tests/alpha_foundry -q
101 passed in 11.43s

pytest agent/tests/security -q
13 passed, 5 warnings in 2.56s

pytest agent/tests/ -k "security or redteam or attack" -q
157 passed, 4725 deselected, 5 warnings in 17.78s

pytest agent/tests/reliability -q
25 passed in 2.31s

pytest agent/tests/research_card -q
3 passed in 0.51s

pytest agent/tests/quant -q
25 passed in 0.54s

pytest agent/tests/contracts/test_alpha_foundry_openapi_snapshot.py -q
3 passed, 5 warnings in 1.42s

pytest agent/tests/alpha_foundry/test_performance.py -q
2 passed in 2.25s

pytest agent/tests/ -q --ignore=agent/tests/alpha_foundry
4775 passed, 6 skipped, 135 warnings in 383.60s
```

## Scripts

```text
python agent/scripts/dump_alpha_foundry_inventory.py
passed; network_calls_performed=false

python agent/scripts/check_api_structure.py
incremental_compatible
```

## Demos

```text
snapshot_match naive_limit_momentum_trap
snapshot_match failed_limit_breakout_candidate
snapshot_match public_alpha_crowding_trap
snapshot_match orthogonal_portfolio_increment
snapshot_match forward_decay_kill

pytest agent/tests/alpha_foundry/demos -q
4 passed in 3.90s
```

## Frontend

```text
cd frontend; npx vitest run --reporter=verbose
28 files passed, 240 tests passed

cd frontend; npm run build
passed; Vite emitted existing large chunk-size warning
```

## Warnings

Observed warnings are non-blocking deprecations/FutureWarnings and existing frontend build chunk-size warning. No acceptance command failed in the final run.
