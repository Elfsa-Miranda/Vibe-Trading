"""SQLite WAL-backed append-only typed research-event store."""

from __future__ import annotations

import json
import random
import sqlite3
import time
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Mapping
from uuid import UUID, uuid4

from src.alpha_quality.flags import AGS_FLAG_DEFAULTS, ResolvedAGSFlags
from src.research_ledger.events.artifacts import (
    hash_artifact,
    validate_artifact_references,
)
from src.research_ledger.events.model import (
    EventDraft,
    EventIdempotencyConflict,
    EventMutationError,
    EventTransitionError,
    EventValidationError,
    LifecycleSummary,
    ReplayState,
    ResearchEventAppendError,
    ResearchEventEnvelope,
)
from src.research_ledger.events.payloads import (
    envelope_diagnostics,
    validate_and_redact_payload,
)
from src.research_ledger.events.replay import build_replay_state
from src.research_ledger.hash_utils import (
    canonical_json,
    canonical_json_hash,
    redact_secrets,
    utc_now_iso,
)


DurabilityProfile = Literal["authoritative", "balanced"]


class ResearchEventStore:
    """Additive event table sharing the existing research-ledger database."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        artifact_root: str | Path,
        flags: ResolvedAGSFlags,
        code_version: str,
        durability_profile: DurabilityProfile = "authoritative",
        busy_timeout_ms: int = 30_000,
        max_retries: int = 12,
    ) -> None:
        if not flags.enabled("VIBE_TRADING_RESEARCH_EVENTS"):
            raise RuntimeError("research events capability is disabled")
        if durability_profile not in {"authoritative", "balanced"}:
            raise ValueError("unknown research-event durability profile")
        if not code_version.strip():
            raise ValueError("code_version is required")
        self._reject_secret_or_path(code_version, "code_version")
        if busy_timeout_ms <= 0 or max_retries <= 0:
            raise ValueError("busy timeout and retry count must be positive")

        self.db_path = Path(db_path)
        self.artifact_root = Path(artifact_root)
        self.flags = flags
        self.code_version = code_version
        self.durability_profile = durability_profile
        self.busy_timeout_ms = int(busy_timeout_ms)
        self.max_retries = int(max_retries)
        self.synchronous_mode = "FULL" if durability_profile == "authoritative" else "NORMAL"
        self.decision_cap = None if durability_profile == "authoritative" else "research_only"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root = self.artifact_root.resolve(strict=True)
        self._initialize_schema()

    @staticmethod
    def hash_artifact(path: str | Path) -> str:
        return hash_artifact(path)

    def durability_diagnostics(self) -> dict[str, str | int]:
        with self._connect() as conn:
            journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).upper()
            synchronous_value = int(conn.execute("PRAGMA synchronous").fetchone()[0])
            busy_timeout = int(conn.execute("PRAGMA busy_timeout").fetchone()[0])
        synchronous = {0: "OFF", 1: "NORMAL", 2: "FULL", 3: "EXTRA"}.get(
            synchronous_value,
            f"UNKNOWN:{synchronous_value}",
        )
        return {
            "journal_mode": journal_mode,
            "synchronous": synchronous,
            "busy_timeout_ms": busy_timeout,
        }

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=self.busy_timeout_ms / 1000.0,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA synchronous={self.synchronous_mode}")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize_schema(self) -> None:
        last_error: sqlite3.OperationalError | None = None
        for attempt in range(self.max_retries):
            try:
                self._initialize_schema_once()
                return
            except sqlite3.OperationalError as exc:
                last_error = exc
                if not self._is_retryable_lock(exc) or attempt + 1 >= self.max_retries:
                    raise ResearchEventAppendError(
                        f"research-event schema initialization failed: {exc}"
                    ) from exc
                self._retry_delay(attempt)
        raise ResearchEventAppendError(
            f"research-event schema initialization failed after retries: {last_error}"
        )

    def _initialize_schema_once(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    schema_version TEXT NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    payload_schema_version TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    idempotency_key TEXT,
                    previous_event_hash TEXT,
                    event_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    code_version TEXT NOT NULL,
                    feature_flags TEXT NOT NULL,
                    warnings TEXT NOT NULL,
                    hard_failures TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_research_events_idempotency
                    ON research_events(idempotency_key)
                    WHERE idempotency_key IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_research_events_entity
                    ON research_events(entity_id, seq);
                CREATE INDEX IF NOT EXISTS idx_research_events_type
                    ON research_events(event_type, seq);
                CREATE TRIGGER IF NOT EXISTS research_events_no_update
                BEFORE UPDATE ON research_events
                BEGIN
                    SELECT RAISE(ABORT, 'research_events is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS research_events_no_delete
                BEFORE DELETE ON research_events
                BEGIN
                    SELECT RAISE(ABORT, 'research_events is append-only');
                END;
                """
            )
            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(research_events)").fetchall()
            }
            expected = {
                "seq",
                "schema_version",
                "event_id",
                "event_type",
                "entity_id",
                "run_id",
                "payload_schema_version",
                "payload",
                "payload_hash",
                "idempotency_key",
                "previous_event_hash",
                "event_hash",
                "created_at",
                "code_version",
                "feature_flags",
                "warnings",
                "hard_failures",
            }
            if columns != expected:
                raise ResearchEventAppendError(
                    "incompatible research_events schema; additive migration required"
                )

    def append_event(self, draft: EventDraft) -> ResearchEventEnvelope:
        self._validate_draft_identity(draft)
        payload = validate_and_redact_payload(
            draft.event_type,
            draft.payload_schema_version,
            draft.payload,
        )
        self._validate_payload_entity(draft, payload)
        self._validate_artifacts(payload)
        payload_hash = canonical_json_hash(payload)
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            conn: sqlite3.Connection | None = None
            try:
                conn = self._connect()
                conn.execute("BEGIN IMMEDIATE")
                existing = self._idempotent_event(conn, draft, payload, payload_hash)
                if existing is not None:
                    conn.execute("COMMIT")
                    return existing
                self._validate_transition(conn, draft, payload)
                previous_event_hash = self._tail_hash(conn)
                event = self._build_event(
                    draft,
                    payload,
                    payload_hash=payload_hash,
                    previous_event_hash=previous_event_hash,
                )
                self._insert_event(conn, event, canonical_json(payload))
                conn.execute("COMMIT")
                return event
            except sqlite3.OperationalError as exc:
                if conn is not None:
                    self._rollback_quietly(conn)
                last_error = exc
                if not self._is_retryable_lock(exc) or attempt + 1 >= self.max_retries:
                    raise ResearchEventAppendError(str(exc)) from exc
                self._retry_delay(attempt)
            except (EventIdempotencyConflict, EventTransitionError, EventValidationError):
                if conn is not None:
                    self._rollback_quietly(conn)
                raise
            except sqlite3.IntegrityError as exc:
                if conn is not None:
                    self._rollback_quietly(conn)
                raise ResearchEventAppendError(str(exc)) from exc
            except Exception as exc:
                if conn is not None:
                    self._rollback_quietly(conn)
                raise ResearchEventAppendError(str(exc)) from exc
            finally:
                if conn is not None:
                    conn.close()
        raise ResearchEventAppendError(f"append failed after retries: {last_error}")

    def _build_event(
        self,
        draft: EventDraft,
        payload: Mapping[str, Any],
        *,
        payload_hash: str,
        previous_event_hash: str | None,
    ) -> ResearchEventEnvelope:
        warnings, hard_failures = envelope_diagnostics(
            draft.event_type,
            payload,
            reduced_durability=self.durability_profile == "balanced",
        )
        without_hash = {
            "schema_version": "research_event.v1",
            "event_id": str(uuid4()),
            "event_type": draft.event_type,
            "entity_id": draft.entity_id,
            "run_id": draft.run_id,
            "payload_schema_version": draft.payload_schema_version,
            "payload": dict(payload),
            "payload_hash": payload_hash,
            "idempotency_key": draft.idempotency_key,
            "previous_event_hash": previous_event_hash,
            "created_at": utc_now_iso(),
            "code_version": self.code_version,
            "feature_flags": self.flags.as_dict(),
            "warnings": list(warnings),
            "hard_failures": list(hard_failures),
        }
        event_hash = canonical_json_hash(without_hash)
        return ResearchEventEnvelope.from_dict({**without_hash, "event_hash": event_hash})

    def _insert_event(
        self,
        conn: sqlite3.Connection,
        event: ResearchEventEnvelope,
        payload_json: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO research_events (
                schema_version, event_id, event_type, entity_id, run_id,
                payload_schema_version, payload, payload_hash,
                idempotency_key, previous_event_hash, event_hash,
                created_at, code_version, feature_flags, warnings, hard_failures
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.schema_version,
                event.event_id,
                event.event_type,
                event.entity_id,
                event.run_id,
                event.payload_schema_version,
                payload_json,
                event.payload_hash,
                event.idempotency_key,
                event.previous_event_hash,
                event.event_hash,
                event.created_at,
                event.code_version,
                canonical_json(dict(event.feature_flags)),
                canonical_json(list(event.warnings)),
                canonical_json(list(event.hard_failures)),
            ),
        )

    def _idempotent_event(
        self,
        conn: sqlite3.Connection,
        draft: EventDraft,
        payload: Mapping[str, Any],
        payload_hash: str,
    ) -> ResearchEventEnvelope | None:
        if draft.idempotency_key is None:
            return None
        row = conn.execute(
            "SELECT * FROM research_events WHERE idempotency_key = ?",
            (draft.idempotency_key,),
        ).fetchone()
        if row is None:
            return None
        existing = self._row_to_event(row)
        requested_warnings, requested_hard_failures = envelope_diagnostics(
            draft.event_type,
            payload,
            reduced_durability=self.durability_profile == "balanced",
        )
        business_identity = (
            existing.event_type,
            existing.entity_id,
            existing.run_id,
            existing.payload_schema_version,
            existing.payload_hash,
            existing.code_version,
            dict(existing.feature_flags),
            existing.warnings,
            existing.hard_failures,
        )
        requested_identity = (
            draft.event_type,
            draft.entity_id,
            draft.run_id,
            draft.payload_schema_version,
            payload_hash,
            self.code_version,
            self.flags.as_dict(),
            requested_warnings,
            requested_hard_failures,
        )
        if business_identity != requested_identity:
            raise EventIdempotencyConflict(
                f"idempotency key conflicts with existing event: {draft.idempotency_key}"
            )
        return existing

    def _validate_draft_identity(self, draft: EventDraft) -> None:
        for name, value in (("entity_id", draft.entity_id), ("run_id", draft.run_id)):
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise EventValidationError(f"{name} must be a non-empty bounded string")
            if any(ord(char) < 32 for char in value):
                raise EventValidationError(f"{name} contains control characters")
            self._reject_secret_or_path(value, name)
        if draft.idempotency_key is not None:
            if not draft.idempotency_key.strip() or len(draft.idempotency_key) > 512:
                raise EventValidationError("idempotency_key must be a bounded non-empty string")
            self._reject_secret_or_path(draft.idempotency_key, "idempotency_key")

    @staticmethod
    def _reject_secret_or_path(value: str, name: str) -> None:
        if redact_secrets(value) != value or PurePosixPath(value).is_absolute():
            raise EventValidationError(f"{name} contains secret or local path")

    @staticmethod
    def _validate_payload_entity(draft: EventDraft, payload: Mapping[str, Any]) -> None:
        identity_fields = {
            "TrialStarted": "trial_id",
            "FactorDefinitionRecorded": "factor_spec_id",
            "RegistryBootstrapRecorded": "snapshot_id",
            "DerivationRecorded": "child_factor_spec_id",
            "ProcessActionFrozen": "action_id",
            "ProcessOutcomeRecorded": "outcome_id",
            "GenerationFailureRecorded": "trial_id",
            "EvaluationRecorded": "evaluation_id",
            "TrialTerminated": "trial_id",
            "RetrieverDecisionRecorded": "decision_id",
            "FalsificationContractRegistered": "contract_id",
            "FalsificationResultRecorded": "result_id",
            "QualityDecisionRecorded": "decision_id",
            "ForwardPlanRecorded": "plan_id",
            "ForwardObservationRecorded": "observation_id",
        }
        field = identity_fields[draft.event_type]
        if draft.entity_id != payload[field]:
            raise EventValidationError(
                f"entity_id must equal payload {field} for {draft.event_type}"
            )

    def _validate_artifacts(self, payload: dict[str, Any]) -> None:
        references = payload.get("artifact_refs")
        if references is None:
            return
        payload["artifact_refs"] = validate_artifact_references(
            self.artifact_root,
            references,
        )

    def _validate_transition(
        self,
        conn: sqlite3.Connection,
        draft: EventDraft,
        payload: Mapping[str, Any],
    ) -> None:
        event_type = draft.event_type
        if event_type == "DerivationRecorded":
            terminal = conn.execute(
                """
                SELECT 1 FROM research_events
                WHERE event_type = 'TrialTerminated' AND event_hash = ?
                """,
                (payload["trial_terminal_event_hash"],),
            ).fetchone()
            if terminal is None:
                raise EventTransitionError("derivation references no prior terminal trial event")
            child = str(payload["child_factor_spec_id"])
            parents = [str(parent) for parent in payload["parent_factor_spec_ids"]]
            if child in parents:
                raise EventTransitionError("derivation cannot contain a self-edge")
            if len(parents) != len(set(parents)):
                raise EventTransitionError("derivation cannot contain duplicate parents")
            definition_ids = {child, *parents}
            known_definitions = {
                factor_id
                for factor_id in definition_ids
                if conn.execute(
                    """
                    SELECT 1 FROM research_events
                    WHERE event_type = 'FactorDefinitionRecorded' AND entity_id = ?
                    """,
                    (factor_id,),
                ).fetchone()
                is not None
            }
            if known_definitions != definition_ids:
                raise EventTransitionError("derivation references no prior factor definition")
            prior_rows = conn.execute(
                "SELECT payload FROM research_events WHERE event_type = 'DerivationRecorded' ORDER BY seq ASC"
            ).fetchall()
            graph: dict[str, set[str]] = {}
            for row in prior_rows:
                prior = json.loads(str(row["payload"]))
                prior_child = str(prior["child_factor_spec_id"])
                if prior_child == child:
                    raise EventTransitionError("multiple lineage derivations for one child are ambiguous")
                for parent in prior["parent_factor_spec_ids"]:
                    graph.setdefault(str(parent), set()).add(prior_child)
            if any(self._graph_has_path(graph, child, parent) for parent in parents):
                raise EventTransitionError("derivation creates a lineage cycle")
            return
        if event_type == "ProcessActionFrozen":
            started = conn.execute(
                "SELECT 1 FROM research_events WHERE event_type = 'TrialStarted' AND entity_id = ?",
                (payload["trial_id"],),
            ).fetchone()
            if started is None:
                raise EventTransitionError("process action references no prior trial start")
            return
        if event_type == "ProcessOutcomeRecorded":
            action = conn.execute(
                "SELECT payload FROM research_events WHERE event_type = 'ProcessActionFrozen' AND entity_id = ?",
                (payload["action_id"],),
            ).fetchone()
            terminal = conn.execute(
                "SELECT payload FROM research_events WHERE event_type = 'TrialTerminated' AND event_hash = ?",
                (payload["terminal_event_hash"],),
            ).fetchone()
            if action is None or terminal is None:
                raise EventTransitionError("process outcome lacks prior action or terminal evidence")
            if json.loads(action["payload"])["trial_id"] != payload["trial_id"]:
                raise EventTransitionError("process outcome trial does not match frozen action")
            if json.loads(terminal["payload"])["trial_id"] != payload["trial_id"]:
                raise EventTransitionError("process outcome trial does not match terminal evidence")
            if payload["child_factor_spec_id"] is None and payload["ast_diff"] is not None:
                raise EventValidationError("invalid process outcome cannot carry an AST diff")
            return
        if event_type == "FalsificationResultRecorded":
            contract = conn.execute(
                """
                SELECT payload FROM research_events
                WHERE event_type = 'FalsificationContractRegistered' AND entity_id = ?
                ORDER BY seq DESC LIMIT 1
                """,
                (payload["contract_id"],),
            ).fetchone()
            if contract is None or json.loads(contract["payload"])["contract_hash"] != payload["contract_hash"]:
                raise EventTransitionError("falsification result has no matching prior contract")
            return
        if event_type == "ForwardObservationRecorded":
            plan = conn.execute(
                """
                SELECT 1 FROM research_events
                WHERE event_type = 'ForwardPlanRecorded' AND entity_id = ?
                """,
                (payload["plan_id"],),
            ).fetchone()
            if plan is None:
                raise EventTransitionError("forward observation has no prior plan")
            return
        if event_type not in {"TrialStarted", "EvaluationRecorded", "TrialTerminated"}:
            return
        trial_id = str(payload["trial_id"])
        if event_type in {"TrialStarted", "TrialTerminated"} and draft.entity_id != trial_id:
            raise EventValidationError("trial entity_id must equal payload trial_id")
        started = conn.execute(
            "SELECT event_hash FROM research_events WHERE event_type = 'TrialStarted' AND entity_id = ?",
            (trial_id,),
        ).fetchone()
        terminal = conn.execute(
            "SELECT event_hash FROM research_events WHERE event_type = 'TrialTerminated' AND entity_id = ?",
            (trial_id,),
        ).fetchone()
        if event_type == "TrialStarted":
            if started is not None:
                raise EventTransitionError(f"trial already started: {trial_id}")
            if terminal is not None:
                raise EventTransitionError(f"trial already terminated: {trial_id}")
            return
        if started is None:
            raise EventTransitionError(f"trial was not started: {trial_id}")
        if terminal is not None:
            raise EventTransitionError(f"trial already terminated: {trial_id}")
        if event_type == "TrialTerminated" and payload["status"] == "success":
            evaluation_hash = payload["evaluation_event_hash"]
            if evaluation_hash is None:
                raise EventTransitionError("successful trial requires terminal evaluation evidence")
            evaluation = conn.execute(
                """
                SELECT payload FROM research_events
                WHERE event_type = 'EvaluationRecorded' AND event_hash = ?
                """,
                (evaluation_hash,),
            ).fetchone()
            if evaluation is None or json.loads(evaluation["payload"])["trial_id"] != trial_id:
                raise EventTransitionError("successful trial evaluation evidence is missing or mismatched")

    def _tail_hash(self, conn: sqlite3.Connection) -> str | None:
        row = conn.execute(
            "SELECT event_hash FROM research_events ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return None if row is None else str(row["event_hash"])

    @staticmethod
    def _rollback_quietly(conn: sqlite3.Connection) -> None:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass

    @staticmethod
    def _is_retryable_lock(exc: sqlite3.OperationalError) -> bool:
        message = str(exc).lower()
        return "locked" in message or "busy" in message

    @staticmethod
    def _retry_delay(attempt: int) -> None:
        ceiling = min(0.5, 0.005 * (2**attempt))
        time.sleep(ceiling + random.uniform(0.0, ceiling / 4.0))

    def query_events(
        self,
        *,
        event_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[ResearchEventEnvelope]:
        clauses: list[str] = []
        params: list[str] = []
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        if entity_id is not None:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        sql = "SELECT * FROM research_events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY seq ASC"
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [self._row_to_event(row) for row in rows]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> ResearchEventEnvelope:
        return ResearchEventEnvelope(
            schema_version=str(row["schema_version"]),
            event_id=str(row["event_id"]),
            event_type=str(row["event_type"]),
            entity_id=str(row["entity_id"]),
            run_id=str(row["run_id"]),
            payload_schema_version=str(row["payload_schema_version"]),
            payload=json.loads(row["payload"]),
            payload_hash=str(row["payload_hash"]),
            idempotency_key=(
                None if row["idempotency_key"] is None else str(row["idempotency_key"])
            ),
            previous_event_hash=(
                None if row["previous_event_hash"] is None else str(row["previous_event_hash"])
            ),
            event_hash=str(row["event_hash"]),
            created_at=str(row["created_at"]),
            code_version=str(row["code_version"]),
            feature_flags=json.loads(row["feature_flags"]),
            warnings=tuple(json.loads(row["warnings"])),
            hard_failures=tuple(json.loads(row["hard_failures"])),
        )

    def verify_chain(self) -> bool:
        try:
            events = self.query_events()
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return False
        return self._verify_events(events)

    def _verify_events(self, events: list[ResearchEventEnvelope]) -> bool:
        previous: str | None = None
        for event in events:
            try:
                if event.schema_version != "research_event.v1":
                    return False
                if UUID(event.event_id).version != 4:
                    return False
                created_at = event.created_at[:-1] + "+00:00" if event.created_at.endswith("Z") else event.created_at
                if datetime.fromisoformat(created_at).tzinfo is None:
                    return False
                if event.previous_event_hash != previous:
                    return False
                event_dict = event.to_dict()
                validated_payload = validate_and_redact_payload(
                    event.event_type,
                    event.payload_schema_version,
                    event_dict["payload"],
                )
                self._validate_artifacts(validated_payload)
                if validated_payload != event_dict["payload"]:
                    return False
                self._validate_draft_identity(
                    EventDraft(
                        event_type=event.event_type,
                        entity_id=event.entity_id,
                        run_id=event.run_id,
                        payload_schema_version=event.payload_schema_version,
                        payload=validated_payload,
                        idempotency_key=event.idempotency_key,
                    )
                )
                self._validate_payload_entity(
                    EventDraft(
                        event_type=event.event_type,
                        entity_id=event.entity_id,
                        run_id=event.run_id,
                        payload_schema_version=event.payload_schema_version,
                        payload=validated_payload,
                        idempotency_key=event.idempotency_key,
                    ),
                    validated_payload,
                )
                stored_flags = dict(event.feature_flags)
                if set(stored_flags) != set(AGS_FLAG_DEFAULTS):
                    return False
                if any(not isinstance(value, bool) for value in stored_flags.values()):
                    return False
                if not stored_flags["VIBE_TRADING_AGS_ENABLED"] and any(
                    value
                    for name, value in stored_flags.items()
                    if name != "VIBE_TRADING_AGS_ENABLED"
                ):
                    return False
                if not stored_flags["VIBE_TRADING_RESEARCH_EVENTS"]:
                    return False
                self._reject_secret_or_path(event.code_version, "code_version")
                expected_warnings, expected_hard_failures = envelope_diagnostics(
                    event.event_type,
                    validated_payload,
                    reduced_durability="REDUCED_DURABILITY" in event.warnings,
                )
                if event.warnings != expected_warnings or event.hard_failures != expected_hard_failures:
                    return False
                if canonical_json_hash(validated_payload) != event.payload_hash:
                    return False
                without_hash = event_dict
                without_hash.pop("event_hash")
                if canonical_json_hash(without_hash) != event.event_hash:
                    return False
            except (EventValidationError, ValueError, TypeError, KeyError, AttributeError):
                return False
            previous = event.event_hash
        return self._verify_references_and_lifecycle(events)

    @staticmethod
    def _verify_references_and_lifecycle(events: list[ResearchEventEnvelope]) -> bool:
        started: set[str] = set()
        terminated: set[str] = set()
        evaluations: dict[str, str] = {}
        terminal_hashes: set[str] = set()
        contracts: dict[str, str] = {}
        plans: set[str] = set()
        for event in events:
            payload = event.payload
            if event.event_type == "TrialStarted":
                trial_id = str(payload["trial_id"])
                if trial_id in started or trial_id in terminated:
                    return False
                started.add(trial_id)
            elif event.event_type == "EvaluationRecorded":
                trial_id = str(payload["trial_id"])
                if trial_id not in started or trial_id in terminated:
                    return False
                evaluations[event.event_hash] = trial_id
            elif event.event_type == "TrialTerminated":
                trial_id = str(payload["trial_id"])
                if trial_id not in started or trial_id in terminated:
                    return False
                if payload["status"] == "success":
                    evaluation_hash = payload["evaluation_event_hash"]
                    if evaluations.get(str(evaluation_hash)) != trial_id:
                        return False
                terminated.add(trial_id)
                terminal_hashes.add(event.event_hash)
            elif event.event_type == "DerivationRecorded":
                if payload["trial_terminal_event_hash"] not in terminal_hashes:
                    return False
            elif event.event_type == "FalsificationContractRegistered":
                contracts[str(payload["contract_id"])] = str(payload["contract_hash"])
            elif event.event_type == "FalsificationResultRecorded":
                if contracts.get(str(payload["contract_id"])) != payload["contract_hash"]:
                    return False
            elif event.event_type == "ForwardPlanRecorded":
                plans.add(str(payload["plan_id"]))
            elif event.event_type == "ForwardObservationRecorded":
                if str(payload["plan_id"]) not in plans:
                    return False
        return True

    @staticmethod
    def _graph_has_path(graph: Mapping[str, set[str]], start: str, target: str) -> bool:
        pending = [start]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current in seen:
                continue
            seen.add(current)
            pending.extend(graph.get(current, ()))
        return False

    def replay(self) -> ReplayState:
        try:
            events = self.query_events()
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ResearchEventAppendError("replay verification failed: unreadable event") from exc
        if not self._verify_events(events):
            raise ResearchEventAppendError("replay verification failed: invalid event chain")
        return build_replay_state(events)

    def lifecycle_summary(self) -> LifecycleSummary:
        events = self.query_events()
        started = {
            str(event.payload["trial_id"])
            for event in events
            if event.event_type == "TrialStarted"
        }
        terminal_by_trial = {
            str(event.payload["trial_id"]): str(event.payload["status"])
            for event in events
            if event.event_type == "TrialTerminated"
        }
        return LifecycleSummary(
            started_count=len(started),
            terminal_count=len(terminal_by_trial),
            open_trial_ids=tuple(sorted(started - set(terminal_by_trial))),
            terminal_status_counts=tuple(sorted(Counter(terminal_by_trial.values()).items())),
        )

    def update(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
        raise EventMutationError("research events are append-only")

    def delete(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
        raise EventMutationError("research events are append-only")


__all__ = ["DurabilityProfile", "ResearchEventStore"]
