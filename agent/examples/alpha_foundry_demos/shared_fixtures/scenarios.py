"""Deterministic scenario builders for Alpha Foundry flagship demos."""

from __future__ import annotations

import tempfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.alpha_foundry.common.errors import ConclusionLevel, HardFailureCode
from src.alpha_foundry.diagnostics.falsification import FactorFalsificationReport, run_factor_falsification
from src.alpha_foundry.forward.kill_rules import evaluate_forward_status
from src.alpha_foundry.forward.model import create_forward_observation, create_forward_tracking_plan
from src.alpha_foundry.forward.store import ForwardObservationJsonlStore, ForwardStoreMutationError
from src.alpha_foundry.overfit.trial_ledger import TrialLedger
from src.alpha_foundry.portfolio.combine import assess_orthogonal_alpha
from src.alpha_foundry.portfolio.optimizer import PortfolioConstraints, construct_long_only_top_n_portfolio
from src.alpha_foundry.portfolio.risk_model import build_risk_model_snapshot
from src.alpha_foundry.reports.builder import build_alpha_foundry_report, make_factor_candidate_card
from src.reliability.quant.methodology_facts import AlphaFoundryMethodologyFacts
from src.reliability.quant.scorecard_policy import (
    AlphaFoundryClaim,
    AlphaFoundryClaimSet,
    AlphaFoundryScorecard,
    evaluate_alpha_foundry_scorecard,
)
from src.research_card.builder import AlphaFoundryResearchCard, build_alpha_foundry_research_card


PROTOCOL_HASH = "protocol-alpha-foundry-demo"


def build_naive_limit_momentum_trap() -> dict[str, Any]:
    factor, returns, exposures = factor_return_fixture(
        factor_id="naive_limit_momentum",
        return_column="close_return",
    )
    report, ledger = run_factor_falsification(
        factor,
        returns,
        factor_id="naive_limit_momentum",
        hypothesis_id="naive_limit_momentum",
        track="limit_liquidity_microstructure",
        factor_definition_hash="hash-naive_limit_momentum",
        protocol_hash=PROTOCOL_HASH,
        ledger=TrialLedger.create(ledger_id="ledger-naive-limit", family_id="limit_liquidity_microstructure"),
        exposures=exposures,
        return_column="close_return",
        parameter_variant={"demo": "naive_limit_momentum_trap"},
    )
    return build_demo_output(
        demo_name="naive_limit_momentum_trap",
        factor_id="naive_limit_momentum",
        hypothesis_id="naive_limit_momentum",
        track="limit_liquidity_microstructure",
        factor_definition_hash="hash-naive_limit_momentum",
        falsification_report=report,
        ledger=ledger,
        claim_type="tradable",
        facts_overrides={"uses_execution_return": False, "has_tradability_mask": False},
        extra_warnings=["naive_close_return_rejected_by_tradability_gate"],
        proxy_note=None,
    )


def build_failed_limit_breakout_candidate() -> dict[str, Any]:
    factor, returns, exposures = factor_return_fixture(
        factor_id="failed_limit_breakout_reversal",
        return_column="execution_return",
    )
    report, ledger = run_factor_falsification(
        factor,
        returns,
        factor_id="failed_limit_breakout_reversal",
        hypothesis_id="failed_limit_breakout_reversal",
        track="limit_liquidity_microstructure",
        factor_definition_hash="hash-failed_limit_breakout_reversal",
        protocol_hash=PROTOCOL_HASH,
        ledger=TrialLedger.create(ledger_id="ledger-breakout", family_id="limit_liquidity_microstructure"),
        exposures=exposures,
        return_column="execution_return",
        placebo_rank_ics=[0.01],
        regime_ic={"bull": 0.035, "sideways": 0.028, "bear": 0.012},
        parameter_variant={"demo": "failed_limit_breakout_candidate"},
    )
    return build_demo_output(
        demo_name="failed_limit_breakout_candidate",
        factor_id="failed_limit_breakout_reversal",
        hypothesis_id="failed_limit_breakout_reversal",
        track="limit_liquidity_microstructure",
        factor_definition_hash="hash-failed_limit_breakout_reversal",
        falsification_report=report,
        ledger=ledger,
        claim_type="alpha",
        facts_overrides={"uses_execution_return": True},
        proxy_note=None,
    )


