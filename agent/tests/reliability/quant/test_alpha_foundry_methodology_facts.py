from __future__ import annotations

from datetime import datetime, timezone

from src.alpha_foundry.reports.builder import build_alpha_foundry_report, make_factor_candidate_card
from src.alpha_foundry.overfit.trial_ledger import TrialLedger, TrialRecord
from src.reliability.quant.methodology_facts import derive_alpha_foundry_methodology_facts
from tests.alpha_foundry.fixtures.factory import make_alpha_foundry_factor_card_kwargs


def _ledger() -> TrialLedger:
    ledger = TrialLedger.create(ledger_id="ledger-aaf", family_id="limit_liquidity")
    for suffix in ("a", "b"):
        ledger = ledger.append(
            TrialRecord(
                trial_id=f"trial-{suffix}",
                family_id="limit_liquidity",
                sub_family_id="limit_queue_pressure_proxy",
                hypothesis_id="limit_queue_pressure_proxy",
                factor_id="limit_queue_pressure_proxy",
                factor_definition_hash="hash-limit_queue_pressure_proxy",
                parameter_variant={"suffix": suffix},
                param_hash=f"param-{suffix}",
                started_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
                completed_at=datetime(2026, 1, 5, 1, tzinfo=timezone.utc),
                outcome="reported",
            )
        )
    return ledger


def test_methodology_facts_derive_trial_count_only_from_trial_ledger() -> None:
    card = make_factor_candidate_card(**make_alpha_foundry_factor_card_kwargs())
    report = build_alpha_foundry_report(
        report_id="aaf-report",
        protocol_hash="protocol-hash",
        cards=[card],
        trial_ledger_ref="not-a-count-source",
    )

    facts = derive_alpha_foundry_methodology_facts(
        report,
        trial_ledger=_ledger(),
        has_tradability_mask=True,
        uses_execution_return=True,
        has_multiple_testing_report=True,
        has_risk_model=True,
        risk_model_covariance_psd=True,
        has_forward_plan=True,
        forward_plan_frozen=True,
        has_benchmark=True,
    )

    assert facts.schema_version == "2.1.0"
    assert facts.has_factor_formula is True
    assert facts.has_trial_ledger is True
    assert facts.trial_count == 2
    assert facts.has_proxy_only_data is True
    assert facts.generated_from_artifacts == ["falsification-limit_queue_pressure_proxy"]


def test_methodology_facts_keep_execution_and_risk_evidence_explicit() -> None:
    card = make_factor_candidate_card(**make_alpha_foundry_factor_card_kwargs(proxy_note=None))
    report = build_alpha_foundry_report(
        report_id="aaf-report",
        protocol_hash="protocol-hash",
        cards=[card],
    )

    facts = derive_alpha_foundry_methodology_facts(
        report,
        has_tradability_mask=False,
        uses_execution_return=False,
        has_risk_model=True,
        risk_model_covariance_psd=False,
        has_forward_plan=True,
        forward_plan_frozen=False,
        has_benchmark=False,
    )

    assert facts.has_tradability_mask is False
    assert facts.uses_execution_return is False
    assert facts.has_risk_model is True
    assert facts.risk_model_covariance_psd is False
    assert facts.forward_plan_frozen is False
    assert facts.has_benchmark is False
