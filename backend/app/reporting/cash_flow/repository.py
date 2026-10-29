"""현금흐름표 선행 매핑을 회사 범위로 저장합니다."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.accounting.journals.infrastructure.models import (
    JournalEvidenceModel,
    JournalLineModel,
    JournalModel,
)
from app.reporting.cash_flow.entities import (
    CashAllocation,
    CashClassification,
    CashFlowPolicy,
    CashScope,
    DisposalSource,
    NonCashDisclosure,
)
from app.reporting.cash_flow.indirect import AdjustmentRule
from app.reporting.cash_flow.models import (
    CashFlowAdjustmentRuleModel,
    CashFlowAllocationModel,
    CashFlowClassificationModel,
    CashFlowDisposalSourceModel,
    CashFlowNonCashDisclosureModel,
    CashFlowPolicyModel,
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

    def policies(self, company: UUID) -> tuple[CashFlowPolicy, ...]:
        rows = list(
            self.session.scalars(
                select(CashFlowPolicyModel)
                .where(CashFlowPolicyModel.company_id == company)
                .order_by(CashFlowPolicyModel.version)
            )
        )
        return tuple(
            CashFlowPolicy(
                row.id,
                row.effective_from,
                row.version,
                row.interest_paid,
                row.interest_received,
                row.income_tax_paid,
                rows[index + 1].effective_from - timedelta(days=1)
                if index + 1 < len(rows)
                else None,
                "SUPERSEDED" if index + 1 < len(rows) else "LATEST",
            )
            for index, row in enumerate(rows)
        )

    def add_policy(
        self,
        company: UUID,
        effective_from: date,
        version: int,
        interest_paid: str,
        interest_received: str,
        income_tax_paid: str,
        actor: UUID,
        now: datetime,
    ) -> CashFlowPolicy:
        row = CashFlowPolicyModel(
            id=uuid4(),
            company_id=company,
            effective_from=effective_from,
            version=version,
            interest_paid=interest_paid,
            interest_received=interest_received,
            income_tax_paid=income_tax_paid,
            created_by=actor,
            created_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return CashFlowPolicy(
            row.id,
            row.effective_from,
            row.version,
            row.interest_paid,
            row.interest_received,
            row.income_tax_paid,
        )

    def non_cash_disclosures(
        self, company: UUID, period_id: UUID | None = None
    ) -> tuple[NonCashDisclosure, ...]:
        query = select(CashFlowNonCashDisclosureModel).where(
            CashFlowNonCashDisclosureModel.company_id == company
        )
        if period_id is not None:
            query = query.join(
                JournalModel,
                (JournalModel.company_id == company)
                & (JournalModel.id == CashFlowNonCashDisclosureModel.journal_id),
            ).where(JournalModel.accounting_period_id == period_id)
        return tuple(
            NonCashDisclosure(
                row.id,
                row.journal_id,
                row.debit_line_id,
                row.credit_line_id,
                row.evidence_id,
                row.source_type,
                row.amount,
                row.version,
            )
            for row in self.session.scalars(
                query.order_by(
                    CashFlowNonCashDisclosureModel.journal_id,
                    CashFlowNonCashDisclosureModel.debit_line_id,
                    CashFlowNonCashDisclosureModel.credit_line_id,
                )
            )
        )

    def disposal_sources(
        self, company: UUID, period_id: UUID | None = None
    ) -> tuple[DisposalSource, ...]:
        query = select(CashFlowDisposalSourceModel).where(
            CashFlowDisposalSourceModel.company_id == company
        )
        if period_id is not None:
            query = query.join(
                JournalModel,
                (JournalModel.company_id == company)
                & (JournalModel.id == CashFlowDisposalSourceModel.journal_id),
            ).where(JournalModel.accounting_period_id == period_id)
        return tuple(
            DisposalSource(
                row.id,
                row.journal_id,
                row.cash_line_id,
                row.asset_line_id,
                row.gain_line_id,
                row.evidence_id,
                row.proceeds,
                row.gain_amount,
                row.version,
            )
            for row in self.session.scalars(
                query.order_by(
                    CashFlowDisposalSourceModel.journal_id, CashFlowDisposalSourceModel.id
                )
            )
        )

    def add_disposal_source(
        self,
        company: UUID,
        journal_id: UUID,
        cash_line_id: UUID,
        asset_line_id: UUID,
        gain_line_id: UUID,
        evidence_id: UUID,
        proceeds: Decimal,
        gain_amount: Decimal,
        actor: UUID,
        now: datetime,
    ) -> DisposalSource:
        row = CashFlowDisposalSourceModel(
            id=uuid4(),
            company_id=company,
            journal_id=journal_id,
            cash_line_id=cash_line_id,
            asset_line_id=asset_line_id,
            gain_line_id=gain_line_id,
            evidence_id=evidence_id,
            proceeds=proceeds,
            gain_amount=gain_amount,
            version=1,
            created_by=actor,
            created_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return DisposalSource(
            row.id,
            journal_id,
            cash_line_id,
            asset_line_id,
            gain_line_id,
            evidence_id,
            proceeds,
            gain_amount,
            1,
        )

    def add_non_cash_disclosure(
        self,
        company: UUID,
        journal_id: UUID,
        debit_line_id: UUID,
        credit_line_id: UUID,
        evidence_id: UUID,
        source_type: str,
        amount: Decimal,
        actor: UUID,
        now: datetime,
    ) -> NonCashDisclosure:
        row = CashFlowNonCashDisclosureModel(
            id=uuid4(),
            company_id=company,
            journal_id=journal_id,
            debit_line_id=debit_line_id,
            credit_line_id=credit_line_id,
            evidence_id=evidence_id,
            source_type=source_type,
            amount=amount,
            version=1,
            created_by=actor,
            created_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return NonCashDisclosure(
            row.id, journal_id, debit_line_id, credit_line_id, evidence_id, source_type, amount, 1
        )

    def lock_configuration(self, company: UUID) -> None:
        """Serialize rule insertion and snapshot creation, including empty rule sets."""
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"cash-flow:{company}"},
        )

    def posted_balance_before(
        self, company: UUID, account_id: UUID, posted_at: datetime
    ) -> Decimal:
        value = self.session.scalar(
            select(
                func.coalesce(
                    func.sum(JournalLineModel.debit_amount - JournalLineModel.credit_amount), 0
                )
            )
            .join(
                JournalModel,
                (JournalModel.company_id == JournalLineModel.company_id)
                & (JournalModel.id == JournalLineModel.journal_entry_id),
            )
            .where(
                JournalLineModel.company_id == company,
                JournalLineModel.account_id == account_id,
                JournalModel.status == "POSTED",
                JournalModel.posted_at < posted_at,
            )
        )
        return Decimal(value or 0)

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
