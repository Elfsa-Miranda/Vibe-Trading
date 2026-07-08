# AAF v2.1 Focus Lock

## Decision

The next stage is one deep chain:

```text
A-share mechanism hypothesis
-> PIT-safe factor panel
-> A-share tradability mask
-> mechanism factor library
-> factor falsification
-> TrialLedger / multiple testing
-> orthogonal alpha combination
-> constrained portfolio
-> execution and capacity simulation
-> forward paper tracking
-> local alpha_foundry report artifact
```

This is not a broad Agent expansion and not an Alpha Zoo refresh. The product of
this stage is an auditable research foundry that can reject attractive but
invalid A-share alphas, and preserve only narrowly supported candidates for
portfolio and forward tracking.

## Why A-share Mechanism Alphas

A-share research is the best high-value target for this repository because the
market rules are hard to fake safely:

- T+1 sell restrictions affect rebalance feasibility.
- Limit-up and limit-down states separate close returns from executable
  returns.
- Suspensions, ST status, new-stock filters, one-word boards, lot size, fees and
  capacity all create places where naive backtests overstate tradability.
- Existing code already contains China A backtest and loader surfaces, so the
  next work can extend through explicit, opt-in, local adapters instead of
  replacing runtime objects.

## Upstream Integration Boundary

Alpha Foundry must land as a pure research package first. It must not change
legacy backtest, session, registry, Research Card, scorecard, API, or UI paths
unless a caller explicitly opts in.

Default operational posture:

- `VIBE_TRADING_ALPHA_FOUNDRY_MODE` defaults to `off`.
- `observe`, `warn`, and `enforce` are not enough to attach Alpha Foundry to a
  legacy path.
- API exposure also requires `VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API=1`.
- No default Research Card section, scorecard bridge, API route, UI panel,
  report adapter, warning, or artifact may be added to an existing legacy run.

Accepted first landing surfaces:

- `agent/src/alpha_foundry/reports/model.py`
- `agent/src/alpha_foundry/reports/render_markdown.py`
- deterministic fixtures
- local JSON/Markdown artifacts created only by explicit CLI/function/test calls

Deferred integration surfaces:

- `agent/src/reliability/quant/methodology_facts.py`
- `agent/src/reliability/quant/scorecard_policy.py`
- `agent/src/research_card/builder.py`
- `agent/src/research_card/render_markdown.py`
- global API/UI exposure

Current tracked code on the main-based branch has reliability artifact store
and redaction primitives, but not the full v2.1 Alpha Foundry contracts. Later
phases must add those contracts incrementally without changing public
interfaces.

## Upstream PR Slice

Do not submit AAF-IRR v2.1 as one full-stack PR. Slice by reviewable boundary:

1. A-share alpha_foundry docs and inventory only.
2. Pure schema plus deterministic fixtures.
3. Tradability masks.
4. One factor family with tests.
5. Diagnostics only.

Portfolio, forward tracking, Research Card, scorecard, API/UI, performance,
demos, and migration stay out of the first upstream sequence until maintainers
accept the core package boundary.

## Research Scope

- `limit_liquidity_microstructure`: limit locks, failed breakouts, one-word
  boards, limit gaps and liquidity recovery.
- `residual_price_volume_behavior`: residual momentum, turnover unwind,
  liquidity-conditioned reversal and volume-price divergence.
- `pit_financial_quality_revision`: data-gated adapter and fixtures unless
  real PIT availability is proven.

## Deferred

- Live trading expansion.
- HFT or order-book execution simulation.
- Options lab.
- Global multi-asset expansion.
- Production optimizer claims.
- Any LLM-authored upgrade of scorecard conclusions.

## Phase 0 Gate

Financial quality alpha claims are blocked until real `available_at` support is
proven. `announcement_time` may only support an explicit conservative proxy
with one-trading-day lag and an exploratory cap. `report_period_end` is never an
availability timestamp.

Rollback: delete this document and the other Phase 0 docs/script/test.