def build_public_alpha_crowding_trap() -> dict[str, Any]:
    factor, returns, exposures = factor_return_fixture(
        factor_id="public_alpha_crowding_proxy",
        return_column="close_return",
        size_driven=True,
    )
    report, ledger = run_factor_falsification(
        factor,
        returns,
        factor_id="public_alpha_crowding_proxy",
        hypothesis_id="public_alpha_crowding_proxy",
        track="residual_price_volume_behavior",
        factor_definition_hash="hash-public_alpha_crowding_proxy",
        protocol_hash=PROTOCOL_HASH,
        ledger=TrialLedger.create(ledger_id="ledger-crowding", family_id="residual_price_volume_behavior"),
        exposures=exposures,
        placebo_rank_ics=[0.20],
        parameter_variant={"demo": "public_alpha_crowding_trap"},
    )
    return build_demo_output(
        demo_name="public_alpha_crowding_trap",
        factor_id="public_alpha_crowding_proxy",
        hypothesis_id="public_alpha_crowding_proxy",
        track="residual_price_volume_behavior",
        factor_definition_hash="hash-public_alpha_crowding_proxy",
        falsification_report=report,
        ledger=ledger,
        claim_type="factor_novelty",
        extra_warnings=["public_analogue_crowding_stress_cap"],
        proxy_note="Public analogue proxy only; crowding stress required before promotion.",
    )


def build_orthogonal_portfolio_increment() -> dict[str, Any]:
    factor, returns, exposures = factor_return_fixture(
        factor_id="orthogonal_breakout_increment",
        return_column="execution_return",
    )
    falsification, ledger = run_factor_falsification(
        factor,
        returns,
        factor_id="orthogonal_breakout_increment",
        hypothesis_id="orthogonal_breakout_increment",
        track="residual_price_volume_behavior",
        factor_definition_hash="hash-orthogonal_breakout_increment",
        protocol_hash=PROTOCOL_HASH,
        ledger=TrialLedger.create(ledger_id="ledger-orthogonal", family_id="residual_price_volume_behavior"),
        exposures=exposures,
        return_column="execution_return",
        placebo_rank_ics=[0.01],
        parameter_variant={"demo": "orthogonal_portfolio_increment"},
    )
    combo_frame = pd.DataFrame(
        {
            "candidate": [0.1, 0.3, 0.2, 0.5, 0.4],
            "existing_value": [0.2, -0.1, 0.1, 0.0, 0.3],
            "existing_momentum": [-0.2, 0.2, 0.0, 0.1, 0.4],
        }
    )
    orthogonal = assess_orthogonal_alpha(
        combo_frame,
        candidate_column="candidate",
        existing_factor_columns=["existing_value", "existing_momentum"],
        marginal_ic_after_existing=0.031,
    )
    scores = pd.DataFrame(
        {
            "symbol": [f"S{i:03d}" for i in range(10)],
            "score": [10 - i for i in range(10)],
            "sector": ["SW_TECH" if i % 2 else "SW_BANK" for i in range(10)],
            "adv": [50_000_000.0 for _ in range(10)],
            "price": [10.0 + i for i in range(10)],
        }
    )
    constraints = PortfolioConstraints(top_n=5, single_name_cap=0.05, sector_cap=0.25, turnover_cap=0.20, adv_cap=0.10)
    portfolio = construct_long_only_top_n_portfolio(scores, constraints=constraints)
    risk_model = build_risk_model_snapshot(
        model_id="risk-model-orthogonal-demo",
        as_of=date(2026, 1, 9),
        universe=list(scores["symbol"]),
        factor_names=["market", "size"],
        factor_covariance_matrix=np.array([[0.04, 0.01], [0.01, 0.03]]),
        residual_variance={str(symbol): 0.01 for symbol in scores["symbol"]},
        estimation_window_days=60,
    )
    output = build_demo_output(
        demo_name="orthogonal_portfolio_increment",
        factor_id="orthogonal_breakout_increment",
        hypothesis_id="orthogonal_breakout_increment",
        track="residual_price_volume_behavior",
        factor_definition_hash="hash-orthogonal_breakout_increment",
        falsification_report=falsification,
        ledger=ledger,
        claim_type="portfolio_candidate",
        facts_overrides={"has_risk_model": True, "risk_model_covariance_psd": risk_model.covariance_psd},
        portfolio_report_refs=[portfolio.report_id, orthogonal.report_id, risk_model.model_id],
    )
    output["portfolio"] = {
        "accepted_incremental_alpha": orthogonal.accepted,
        "max_abs_correlation": round_float(orthogonal.max_abs_correlation),
        "marginal_ic_after_existing": round_float(orthogonal.marginal_ic_after_existing),
        "risk_model_covariance_psd": risk_model.covariance_psd,
        "constraints_tested": portfolio.constraints,
        "hard_failures": [failure.value for failure in portfolio.hard_failures],
    }
    return output


