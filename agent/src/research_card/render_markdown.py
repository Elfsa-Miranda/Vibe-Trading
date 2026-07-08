"""Markdown rendering for Alpha Foundry Research Cards."""

from __future__ import annotations

from html import escape

from src.research_card.builder import AlphaFoundryResearchCard
from src.reliability.redaction import redact_secret_text


def render_alpha_foundry_research_card_markdown(card: AlphaFoundryResearchCard) -> str:
    lines = [
        f"# Alpha Foundry Research Card: {_safe_text(card.card_id)}",
        "",
        f"Conclusion: {card.conclusion_level.value}",
        f"Hard failures: {_format_failures(card.hard_failures)}",
        f"Trial count: {card.trial_count if card.trial_count is not None else 'unknown'}",
        f"Factor definition hashes: {_safe_text(', '.join(card.factor_definition_hashes) or 'none')}",
        f"Return validation: {_return_track_text(card.uses_execution_return, card.has_close_return_diagnostics)}",
    ]
    if card.proxy_notes:
        lines.append("")
        lines.append("## Proxy Notes")
        lines.extend(f"- {_safe_text(note)}" for note in card.proxy_notes)
    if card.warnings:
        lines.append("")
        lines.append("## Warnings")
        lines.extend(f"- {_safe_text(warning)}" for warning in card.warnings)
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
