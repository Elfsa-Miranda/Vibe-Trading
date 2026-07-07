# AAF v2.1 Current Quant Capability Map

Generated from `python agent/scripts/dump_alpha_foundry_inventory.py` on the
main-based Alpha Foundry branch.

## Current Strengths

| Area | Current surface | Phase 0 read |
|---|---|---|
| Factor Zoo | `agent/src/factors/zoo` with 456 tracked factor modules across `academic`, `alpha101`, `gtja191`, `qlib158` | Strong raw factor inventory, but not hypothesis-first and not A-share mechanism-gated. |
| Factor registry | `agent/src/factors/registry.py` | AST metadata scan, lazy import and purity checks are useful patterns for future FactorSpec loading. |
| Factor operators | `agent/src/factors/base.py` | Causal operators and lookahead bans exist; future Alpha Foundry contracts should reuse the discipline. |
| Backtest engines | `agent/backtest/engines/china_a.py` plus global/futures/crypto engines | China A engine already captures no shorting, T+1 sell block, price limits, lot size and fees at a basic execution-rule level. |
| Data loaders | BaoStock, Tencent, Tushare, Akshare, Eastmoney, Sina, local and others | Useful source adapters exist, but Phase 0 does not prove PIT `available_at` for financial statements. |
| Tests | 13 factor tests and 20 loader/backtest engine tests in tracked main branch | Good smoke foundation; Alpha Foundry-specific contracts are absent before this phase. |
| Reliability | `agent/src/reliability/artifacts`, redaction and schema helpers | Artifact store is present and should be referenced by later Alpha Foundry reports. |

## Wrap Without Public Interface Changes

The following can be wrapped in later phases without changing public signatures:

- `BaseTool.execute(**kwargs) -> str`: Alpha Foundry must not alter this.
- `ToolRegistry.execute(name, params) -> str`: later governance wrapping must be
  outside this public contract.
- `DataLoaderProtocol.fetch(codes, start_date, end_date, interval="1D", fields=None) -> dict[str, DataFrame]`:
  FactorPanel construction should consume loader output and add PIT/tradability
  contracts around it.
- `Registry.compute(alpha_id, panel) -> pd.DataFrame`: legacy Alpha Zoo can stay
  as a source of comparison/placebo candidates, not as the Alpha Foundry truth
  model.
- `ChinaAEngine.can_execute`, `round_size`, and fee helpers can inform
  tradability and execution-return fixtures.

## Gaps To Close

| Gap | Impact | Owning phase |
|---|---|---|
| No AlphaHypothesis registry | Factor names can be mistaken for mechanisms. | Phase 1 |
| No TrialLedger for alpha trials | Trial count and best-trial disclosure cannot be trusted. | Phase 1, Phase 6, Phase 7 |
| No FactorOutputFrame contract | Factor values could carry labels or future returns. | Phase 2 |
| No A-share tradability mask report | Limit, ST, suspension, new stock and lot policies are not auditable at factor-panel level. | Phase 2 |
| No deterministic AAF factor specs | Factor formulas could drift from names. | Phase 2-4 |
| No AAF falsification engine | IC, neutralization, placebo, regime and cost gates are not deterministic. | Phase 6 |
| No AAF portfolio/risk model report | Portfolio candidate claims would lack benchmark, PSD covariance and constraints. | Phase 8 |
| No forward append-only tracking store | Paper tracking can be retroactively edited. | Phase 9 |
| No AAF scorecard/card exact-match gate | Hard failures could drift across card/API/UI. | Phase 10-11 |

## Current Test Smoke State

Recommended legacy smoke commands during early phases:

```bash
pytest agent/tests/factors/test_registry.py -q
pytest agent/tests/factors/test_lookahead.py -q
pytest agent/tests/test_china_a_engine.py -q
pytest agent/tests/test_baostock_loader.py -q
pytest agent/tests/reliability/test_artifact_store.py -q
```

Phase 0 adds:

```bash
python agent/scripts/dump_alpha_foundry_inventory.py
pytest agent/tests/alpha_foundry/test_alpha_foundry_inventory_smoke.py -q
```

## Known Limitations

- The inventory is source-level only; it does not prove runtime data quality.
- No real market network, broker or LLM call is made.
- Existing China A execution rules are useful but not sufficient for the
  Phase 2 tradability mask or Phase 6 execution-return validation.
- Current tracked main branch does not contain a complete IRR-AGL scorecard,
  governance, ClaimSet or Research Card implementation; later phases must add
  or integrate them incrementally.