def build_forward_decay_kill() -> dict[str, Any]:
    factor, returns, exposures = factor_return_fixture(
        factor_id="forward_decay_candidate",
        return_column="execution_return",
    )
    falsification, ledger = run_factor_falsification(
        factor,
        returns,
        factor_id="forward_decay_candidate",
        hypothesis_id="forward_decay_candidate",
        track="residual_price_volume_behavior",
        factor_definition_hash="hash-forward_decay_candidate",
        protocol_hash=PROTOCOL_HASH,
        ledger=TrialLedger.create(ledger_id="ledger-forward-decay", family_id="residual_price_volume_behavior"),
        exposures=exposures,
        return_column="execution_return",
        parameter_variant={"demo": "forward_decay_kill"},
    )
    plan = create_forward_tracking_plan(
        plan_id="plan-forward-decay",
        factor_id="forward_decay_candidate",
        hypothesis_id="forward_decay_candidate",
        frozen_factor_definition_hash="hash-forward_decay_candidate",
        expected_rank_ic=0.04,
        min_observations_required=12,
    )
    mutation_error = ""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ForwardObservationJsonlStore(Path(tmpdir) / "forward.jsonl")
        observations = []
        for idx, realized_ic in enumerate((-0.01, -0.02, -0.03), start=1):
            observation = create_forward_observation(
                observation_id=f"obs-{idx}",
                plan_id=plan.plan_id,
                period_start=date(2026, 1, idx),
                period_end=date(2026, 1, idx + 1),
                realized_rank_ic=realized_ic,
            )
            observations.append(store.append(observation))
        try:
            store.update(observations[0])
        except ForwardStoreMutationError as exc:
            mutation_error = str(exc)
    status = evaluate_forward_status(plan, observations)
    output = build_demo_output(
        demo_name="forward_decay_kill",
        factor_id="forward_decay_candidate",
        hypothesis_id="forward_decay_candidate",
        track="residual_price_volume_behavior",
        factor_definition_hash="hash-forward_decay_candidate",
        falsification_report=falsification,
        ledger=ledger,
        claim_type="paper_tracking_candidate",
        facts_overrides={"has_forward_plan": True, "forward_plan_frozen": True},
        forward_plan_refs=[plan.plan_id],
        extra_warnings=["forward_status_killed_by_append_only_observations"],
    )
    output["forward_status"] = status.status
    output["forward_reasons"] = status.reasons
    output["mutation_error"] = mutation_error
    output["forward_plan"] = {
        "plan_id": plan.plan_id,
        "frozen_config_hash": plan.frozen_config_hash,
        "min_observations_required": plan.min_observations_required,
    }
    return output


def build_demo_output(
    *,
    demo_name: str,
    factor_id: str,
    hypothesis_id: str,
    track: str,
    factor_definition_hash: str,
    falsification_report: FactorFalsificationReport,
    ledger: TrialLedger,
    claim_type: str,
    facts_overrides: dict[str, Any] | None = None,
    extra_warnings: list[str] | None = None,
    proxy_note: str | None = None,
    portfolio_report_refs: list[str] | None = None,
    forward_plan_refs: list[str] | None = None,
) -> dict[str, Any]:
    card = make_factor_candidate_card(
        factor_id=factor_id,
        hypothesis_id=hypothesis_id,
        factor_definition_hash=factor_definition_hash,
        falsification_report_ref=f"generated-{demo_name}-falsification",
        conclusion_level=falsification_report.conclusion_cap,
        key_metrics={
            "rank_ic_after_neutralization": falsification_report.rank_ic_after_neutralization,
            "t_stat_after_neutralization": falsification_report.t_stat_after_neutralization,
        },
        hard_failures=falsification_report.hard_failures,
        warnings=(falsification_report.warnings + list(extra_warnings or [])),
        next_action="reject" if falsification_report.hard_failures else "forward_track",
        trial_count=ledger.trial_count(family_id=track, sub_family_id=hypothesis_id),
        proxy_note=proxy_note,
        uses_execution_return=falsification_report.execution_return_used,
    )
    report = build_alpha_foundry_report(
        report_id=f"{demo_name}-report",
        protocol_hash=PROTOCOL_HASH,
        cards=[card],
        portfolio_report_refs=portfolio_report_refs or [],
        forward_plan_refs=forward_plan_refs or [],
        trial_ledger_ref=f"ledger-{demo_name}",
    )
    scorecard = build_scorecard(
        report=report,
        claim_type=claim_type,
        facts=build_facts(
            report_id=report.report_id,
            protocol_hash=report.protocol_hash,
            trial_count=card.trial_count,
            uses_execution_return=falsification_report.execution_return_used,
            has_proxy_only_data=proxy_note is not None,
            overrides=facts_overrides or {},
        ),
    )
    research_card = build_alpha_foundry_research_card(report=report, scorecard=scorecard)
    return normalized_output(
        demo_name=demo_name,
        report=report,
        scorecard=scorecard,
        research_card=research_card,
        ledger=ledger,
        track=track,
        hypothesis_id=hypothesis_id,
        falsification_report=falsification_report,
    )


