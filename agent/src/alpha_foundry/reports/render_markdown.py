"""Markdown rendering for Alpha Foundry reports."""

from __future__ import annotations

from html import escape

from src.alpha_foundry.reports.model import AlphaFoundryReport
from src.reliability.redaction import redact_secret_text


def render_alpha_foundry_report_markdown(report: AlphaFoundryReport) -> str:
    lines = [
        f"# Alpha Foundry Report: {_safe_text(report.report_id)}",
        "",
        f"Conclusion: {report.conclusion_level.value}",
        f"Protocol hash: {_safe_text(report.protocol_hash)}",
        f"Hard failures: {_format_failures(report.hard_failures)}",
        f"Trial ledger: {_safe_text(report.trial_ledger_ref or 'none')}",
        "",
        "## Factor Candidates",
    ]
    for card in report.factor_candidate_cards:
        lines.extend(
            [
                f"- Factor: {_safe_text(card.factor_id)}",
                f"  - factor_definition_hash: {_safe_text(card.factor_definition_hash)}",
                f"  - trial_count: {card.trial_count if card.trial_count is not None else 'unknown'}",
                f"  - hard_failures: {_format_failures(card.hard_failures)}",
                f"  - return track: {_return_track_text(card.uses_execution_return, card.has_close_return_diagnostics)}",
            ]
        )
        if card.proxy_note:
            lines.append(f"  - proxy_note: {_safe_text(card.proxy_note)}")
    return "\n".join(lines) + "\n"


def _format_failures(failures: list[object]) -> str:
    if not failures:
        return "none"
    return ", ".join(getattr(failure, "value", str(failure)) for failure in failures)


def _return_track_text(uses_execution_return: bool, has_close_return_diagnostics: bool) -> str:
    pieces: list[str] = []
    if uses_execution_return:
        pieces.append("execution_return used for tradable validation")
    else:
        pieces.append("execution_return missing for tradable validation")
    if has_close_return_diagnostics:
        pieces.append("close_return shown only as diagnostics")
    return "; ".join(pieces)


def _safe_text(value: object) -> str:
    return escape(redact_secret_text(str(value)), quote=False)
