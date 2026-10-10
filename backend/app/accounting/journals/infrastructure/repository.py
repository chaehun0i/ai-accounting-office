from dataclasses import asdict
from datetime import date
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.accounting.journals.domain.entities import Journal, JournalLine
from app.accounting.journals.infrastructure.models import (
    JournalEvidenceModel,
    JournalLineModel,
    JournalModel,
    JournalProposalModel,
)


class JournalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def entity(self, row: JournalModel) -> Journal:
        lines = tuple(
            JournalLine(**{name: getattr(line, name) for name in JournalLine.__dataclass_fields__})
            for line in self.session.scalars(
                select(JournalLineModel)
                .where(
                    JournalLineModel.company_id == row.company_id,
                    JournalLineModel.journal_entry_id == row.id,
                )
                .order_by(JournalLineModel.line_no)
            )
        )
        evidence = tuple(
            self.session.scalars(
                select(JournalEvidenceModel.evidence_id).where(
                    JournalEvidenceModel.company_id == row.company_id,
                    JournalEvidenceModel.journal_entry_id == row.id,
                )
            )
        )
        return Journal(
            **{
                name: getattr(row, name)
                for name in Journal.__dataclass_fields__
                if name not in ("lines", "evidence_ids")
            },
            lines=lines,
            evidence_ids=evidence,
        )

    def get(self, company_id: UUID, resource_id: UUID, *, lock: bool = False) -> Journal | None:
        q = select(JournalModel).where(
            JournalModel.company_id == company_id, JournalModel.id == resource_id
        )
        row = self.session.scalar(q.with_for_update() if lock else q)
        return self.entity(row) if row else None

    def list(self, company_id: UUID, date_from: date, date_to: date) -> list[Journal]:
        return [
            self.entity(r)
            for r in self.session.scalars(
                select(JournalModel)
                .where(
                    JournalModel.company_id == company_id,
                    JournalModel.entry_date.between(date_from, date_to),
                )
                .order_by(JournalModel.entry_date, JournalModel.id)
                .limit(500)
            )
        ]

    def reversal(self, company_id: UUID, original: UUID) -> Journal | None:
        row = self.session.scalar(
            select(JournalModel).where(
                JournalModel.company_id == company_id, JournalModel.reversal_of_id == original
            )
        )
        return self.entity(row) if row else None

    def add_lines(self, value: Journal) -> None:
        for line in value.lines:
            self.session.add(
                JournalLineModel(
                    company_id=value.company_id, journal_entry_id=value.id, **asdict(line)
                )
            )
        for evidence in value.evidence_ids:
            self.session.add(
                JournalEvidenceModel(
                    id=uuid4(),
                    company_id=value.company_id,
                    journal_entry_id=value.id,
                    evidence_id=evidence,
                )
            )

    def add(self, value: Journal) -> None:
        data = asdict(value)
        data.pop("lines")
        data.pop("evidence_ids")
        self.session.add(JournalModel(**data))
        self.session.flush()
        self.add_lines(value)
        self.session.add(
            JournalProposalModel(
                id=uuid4(),
                company_id=value.company_id,
                journal_entry_id=value.id,
                transaction_id=value.source_transaction_id,
                status="DRAFT",
                reason_summary=value.description,
                version=1,
                created_at=value.created_at,
                updated_at=value.updated_at,
            )
        )
        self.session.flush()

    def update(self, value: Journal, expected_version: int, *, replace_lines: bool = False) -> bool:
        data = asdict(value)
        data.pop("lines")
        data.pop("evidence_ids")
        result = self.session.execute(
            update(JournalModel)
            .where(
                JournalModel.company_id == value.company_id,
                JournalModel.id == value.id,
                JournalModel.version == expected_version,
                JournalModel.status != "POSTED",
            )
            .values(**data)
        )
        if cast(CursorResult[object], result).rowcount != 1:
            return False
        if replace_lines:
            self.session.execute(
                delete(JournalLineModel).where(
                    JournalLineModel.company_id == value.company_id,
                    JournalLineModel.journal_entry_id == value.id,
                )
            )
            self.session.execute(
                delete(JournalEvidenceModel).where(
                    JournalEvidenceModel.company_id == value.company_id,
                    JournalEvidenceModel.journal_entry_id == value.id,
                )
            )
            self.add_lines(value)
        self.session.execute(
            update(JournalProposalModel)
            .where(
                JournalProposalModel.company_id == value.company_id,
                JournalProposalModel.journal_entry_id == value.id,
            )
            .values(status=value.status, version=value.version, updated_at=value.updated_at)
        )
        self.session.flush()
        return True
