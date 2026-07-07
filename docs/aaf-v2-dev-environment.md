# AAF v2.1 Development Environment

## Baseline

```text
Python >= 3.11
pandas >= 2.0
numpy >= 1.24
scipy >= 1.11
pydantic >= 2.0
pytest
No real broker / no real LLM / no real external market network in CI
```

## Repository Baseline

`pyproject.toml` currently declares:

- Python `>=3.11`
- pandas `>=2.0.0,<3.0.0`
- numpy `>=1.24.0`
- scipy `>=1.10.0`
- pydantic `>=2.0.0`
- pytest and pytest-cov under the `dev` extra

The requested v2.1 baseline asks for scipy `>=1.11`. Later dependency work
should raise that lower bound intentionally if a new numerical routine needs it;
Phase 0 does not change dependency pins.

## CI Safety

Phase 0 inventory and smoke tests are source-only:

```bash
python agent/scripts/dump_alpha_foundry_inventory.py
pytest agent/tests/alpha_foundry/test_alpha_foundry_inventory_smoke.py -q
```

They must not call:

- real broker APIs;
- real LLM APIs;
- external market data networks;
- shell execution through runtime tools.

## Local Execution Notes

`AGENTS.MD` and `execplan.md` are local execution instructions in this working
tree and must not be committed or pushed. They are protected by local ignore
rules.
