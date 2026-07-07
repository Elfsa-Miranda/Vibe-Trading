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
-> scorecard / Research Card / evidence closure
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
  next work can wrap current interfaces instead of inventing a parallel stack.

## IRR-AGL Role

IRR-AGL remains the evidence and gate infrastructure. Alpha Foundry produces
research objects; IRR-AGL keeps those objects auditable.

Required references for later Alpha Foundry outputs:

- artifact refs for factor specs, falsification reports, portfolio reports,
  forward plans and Research Cards;
- ClaimSet refs for alpha, tradable, generalization, novelty, portfolio and
  paper-tracking claims;
- MethodologyFactSet refs for PIT, tradability, TrialLedger, neutralization,
  risk model and forward-plan facts;
- ScorecardPolicy triggered rules with deterministic hard failure codes;
- evidence closure refs proving card/API/UI consistency.

Current tracked code on the main-based branch has reliability artifact store
and redaction primitives, but not the full v2.1 Alpha Foundry contracts. Later
phases must add those contracts incrementally without changing public
interfaces.

## In Scope

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
