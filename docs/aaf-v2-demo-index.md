# A-Share Alpha Foundry v2.1 Demo Index

Each demo is deterministic, dry-run capable, and compares computed output against
`expected_output.json`. The runners call explicit Alpha Foundry builders and do
not attach reports, warnings, Research Card sections, scorecards, API routes, or
UI panels to legacy paths by default.

## Naive Limit Momentum Trap

Path:

```text
agent/examples/alpha_foundry_demos/naive_limit_momentum_trap/
```

Command:

```text
python agent/examples/alpha_foundry_demos/naive_limit_momentum_trap/runner.py --dry-run
```

Expected result:

- Snapshot match.
- Naive close-return evidence is rejected by tradability validation.
- `EXECUTION_RETURN_MISSING` is present.
- Conclusion is invalid rather than a tradable alpha claim.

## Failed Limit Breakout Candidate

Path:

```text
agent/examples/alpha_foundry_demos/failed_limit_breakout_candidate/
```

Command:

```text
python agent/examples/alpha_foundry_demos/failed_limit_breakout_candidate/runner.py --dry-run
```

Expected result:

- Snapshot match.
- Candidate reaches `research_candidate`.
- `rank_ic_after_neutralization > 0.02`.
- `t_stat_after_neutralization > 1.5`.
- Placebo IC is lower than the selected factor.
- Negative regime fraction is below 40 percent.
- `falsified` is false and TrialLedger count is disclosed.

## Public Alpha Crowding Trap

Path:

```text
agent/examples/alpha_foundry_demos/public_alpha_crowding_trap/
```

Command:

```text
python agent/examples/alpha_foundry_demos/public_alpha_crowding_trap/runner.py --dry-run
```

Expected result:

- Snapshot match.
- Raw IC does not survive neutralization and crowding stress.
- `NEUTRALIZED_IC_COLLAPSE`, `PLACEBO_COMPARABLE`, and `EOD_PROXY_OVERCLAIM` are present.
- Proxy/crowding warning caps the claim.

## Orthogonal Portfolio Increment

Path:

```text
agent/examples/alpha_foundry_demos/orthogonal_portfolio_increment/
```

Command:

```text
python agent/examples/alpha_foundry_demos/orthogonal_portfolio_increment/runner.py --dry-run
```

Expected result:

- Snapshot match.
- Baseline versus candidate comparison is disclosed.
- Risk model PSD is true.
- Benchmark, single-name cap, sector cap, turnover cap, ADV cap, T+1 feasibility, factor correlation, and marginal IC gates are tested.
- Candidate is accepted only through positive marginal contribution, not production readiness.

## Forward Decay Kill

Path:

```text
agent/examples/alpha_foundry_demos/forward_decay_kill/
```

Command:

```text
python agent/examples/alpha_foundry_demos/forward_decay_kill/runner.py --dry-run
```

Expected result:

- Snapshot match.
- Forward plan includes `frozen_config_hash`, `kill_rule_params`, and `min_observations_required`.
- Observations are append-only.
- Consecutive negative IC triggers killed status.
- Attempted mutation fails with an append-only error.
