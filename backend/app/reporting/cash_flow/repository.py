"""현금흐름표 선행 매핑을 회사 범위로 저장합니다."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.reporting.cash_flow.entities import CashClassification, CashScope
from app.reporting.cash_flow.models import CashFlowClassificationModel, CashScopeMappingModel


class CashFlowRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

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