def build_scorecard(
    *,
    report,
    claim_type: str,
    facts: AlphaFoundryMethodologyFacts,
) -> AlphaFoundryScorecard:
    claim_set = AlphaFoundryClaimSet(
        claim_set_id=f"claims-{report.report_id}",
        run_id="run-demo",
        claims=[
            AlphaFoundryClaim(
                claim_id=f"claim-{claim_type}",
                claim_type=claim_type,  # type: ignore[arg-type]
                claim_text=f"deterministic {claim_type} claim",
                evidence_refs=[report.report_id],
            )
        ],
    )
    return evaluate_alpha_foundry_scorecard(
        report=report,
        claim_set=claim_set,
        methodology_facts=facts,
    )


def build_facts(
    *,
    report_id: str,
    protocol_hash: str,
    trial_count: int | None,
    uses_execution_return: bool,
    has_proxy_only_data: bool,
    overrides: dict[str, Any],
) -> AlphaFoundryMethodologyFacts:
    payload: dict[str, Any] = {
        "run_id": f"run-{report_id}",
        "protocol_hash": protocol_hash,
        "has_factor_formula": True,
        "uses_execution_return": uses_execution_return,
        "has_tradability_mask": True,
        "has_trial_ledger": True,
        "trial_count": trial_count,
        "has_multiple_testing_report": True,
        "has_risk_model": True,
        "risk_model_covariance_psd": True,
        "has_forward_plan": True,
        "forward_plan_frozen": True,
        "has_proxy_only_data": has_proxy_only_data,
        "has_benchmark": True,
    }
    payload.update(overrides)
    return AlphaFoundryMethodologyFacts(**payload)


def normalized_output(
    *,
    demo_name: str,
    report,
    scorecard: AlphaFoundryScorecard,
    research_card: AlphaFoundryResearchCard,
    ledger: TrialLedger,
    track: str,
    hypothesis_id: str,
    falsification_report: FactorFalsificationReport,
) -> dict[str, Any]:
    trial_count = ledger.trial_count(family_id=track, sub_family_id=hypothesis_id)
    return {
        "schema_version": "2.1.0",
        "demo_name": demo_name,
        "status": "snapshot_ready",
        "conclusion_level": scorecard.conclusion_level.value,
        "falsified": falsification_report.falsified,
        "error_codes": [failure.value for failure in scorecard.hard_failures],
        "warnings": sorted(set(report.warnings + scorecard.warnings + research_card.warnings)),
        "report_ref": report.report_id,
        "research_card_ref": research_card.card_id,
        "factor_definition_hashes": research_card.factor_definition_hashes,
        "trial_ledger": {
            "source": "TrialLedger",
            "family_id": track,
            "sub_family_id": hypothesis_id,
            "trial_count": trial_count,
            "outcome_counts": dict(sorted(Counter(record.outcome for record in ledger.records).items())),
        },
        "metrics": {
            "rank_ic_after_neutralization": round_float(falsification_report.rank_ic_after_neutralization),
            "t_stat_after_neutralization": round_float(falsification_report.t_stat_after_neutralization),
            "placebo_max_rank_ic": round_float(falsification_report.placebo_max_rank_ic),
            "regime_negative_fraction": round_float(falsification_report.regime_negative_fraction),
        },
    }


def factor_return_fixture(
    *,
    factor_id: str,
    return_column: str,
    size_driven: bool = False,
    dates: int = 3,
    symbols: int = 35,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    factor_rows: list[dict[str, object]] = []
    return_rows: list[dict[str, object]] = []
    exposure_rows: list[dict[str, object]] = []
    for d in range(dates):
        day = pd.Timestamp("2026-01-05") + pd.Timedelta(days=d)
        for s in range(symbols):
            symbol = f"S{s:03d}"
            value = float(s)
            factor_value = value if size_driven else value + (d * 0.01)
            return_value = value / 100.0
            factor_rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "factor_value": factor_value,
                    "factor_id": factor_id,
                    "as_of": day + pd.Timedelta(hours=15),
                    "available_at": day + pd.Timedelta(hours=15),
                }
            )
            return_rows.append({"date": day, "symbol": symbol, return_column: return_value})
            exposure_rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "industry": "SW_BANK" if s % 2 == 0 else "SW_TECH",
                    "float_mktcap": 100.0 + (value if size_driven else 0.0),
                    "beta_60d": 1.0,
                    "log_avg_daily_turnover_20d": 2.0,
                }
            )
    return pd.DataFrame(factor_rows), pd.DataFrame(return_rows), pd.DataFrame(exposure_rows)


def round_float(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)
