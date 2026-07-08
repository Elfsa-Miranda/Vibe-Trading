"""Read-only Alpha Foundry API routes."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, HTTPException

AuthDep = Callable[..., Awaitable[Any] | Any]
ALPHA_FOUNDRY_MODE_ENV = "VIBE_TRADING_ALPHA_FOUNDRY_MODE"
ALPHA_FOUNDRY_ENABLE_API_ENV = "VIBE_TRADING_ALPHA_FOUNDRY_ENABLE_API"
VALID_ALPHA_FOUNDRY_MODES = frozenset({"off", "observe", "warn", "enforce"})


def alpha_foundry_mode() -> str:
    """Return the explicit Alpha Foundry mode.

    Default is ``off`` so legacy API/session/backtest paths do not gain report
    sections, warnings, or routes unless an operator opts in.
    """
    mode = os.getenv(ALPHA_FOUNDRY_MODE_ENV, "off").strip().lower() or "off"
    return mode if mode in VALID_ALPHA_FOUNDRY_MODES else "off"


def alpha_foundry_api_enabled() -> bool:
    """Return whether the fixture-backed Alpha Foundry API should be mounted."""
    enabled = os.getenv(ALPHA_FOUNDRY_ENABLE_API_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
    return enabled and alpha_foundry_mode() != "off"


def register_alpha_foundry_routes(app: FastAPI, require_auth: AuthDep | None = None) -> None:
    dependencies = [Depends(require_auth)] if require_auth is not None else []

    @app.get("/research/alpha-foundry/reports/{report_id}", dependencies=dependencies)
    async def get_alpha_foundry_report(report_id: str) -> dict[str, Any]:
        surface = _fixture_surface()
        if report_id != surface["report"]["report_id"]:
            raise HTTPException(status_code=404, detail="alpha_foundry report not found")
        return surface

    @app.get("/research/alpha-foundry/factors/{factor_id}", dependencies=dependencies)
    async def get_alpha_foundry_factor(factor_id: str) -> dict[str, Any]:
        surface = _fixture_surface()
        factor = surface["factor"]
        if factor_id != factor["factor_id"]:
            raise HTTPException(status_code=404, detail="alpha_foundry factor not found")
        return factor

    @app.get("/research/alpha-foundry/forward/{plan_id}", dependencies=dependencies)
    async def get_alpha_foundry_forward(plan_id: str) -> dict[str, Any]:
        surface = _fixture_surface()
        forward = surface["forward"]
        if plan_id != forward["plan_id"]:
            raise HTTPException(status_code=404, detail="alpha_foundry forward plan not found")
        return forward

    @app.get("/research/alpha-foundry/trials/{family_id}", dependencies=dependencies)
    async def get_alpha_foundry_trials(family_id: str) -> dict[str, Any]:
        surface = _fixture_surface()
        trials = surface["trials"]
        if family_id != trials["family_id"]:
            raise HTTPException(status_code=404, detail="alpha_foundry trial family not found")
        return trials


def _fixture_surface() -> dict[str, Any]:
    from src.alpha_foundry.common.errors import HardFailureCode
    from src.alpha_foundry.reports.builder import build_alpha_foundry_report, make_factor_candidate_card
    from src.reliability.quant.methodology_facts import AlphaFoundryMethodologyFacts
    from src.reliability.quant.scorecard_policy import (
        AlphaFoundryClaim,
        AlphaFoundryClaimSet,
        evaluate_alpha_foundry_scorecard,
    )
    from src.research_card.builder import (
        build_alpha_foundry_card_consistency_fixture,
        build_alpha_foundry_research_card,
    )

    factor_id = "limit_queue_pressure_proxy"
    proxy_note = "EOD proxy only; no Level-2 queue alpha claim."
    card = make_factor_candidate_card(
        factor_id=factor_id,
        hypothesis_id=factor_id,
        factor_definition_hash=f"hash-{factor_id}",
        falsification_report_ref=f"falsification-{factor_id}",
        hard_failures=[HardFailureCode.EOD_PROXY_OVERCLAIM],
        proxy_note=proxy_note,
        trial_count=8,
        uses_execution_return=True,
        key_metrics={
            "rank_ic_mean": 0.045,
            "close_return_mean": 0.012,
            "execution_return_mean": 0.009,
        },
        next_action="reject",
    )
    report = build_alpha_foundry_report(
        report_id="aaf-report",
        protocol_hash="protocol-hash",
        cards=[card],
        trial_ledger_ref="ledger-limit-liquidity",
        forward_plan_refs=["plan-limit-queue-pressure"],
    )
    claim_set = AlphaFoundryClaimSet(
        claim_set_id="claims-aaf-report",
        run_id="run-aaf",
        claims=[
            AlphaFoundryClaim(
                claim_id="claim-alpha",
                claim_type="alpha",
                claim_text="EOD proxy demonstrates alpha",
                evidence_refs=[report.report_id],
            )
        ],
    )
    facts = AlphaFoundryMethodologyFacts(
        run_id="run-aaf",
        protocol_hash=report.protocol_hash,
        has_factor_formula=True,
        uses_execution_return=True,
        has_tradability_mask=True,
        has_trial_ledger=True,
        trial_count=8,
        has_multiple_testing_report=True,
        has_risk_model=True,
        risk_model_covariance_psd=True,
        has_forward_plan=True,
        forward_plan_frozen=True,
        has_proxy_only_data=True,
        has_benchmark=True,
    )
    scorecard = evaluate_alpha_foundry_scorecard(
        report=report,
        claim_set=claim_set,
        methodology_facts=facts,
    )
    research_card = build_alpha_foundry_research_card(report=report, scorecard=scorecard)
    fixture = build_alpha_foundry_card_consistency_fixture(card=research_card, scorecard=scorecard)
    factor = {
        "factor_id": factor_id,
        "factor_definition_hash": card.factor_definition_hash,
        "proxy_note": proxy_note,
        "return_validation": {
            "execution_return": "used_for_tradable_validation",
            "close_return": "diagnostics_only",
        },
        "falsification_gates": [
            rule.model_dump(mode="json") for rule in scorecard.triggered_rules
        ],
    }
    forward = {
        "plan_id": "plan-limit-queue-pressure",
        "status": "paper_tracking",
        "frozen_config_hash": "frozen-config-hash-limit-queue-pressure",
        "kill_rule_params": {
            "consecutive_negative_ic_n": 3,
            "realized_vs_expected_ratio_min": 0.30,
            "ic_decay_threshold_pct": 0.30,
        },
        "min_observations_required": 12,
    }
    trials = {
        "family_id": "limit_liquidity",
        "trial_count": 8,
        "source": "TrialLedger",
        "outcome_counts": {"reported": 7, "rejected": 1},
    }
    return {
        "status": "ok",
        "report": report.model_dump(mode="json"),
        "scorecard": scorecard.model_dump(mode="json"),
        "research_card": research_card.model_dump(mode="json"),
        "api_fixture": fixture["api_fixture"],
        "ui_fixture": fixture["ui_fixture"],
        "factor": factor,
        "forward": forward,
        "trials": trials,
        "portfolio_constraints": {
            "single_name_cap": "5%",
            "sector_cap": "25%",
            "turnover_cap": "20%",
            "adv_cap": "10%",
        },
    }
