# A-Share Alpha Foundry v2.1 Known Limitations

This document records intentional limits and non-goals for the hardened Alpha Foundry package.

## Data And Factor Limits

- Demo data is deterministic fixture data. It is suitable for regression and evidence-shape tests, not live alpha validation.
- EOD fallback for `limit_queue_pressure_proxy` is exploratory only. It must not be described as Level-2 queue alpha without actual Level-2, tick, or queue data.
- Financial quality factors require PIT financial statement availability. Missing or late filing metadata must keep the factor exploratory or invalid.
- `FactorOutputFrame` intentionally excludes labels, future returns, execution returns, and targets. Forward returns are joined only in diagnostics.

## Research Diagnostics Limits

- Falsification thresholds are deterministic gates. They are not a substitute for economic review, venue microstructure review, or production risk approval.
- Placebo, regime, decay, and correlation diagnostics are implemented for controlled research workflows and deterministic fixtures.
- TrialLedger is the source of trial counts. Reports should not infer trial count from filenames, directories, or selected-card counts.

## Portfolio And Execution Limits

- The portfolio module is a constrained optimizer MVP. It checks risk model PSD, benchmark presence, single-name cap, sector cap, turnover cap, ADV cap, T+1 feasibility, factor correlation, and marginal IC gates.
- It is not a production optimizer and does not include broker integration, intraday execution scheduling, smart order routing, or real-time mandate controls.
- Execution and capacity simulations are deterministic research simulations. They do not authorize live trading.

## Forward Tracking Limits

- Forward tracking is paper-only. It freezes factor definitions, kill rules, and config hashes before observation collection.
- Observations are append-only JSONL-style records by default. Update/delete mutation is intentionally rejected.
- Kill rules are deterministic and conservative; they do not replace committee or mandate review.

## API, UI, And Report Limits

- Alpha Foundry API additions are read-only and opt-in.
- `VIBE_TRADING_ALPHA_FOUNDRY_MODE` defaults to `off`; `warn` is not the
  default and must not alter legacy run payloads.
- API route mounting requires both an enabled mode and
  `VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API=1`.
- Frontend panels, Research Card sections, scorecard bridges, and reliability
  policy integration are deferred from the first upstream PRs.
- Local report output should be produced by explicit CLI/function/test calls,
  not by default legacy backtest or session paths.
- UI consistency tests cover fixture surfaces only; they do not replace
  end-to-end production monitoring.

## Security Limits

- No broker credential, token, or environment secret should appear in trace, artifact, card, API, UI, or demo output.
- The demo harness does not call real network, shell, broker, or live execution paths.
- Local operator instruction files `AGENTS.MD` and `execplan.md` are intentionally excluded from commits and remote pushes.
