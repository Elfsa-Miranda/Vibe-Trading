# AAF v2.1 Data Availability Matrix

This matrix gates later phases. It is intentionally conservative: if a field is
not proven PIT-safe in the current tracked code, later phases must treat it as a
fixture, proxy or unavailable until a data audit proves otherwise.

## Matrix

| Field | Required by track | Source availability | PIT availability | Allowed conclusion cap | Downstream phase gate |
|---|---|---|---|---|---|
| `date` | all | real/derived from bars | bar date | research_candidate if audited | Phase 2 calendar normalization required |
| `symbol` | all | real | as loaded | research_candidate if universe is PIT-safe | Phase 2 universe contract required |
| `open` | limit/liquidity, price-volume | real from OHLC loaders | bar close derived unless signal before open is proven | research_candidate for EOD signals | Same-day open use must state signal time |
| `high` | limit/liquidity, price-volume | real from OHLC loaders | bar close derived | research_candidate | No future bars in factor computation |
| `low` | limit/liquidity, price-volume | real from OHLC loaders | bar close derived | research_candidate | Needed for limit-down recovery |
| `close` | all non-financial tracks | real from OHLC loaders | bar close derived | research_candidate | Cannot be joined with future return inside FactorOutputFrame |
| `prev_close` | limit/liquidity | derived from historical bar | bar close derived | research_candidate | Must be causal shifted value |
| `volume` | limit/liquidity, price-volume | real from OHLCV loaders | bar close derived | research_candidate | Queue-pressure EOD proxy remains exploratory |
| `amount` | price-volume | real/proxy depending loader | bar close derived | research_candidate if audited | Needed for Amihud/liquidity proxy |
| `turnover` | limit/liquidity, price-volume | derived/proxy | bar close derived | research_candidate if shares/float base is audited | Missing base must warn |
| `limit_up_price` | limit/liquidity | derived/proxy from close rules unless exchange field exists | bar close derived | research_candidate only after board/ST policy audit | Phase 2 must encode price-limit policy |
| `limit_down_price` | limit/liquidity | derived/proxy from close rules unless exchange field exists | bar close derived | research_candidate only after board/ST policy audit | Phase 2 must encode price-limit policy |
| `suspension_status` | tradability | proxy/fixture in current tracked code | none proven | exploratory | Phase 2 deterministic fixtures required |
| `st_status` | tradability | proxy/fixture in current tracked code | announcement_time required, not proven | exploratory | ST mask must use announcement date with T+1 lag |
| `listing_date` | tradability | fixture/proxy unless loader proves history | as loaded | exploratory until audited | New-stock mask required |
| `industry` | neutralization | unavailable/proxy in current tracked code | none proven | exploratory for neutralized claims | Phase 6 must warn on replacement taxonomy |
| `float_mktcap` | neutralization/risk | unavailable/proxy in current tracked code | none proven | exploratory for neutralized claims | Default market cap field; no silent replacement |
| `beta_60d_vs_CSI_500` | neutralization/risk | derived | bar close derived | research_candidate if benchmark series audited | Phase 6 fixed neutralization config |
| `log_avg_daily_turnover_20d` | neutralization/risk | derived | bar close derived | research_candidate if turnover inputs audited | Phase 6 fixed neutralization config |
| `benchmark_return_CSI_500` | neutralization/portfolio | real/proxy depending loader | bar close derived | research_candidate if audited | Missing benchmark blocks alpha/portfolio claim |
| `close_return` | diagnostics | derived in diagnostics join only | future label relative to signal | diagnostics only | Forbidden inside FactorOutputFrame |
| `execution_return` | limit/liquidity diagnostics | derived in diagnostics join with tradability rules | future executable label relative to signal | required for tradable limit/liquidity claim | Missing value triggers execution realism failure |
| `queue_size_at_limit` | limit queue pressure | unavailable | none | exploratory only via EOD proxy | No Level-2 queue alpha claim |
| `free_float_shares` | queue/risk/capacity | unavailable/proxy in current tracked code | none proven | exploratory until audited | Needed for real queue/capacity claims |
| `announcement_time` | financial quality | not proven in current tracked code | announcement_time | exploratory proxy only | May set `available_at = announcement_time + 1 trading day` if documented |
| `available_at` | financial quality | unavailable in current tracked code | available_at | required for research_candidate financial quality | Phase 5 adapter-only without it |
| `ingested_at` | financial quality audit | unavailable in current tracked code | ingested_at | exploratory only | Required to detect late-ingest PIT violations |
| `report_period_end` | financial quality | real/proxy | not an availability timestamp | no alpha claim by itself | Never substitute for `available_at` |

## Phase 5 Hard Gate

Current status: real PIT `available_at` for financial quality data is not
proven by tracked code inventory.

Therefore Phase 5 must use this behavior:

- If real `available_at` is absent and `announcement_time` is absent:
  adapter-only plus deterministic fixtures; no financial-quality alpha claim.
- If `announcement_time` exists but real `available_at` is absent:
  use conservative proxy `available_at = announcement_time + 1 trading day`,
  record proxy assumption, cap at exploratory, and do not claim PIT-safe.
- If `report_period_end` is used as availability:
  hard failure.
- If `ingested_at` proves data arrived after the as-of timestamp:
  PIT hard failure.

## Fields Requiring Deterministic Fixtures First

- `suspension_status`
- `st_status`
- `listing_date`
- `queue_size_at_limit`
- `free_float_shares`
- `announcement_time`
- `available_at`
- `ingested_at`

These fields may be represented by fixtures while contracts are built. Fixtures
must not be marketed as real production data availability.
