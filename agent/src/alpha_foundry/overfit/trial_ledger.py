"""Append-only TrialLedger stub for Alpha Foundry."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.alpha_foundry.common.hashing import canonical_hash


class AppendOnlyLedgerError(ValueError):
    """Raised when an append-only TrialLedger rule is violated."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TrialRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    trial_id: str
    family_id: str
    sub_family_id: str | None = None
    hypothesis_id: str
    factor_id: str
    factor_definition_hash: str
    parameter_variant: dict[str, Any]
    param_hash: str
    started_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
    outcome: Literal["reported", "selected", "rejected", "abandoned"]
    rejection_reason: str | None = None
    scorecard_ref: str | None = None
    report_ref: str | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def _datetime_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)


def _ledger_hash_payload(
    *,
    ledger_id: str,
    family_id: str,
    records: tuple[TrialRecord, ...],
    append_only: bool,
) -> dict[str, Any]:
    return {
        "ledger_id": ledger_id,
        "family_id": family_id,
        "records": [record.model_dump(mode="json") for record in records],
        "append_only": append_only,
    }


class TrialLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "2.1.0"
    ledger_id: str
    family_id: str
    records: tuple[TrialRecord, ...] = Field(default_factory=tuple)
    append_only: bool = True
    ledger_hash: str

    @classmethod
    def create(cls, *, ledger_id: str, family_id: str) -> "TrialLedger":
        records: tuple[TrialRecord, ...] = ()
        ledger_hash = canonical_hash(
            _ledger_hash_payload(
                ledger_id=ledger_id,
                family_id=family_id,
                records=records,
                append_only=True,
            )
        )
        return cls(
            ledger_id=ledger_id,
            family_id=family_id,
            records=records,
            append_only=True,
            ledger_hash=ledger_hash,
        )

    def append(self, record: TrialRecord) -> "TrialLedger":
        if not self.append_only:
            raise AppendOnlyLedgerError("ledger is not append-only")
        if record.family_id != self.family_id:
            raise AppendOnlyLedgerError(
                f"record family_id {record.family_id!r} does not match ledger family_id {self.family_id!r}"
            )
        if any(existing.trial_id == record.trial_id for existing in self.records):
            raise AppendOnlyLedgerError(f"duplicate trial_id: {record.trial_id}")

        records = self.records + (record,)
        ledger_hash = canonical_hash(
            _ledger_hash_payload(
                ledger_id=self.ledger_id,
                family_id=self.family_id,
                records=records,
                append_only=self.append_only,
            )
        )
        return self.model_copy(update={"records": records, "ledger_hash": ledger_hash})

    def trial_count(
        self,
        *,
        family_id: str | None = None,
        sub_family_id: str | None = None,
    ) -> int:
        count = 0
        for record in self.records:
            if family_id is not None and record.family_id != family_id:
                continue
            if sub_family_id is not None and record.sub_family_id != sub_family_id:
                continue
            count += 1
        return count


class InMemoryTrialLedgerStore:
    def __init__(self) -> None:
        self._ledgers: dict[str, TrialLedger] = {}

    def create(self, ledger_id: str, family_id: str) -> TrialLedger:
        if ledger_id in self._ledgers:
            raise AppendOnlyLedgerError(f"ledger already exists: {ledger_id}")
        ledger = TrialLedger.create(ledger_id=ledger_id, family_id=family_id)
        self._ledgers[ledger_id] = ledger
        return ledger

    def append(self, ledger_id: str, record: TrialRecord) -> TrialLedger:
        ledger = self.get(ledger_id).append(record)
        self._ledgers[ledger_id] = ledger
        return ledger

    def get(self, ledger_id: str) -> TrialLedger:
        try:
            return self._ledgers[ledger_id]
        except KeyError as exc:
            raise KeyError(f"unknown ledger_id: {ledger_id}") from exc


class JsonTrialLedgerStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, ledger_id: str) -> Path:
        return self.root / f"{ledger_id}.jsonl"

    def create(self, ledger_id: str, family_id: str) -> TrialLedger:
        path = self._path(ledger_id)
        if path.exists():
            raise AppendOnlyLedgerError(f"ledger already exists: {ledger_id}")
        ledger = TrialLedger.create(ledger_id=ledger_id, family_id=family_id)
        path.write_text(
            _json_line(
                {
                    "type": "ledger",
                    "ledger_id": ledger.ledger_id,
                    "family_id": ledger.family_id,
                    "schema_version": ledger.schema_version,
                }
            ),
            encoding="utf-8",
        )
        return ledger

    def append(self, ledger_id: str, record: TrialRecord) -> TrialLedger:
        ledger = self.get(ledger_id).append(record)
        with self._path(ledger_id).open("a", encoding="utf-8") as handle:
            handle.write(_json_line({"type": "record", "record": record.model_dump(mode="json")}))
        return ledger

    def get(self, ledger_id: str) -> TrialLedger:
        path = self._path(ledger_id)
        if not path.exists():
            raise KeyError(f"unknown ledger_id: {ledger_id}")
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            raise AppendOnlyLedgerError(f"empty ledger file: {ledger_id}")

        import json

        header = json.loads(lines[0])
        if header.get("type") != "ledger":
            raise AppendOnlyLedgerError(f"missing ledger header: {ledger_id}")
        ledger = TrialLedger.create(ledger_id=header["ledger_id"], family_id=header["family_id"])
        for line in lines[1:]:
            payload = json.loads(line)
            if payload.get("type") != "record":
                raise AppendOnlyLedgerError(f"unexpected ledger line type: {payload.get('type')}")
            ledger = ledger.append(TrialRecord.model_validate(payload["record"]))
        return ledger


def _json_line(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
