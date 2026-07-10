"""Canonical expression and factor-spec identities plus their event entrypoint."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from src.alpha_foundry.dsl.canonical import (
    CanonicalAST,
    canonicalize_ast,
    thaw_canonical_ast,
)
from src.alpha_foundry.dsl.grammar import DEFAULT_GRAMMAR, GrammarDefinition
from src.alpha_foundry.dsl.model import ASTNode
from src.alpha_foundry.dsl.parser import FormulaParser
from src.alpha_foundry.dsl.validator import validate_expression
from src.alpha_quality.flags import ResolvedAGSFlags
from src.research_ledger.events import EventDraft, EventIdempotencyConflict, ResearchEventStore
from src.research_ledger.hash_utils import canonical_json_hash, utc_now_iso


_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class FormulaIdentityError(ValueError):
    """A deterministic parse/validation error safe to persist in the ledger."""

    def __init__(self, error_codes: list[str] | tuple[str, ...]) -> None:
        self.error_codes = tuple(sorted(set(error_codes)))
        super().__init__(", ".join(self.error_codes))


def _freeze_mapping(value: Mapping[str, str]) -> Mapping[str, str]:
    if not value or any(not isinstance(key, str) or not isinstance(item, str) or not item for key, item in value.items()):
        raise ValueError("field_semantics must be a non-empty string mapping")
    return MappingProxyType(dict(sorted(value.items())))


@dataclass(frozen=True)
class FactorSpecSemantics:
    """Timing, field and mask semantics that turn an expression into a factor."""

    transform_pipeline_hash: str
    field_semantics: Mapping[str, str]
    signal_time: str
    order_time: str
    entry_price_time: str
    execution_lag: int
    return_horizon: int
    universe_mask_hash: str
    tradability_mask_hash: str

    def __post_init__(self) -> None:
        for name in ("transform_pipeline_hash", "universe_mask_hash", "tradability_mask_hash"):
            if not _HASH_RE.fullmatch(str(getattr(self, name))):
                raise ValueError(f"{name} must be a sha256 content hash")
        object.__setattr__(self, "field_semantics", _freeze_mapping(self.field_semantics))
        for name in ("signal_time", "order_time", "entry_price_time"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.execution_lag, bool) or not isinstance(self.execution_lag, int) or self.execution_lag < 1:
            raise ValueError("execution_lag must be an integer of at least one")
        if isinstance(self.return_horizon, bool) or not isinstance(self.return_horizon, int) or self.return_horizon < 1:
            raise ValueError("return_horizon must be an integer of at least one")

    def to_dict(self) -> dict[str, Any]:
        return {
            "transform_pipeline_hash": self.transform_pipeline_hash,
            "field_semantics": dict(self.field_semantics),
            "signal_time": self.signal_time,
            "order_time": self.order_time,
            "entry_price_time": self.entry_price_time,
            "execution_lag": self.execution_lag,
            "return_horizon": self.return_horizon,
            "universe_mask_hash": self.universe_mask_hash,
            "tradability_mask_hash": self.tradability_mask_hash,
        }


@dataclass(frozen=True)
class ExpressionIdentity:
    expression_id: str
    canonical_ast_hash: str
    canonical_formula: str
    grammar_version: str
    grammar_hash: str
    canonical_ast: CanonicalAST
    raw_formula_hash: str


@dataclass(frozen=True)
class SignNormalizedIdentity:
    sign_normalized_id: str
    polarity: int


@dataclass(frozen=True)
class FactorSpecIdentity:
    factor_spec_id: str
    expression: ExpressionIdentity
    semantics: FactorSpecSemantics


@dataclass(frozen=True)
class FactorIdentityAttempt:
    status: str
    factor_spec_id: str | None
    expression_id: str | None
    error_codes: tuple[str, ...] = ()


def _parse_and_validate(formula: str, grammar: GrammarDefinition) -> ASTNode:
    try:
        ast = FormulaParser(grammar).parse(formula)
    except ValueError as exc:
        raise FormulaIdentityError(["INVALID_SYNTAX"]) from exc
    validation = validate_expression(ast, grammar=grammar)
    if not validation.ok:
        raise FormulaIdentityError(validation.errors)
    return ast


def build_expression_identity(
    formula: str,
    *,
    grammar: GrammarDefinition = DEFAULT_GRAMMAR,
) -> ExpressionIdentity:
    ast = _parse_and_validate(formula, grammar)
    canonical_ast = canonicalize_ast(ast, grammar=grammar)
    canonical_ast_hash = canonical_json_hash(thaw_canonical_ast(canonical_ast))
    expression_id = canonical_json_hash(
        {
            "canonical_ast": thaw_canonical_ast(canonical_ast),
            "grammar_version": grammar.semantic_version,
            "grammar_hash": grammar.content_hash,
        }
    )
    from src.alpha_foundry.dsl.canonical import render_canonical_ast

    return ExpressionIdentity(
        expression_id=expression_id,
        canonical_ast_hash=canonical_ast_hash,
        canonical_formula=render_canonical_ast(canonical_ast),
        grammar_version=grammar.semantic_version,
        grammar_hash=grammar.content_hash,
        canonical_ast=canonical_ast,
        raw_formula_hash=canonical_json_hash({"formula": formula}),
    )


def build_sign_normalized_identity(identity: ExpressionIdentity) -> SignNormalizedIdentity:
    root = identity.canonical_ast
    polarity = -1 if root.get("kind") == "call" and root.get("op") == "neg" else 1
    unsigned = root["args"][0] if polarity == -1 else root
    return SignNormalizedIdentity(
        sign_normalized_id=canonical_json_hash(
            {
                "canonical_ast": thaw_canonical_ast(unsigned),
                "grammar_version": identity.grammar_version,
                "grammar_hash": identity.grammar_hash,
            }
        ),
        polarity=polarity,
    )


def build_factor_spec_identity(
    formula: str,
    semantics: FactorSpecSemantics,
    *,
    grammar: GrammarDefinition = DEFAULT_GRAMMAR,
) -> FactorSpecIdentity:
    expression = build_expression_identity(formula, grammar=grammar)
    factor_spec_id = canonical_json_hash(
        {"expression_id": expression.expression_id, "semantics": semantics.to_dict()}
    )
    return FactorSpecIdentity(
        factor_spec_id=factor_spec_id,
        expression=expression,
        semantics=semantics,
    )


class FactorIdentityService:
    """Append canonical definition attempts to the existing typed event spine.

    A valid definition deliberately remains an open trial until the later
    evaluation milestone records its terminal train/valid outcome.  Invalid
    and duplicate attempts are closed immediately with typed non-promoting
    terminal events.
    """

    def __init__(self, *, store: ResearchEventStore, flags: ResolvedAGSFlags) -> None:
        if not flags.enabled("VIBE_TRADING_ALPHA_FOUNDRY") or not flags.enabled("VIBE_TRADING_FACTOR_DAG"):
            raise RuntimeError("canonical factor identity capability is disabled")
        self.store = store
        self.flags = flags

    def record_attempt(
        self,
        *,
        trial_id: str,
        run_id: str,
        candidate_id: str,
        formula: str,
        semantics: FactorSpecSemantics,
        grammar: GrammarDefinition = DEFAULT_GRAMMAR,
    ) -> FactorIdentityAttempt:
        try:
            identity = build_factor_spec_identity(formula, semantics, grammar=grammar)
        except FormulaIdentityError as exc:
            existing = self._existing_terminal(trial_id, candidate_id)
            if existing is not None:
                return FactorIdentityAttempt(existing, None, None, exc.error_codes)
            self._append_trial_started(trial_id, run_id, candidate_id)
            self._append_invalid_terminal(trial_id, run_id, exc.error_codes)
            return FactorIdentityAttempt("invalid", None, None, exc.error_codes)

        existing_status = self._existing_terminal(trial_id, candidate_id)
        if existing_status is not None:
            return FactorIdentityAttempt(existing_status, identity.factor_spec_id, identity.expression.expression_id)
        existing_definition_for_trial = self.store.query_events(
            event_type="FactorDefinitionRecorded", entity_id=identity.factor_spec_id
        )
        if existing_definition_for_trial and str(
            existing_definition_for_trial[0].payload["metadata"].get("originating_trial_id", "")
        ) == trial_id:
            return FactorIdentityAttempt("recorded", identity.factor_spec_id, identity.expression.expression_id)

        self._append_trial_started(trial_id, run_id, candidate_id)

        existing = self.store.query_events(
            event_type="FactorDefinitionRecorded", entity_id=identity.factor_spec_id
        )
        if existing:
            origin = str(existing[0].payload["metadata"].get("originating_trial_id", ""))
            if origin == trial_id:
                return FactorIdentityAttempt("recorded", identity.factor_spec_id, identity.expression.expression_id)
            self._append_duplicate_terminal(trial_id, run_id)
            return FactorIdentityAttempt("duplicate", identity.factor_spec_id, identity.expression.expression_id)

        try:
            self.store.append_event(
                EventDraft(
                    event_type="FactorDefinitionRecorded",
                    entity_id=identity.factor_spec_id,
                    run_id=run_id,
                    payload_schema_version="factor_definition_recorded.v1",
                    idempotency_key=f"factor-definition:{identity.factor_spec_id}",
                    payload={
                        "factor_spec_id": identity.factor_spec_id,
                        "expression_id": identity.expression.expression_id,
                        "canonical_ast_hash": identity.expression.canonical_ast_hash,
                        "grammar_version": identity.expression.grammar_version,
                        "grammar_hash": identity.expression.grammar_hash,
                        "metadata": {
                            "originating_trial_id": trial_id,
                            "canonical_ast": thaw_canonical_ast(identity.expression.canonical_ast),
                            "canonical_formula": identity.expression.canonical_formula,
                            "semantics": identity.semantics.to_dict(),
                        },
                        "artifact_refs": [],
                    },
                )
            )
        except EventIdempotencyConflict:
            # A competing writer won the same content identity.  It is a real
            # duplicate, not an error or a second DAG node.
            self._append_duplicate_terminal(trial_id, run_id)
            return FactorIdentityAttempt("duplicate", identity.factor_spec_id, identity.expression.expression_id)
        return FactorIdentityAttempt("recorded", identity.factor_spec_id, identity.expression.expression_id)

    def _existing_terminal(self, trial_id: str, candidate_id: str) -> str | None:
        """Return the existing terminal status for an exact idempotent retry.

        We inspect the immutable start payload before treating a reused trial ID
        as a retry, so a caller cannot use idempotency to change a trial's
        candidate identity.
        """
        starts = self.store.query_events(event_type="TrialStarted", entity_id=trial_id)
        if not starts:
            return None
        if str(starts[0].payload["candidate_id"]) != candidate_id:
            raise ValueError("trial_id is already bound to another candidate_id")
        terminals = self.store.query_events(event_type="TrialTerminated", entity_id=trial_id)
        if terminals:
            return str(terminals[0].payload["status"])
        return None

    def _append_trial_started(self, trial_id: str, run_id: str, candidate_id: str) -> None:
        self.store.append_event(
            EventDraft(
                event_type="TrialStarted",
                entity_id=trial_id,
                run_id=run_id,
                payload_schema_version="trial_started.v1",
                idempotency_key=f"trial-start:{trial_id}",
                payload={
                    "trial_id": trial_id,
                    "candidate_id": candidate_id,
                    "data_scope": "train_valid",
                    "objective": "canonical_factor_definition",
                    "started_at": utc_now_iso(),
                },
            )
        )

    def _append_invalid_terminal(self, trial_id: str, run_id: str, codes: tuple[str, ...]) -> None:
        failure_code = codes[0] if codes else "INVALID_FORMULA"
        self.store.append_event(
            EventDraft(
                event_type="GenerationFailureRecorded", entity_id=trial_id, run_id=run_id,
                payload_schema_version="generation_failure_recorded.v1",
                idempotency_key=f"generation-failure:{trial_id}",
                payload={"trial_id": trial_id, "failure_code": failure_code, "failure_kind": "invalid", "message": "formula failed deterministic validation", "occurred_at": utc_now_iso()},
            )
        )
        self.store.append_event(
            EventDraft(
                event_type="TrialTerminated", entity_id=trial_id, run_id=run_id,
                payload_schema_version="trial_terminated.v1", idempotency_key=f"trial-terminal:{trial_id}",
                payload={"trial_id": trial_id, "status": "invalid", "reason_codes": list(codes) or ["INVALID_FORMULA"], "decision": "reject", "evaluation_event_hash": None, "terminated_at": utc_now_iso()},
            )
        )

    def _append_duplicate_terminal(self, trial_id: str, run_id: str) -> None:
        self.store.append_event(
            EventDraft(
                event_type="TrialTerminated", entity_id=trial_id, run_id=run_id,
                payload_schema_version="trial_terminated.v1", idempotency_key=f"trial-terminal:{trial_id}",
                payload={"trial_id": trial_id, "status": "duplicate", "reason_codes": ["CANONICAL_DUPLICATE"], "decision": "reject", "evaluation_event_hash": None, "terminated_at": utc_now_iso()},
            )
        )


__all__ = [
    "ExpressionIdentity", "FactorIdentityAttempt", "FactorIdentityService",
    "FactorSpecIdentity", "FactorSpecSemantics", "FormulaIdentityError",
    "SignNormalizedIdentity", "build_expression_identity", "build_factor_spec_identity",
    "build_sign_normalized_identity",
]
