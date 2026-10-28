"""현금흐름표 선행 매핑을 회사 범위로 저장합니다."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.accounting.journals.infrastructure.models import JournalEvidenceModel, JournalModel
from app.reporting.cash_flow.entities import CashAllocation, CashClassification, CashScope
from app.reporting.cash_flow.indirect import AdjustmentRule
from app.reporting.cash_flow.models import (
    CashFlowAdjustmentRuleModel,
    CashFlowAllocationModel,
    CashFlowClassificationModel,
    CashScopeMappingModel,
)
from app.reporting.financial_statements.infrastructure.models import (
    StatementLineModel,
    StatementModel,
    StatementSnapshotModel,
)


class CashFlowRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_configuration(self, company: UUID) -> None:
        """Serialize rule insertion and snapshot creation, including empty rule sets."""
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"cash-flow:{company}"},
        )

    def statement_snapshot_sources(
        self,
        company: UUID,
        set_id: UUID,
    ) -> tuple[tuple[str, str, str, int, str, str], ...]:
        rows = self.session.execute(
            select(StatementSnapshotModel, StatementModel.statement_type)
            .join(StatementModel, StatementModel.id == StatementSnapshotModel.statement_id)
            .where(
                StatementSnapshotModel.company_id == company,
                StatementModel.company_id == company,
                StatementModel.statement_set_id == set_id,
            )
            .order_by(StatementModel.statement_type)
        )
        return tuple(
            (
                str(row.id),
                str(row.statement_id),
                kind,
                row.statement_version,
                row.source_digest,
                row.mapping_digest,
            )
            for row, kind in rows
        )

    def statement_line_sources_valid(
        self,
        company: UUID,
        set_id: UUID,
        source_digest: str,
    ) -> bool:
        invalid = self.session.scalar(
            select(StatementLineModel.id)
            .join(
                StatementSnapshotModel, StatementSnapshotModel.id == StatementLineModel.snapshot_id
            )
            .join(StatementModel, StatementModel.id == StatementSnapshotModel.statement_id)
            .where(
                StatementLineModel.company_id == company,
                StatementSnapshotModel.company_id == company,
                StatementModel.company_id == company,
                StatementModel.statement_set_id == set_id,
                StatementLineModel.source_digest != source_digest,
            )
            .limit(1)
        )
        return invalid is None

    def lock_journal(self, company: UUID, journal_id: UUID) -> JournalModel | None:
        return self.session.scalar(
            select(JournalModel)
            .where(JournalModel.company_id == company, JournalModel.id == journal_id)
            .with_for_update()
        )

    def evidence_linked(self, company: UUID, journal_id: UUID, evidence_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(JournalEvidenceModel.id).where(
                    JournalEvidenceModel.company_id == company,
                    JournalEvidenceModel.journal_entry_id == journal_id,
                    JournalEvidenceModel.evidence_id == evidence_id,
                )
            )
            is not None
        )

    def allocation_history(
        self, company: UUID, journal_id: UUID | None = None
    ) -> tuple[CashAllocation, ...]:
        query = select(CashFlowAllocationModel).where(CashFlowAllocationModel.company_id == company)
        if journal_id is not None:
            query = query.where(CashFlowAllocationModel.journal_id == journal_id)
        rows = self.session.scalars(
            query.order_by(
                CashFlowAllocationModel.journal_id,
                CashFlowAllocationModel.cash_line_id,
                CashFlowAllocationModel.counterpart_line_id,
                CashFlowAllocationModel.version,
            )
        )
        return tuple(
            CashAllocation(
                row.id,
                row.journal_id,
                row.cash_line_id,
                row.counterpart_line_id,
                row.evidence_id,
                row.amount,
                row.version,
                row.replaces_id,
            )
            for row in rows
        )

    def allocations(
        self, company: UUID, journal_id: UUID | None = None
    ) -> tuple[CashAllocation, ...]:
        current: dict[tuple[UUID, UUID, UUID], CashAllocation] = {}
        for row in self.allocation_history(company, journal_id):
            current[(row.journal_id, row.cash_line_id, row.counterpart_line_id)] = row
        return tuple(row for row in current.values() if row.amount > 0)

    def allocation(self, company: UUID, allocation_id: UUID) -> CashAllocation | None:
        return next(
            (row for row in self.allocation_history(company) if row.id == allocation_id), None
        )

    def add_allocation(
        self,
        company: UUID,
        journal_id: UUID,
        cash_line_id: UUID,
        counterpart_line_id: UUID,
        evidence_id: UUID,
        amount: Decimal,
        actor: UUID,
        now: datetime,
        version: int = 1,
        replaces_id: UUID | None = None,
    ) -> CashAllocation:
        row = CashFlowAllocationModel(
            id=uuid4(),
            company_id=company,
            journal_id=journal_id,
            cash_line_id=cash_line_id,
            counterpart_line_id=counterpart_line_id,
            evidence_id=evidence_id,
            amount=amount,
            version=version,
            replaces_id=replaces_id,
            created_by=actor,
            created_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return CashAllocation(
            row.id,
            row.journal_id,
            row.cash_line_id,
            row.counterpart_line_id,
            row.evidence_id,
            row.amount,
            row.version,
            row.replaces_id,
        )

    def scopes(self, company: UUID) -> tuple[CashScope, ...]:
        rows = self.session.scalars(
            select(CashScopeMappingModel)
            .where(
                CashScopeMappingModel.company_id == company,
                CashScopeMappingModel.status == "ACTIVE",
            )
            .order_by(CashScopeMappingModel.account_id)
        )
        return tuple(
            CashScope(
                row.id,
                row.account_id,
                row.scope_type,
                row.effective_from,
                row.effective_to,
                row.version,
            )
            for row in rows
        )

    def classifications(self, company: UUID) -> tuple[CashClassification, ...]:
        rows = self.session.scalars(
            select(CashFlowClassificationModel)
            .where(
                CashFlowClassificationModel.company_id == company,
                CashFlowClassificationModel.status == "ACTIVE",
            )
            .order_by(CashFlowClassificationModel.account_id)
        )
        return tuple(
            CashClassification(
                row.id,
                row.account_id,
                row.activity_type,
                row.line_code,
                row.effective_from,
                row.effective_to,
                row.version,
            )
            for row in rows
        )

    def add_scope(
        self,
        company: UUID,
        account: UUID,
        scope_type: str,
        effective_from: date,
        actor: UUID,
        now: datetime,
    ) -> CashScope:
        row = CashScopeMappingModel(
            id=uuid4(),
            company_id=company,
            account_id=account,
            scope_type=scope_type,
            effective_from=effective_from,
            effective_to=None,
            status="ACTIVE",
            version=1,
            created_by=actor,
            created_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return CashScope(
            row.id,
            row.account_id,
            row.scope_type,
            row.effective_from,
            row.effective_to,
            row.version,
        )

    def add_classification(
        self,
        company: UUID,
        account: UUID,
        activity: str,
        line_code: str,
        effective_from: date,
        actor: UUID,
        now: datetime,
    ) -> CashClassification:
        row = CashFlowClassificationModel(
            id=uuid4(),
            company_id=company,
            account_id=account,
            activity_type=activity,
            line_code=line_code,
            effective_from=effective_from,
            effective_to=None,
            status="ACTIVE",
            version=1,
            created_by=actor,
            created_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return CashClassification(
            row.id,
            row.account_id,
            row.activity_type,
            row.line_code,
            row.effective_from,
            row.effective_to,
            row.version,
        )

    def adjustment_rules(self, company: UUID) -> tuple[AdjustmentRule, ...]:
        rows = self.session.scalars(
            select(CashFlowAdjustmentRuleModel)
            .where(CashFlowAdjustmentRuleModel.company_id == company)
            .order_by(CashFlowAdjustmentRuleModel.account_id)
        )
        return tuple(
            AdjustmentRule(
                row.id,
                row.account_id,
                row.adjustment_code,
                row.source_mapping_type,
                row.related_account_id,
                row.effective_from,
                row.effective_to,
                row.version,
                row.policy_code,
                row.policy_version,
            )
            for row in rows
        )

    def add_adjustment_rule(
        self,
        company: UUID,
        rule: AdjustmentRule,
        actor: UUID,
        now: datetime,
    ) -> AdjustmentRule:
        from dataclasses import asdict

        self.session.add(
            CashFlowAdjustmentRuleModel(
                **asdict(rule),
                company_id=company,
                created_by=actor,
                created_at=now,
            )
        )
        self.session.flush()
        return rule
