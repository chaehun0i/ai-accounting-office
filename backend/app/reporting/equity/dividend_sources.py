"""Read-only dividend source selection using the same command validation rules."""

from uuid import UUID

from sqlalchemy import select

from app.accounting.journals.infrastructure.models import JournalEvidenceModel, JournalModel
from app.companies.application.service import require_company
from app.contracts.access_errors import ResourceNotFound
from app.identity.users.domain.entities import Principal
from app.reporting.cash_flow.snapshot_models import CashFlowEventModel, CashFlowStatementModel
from app.reporting.equity.models import DividendDeclarationModel, DividendPaymentModel
from app.reporting.equity.service import ZERO, EquityService


class DividendSources:
    def __init__(self, equity: EquityService) -> None:
        self.equity = equity

    def declarations(
        self, actor: Principal, company: UUID, period_id: UUID
    ) -> list[dict[str, object]]:
        with self.equity.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            if uow.periods.get(company_id=company, resource_id=period_id) is None:
                raise ResourceNotFound()
            journals = uow.session.scalars(
                select(JournalModel)
                .where(
                    JournalModel.company_id == company,
                    JournalModel.accounting_period_id == period_id,
                    JournalModel.status == "POSTED",
                    JournalModel.approval_id.is_not(None),
                )
                .order_by(JournalModel.entry_date, JournalModel.id)
            )
            linked = set(
                uow.session.scalars(
                    select(DividendDeclarationModel.source_journal_id).where(
                        DividendDeclarationModel.company_id == company,
                    )
                )
            )
            result: list[dict[str, object]] = []
            for journal in journals:
                amount = self.equity._dividend_amount(uow, company, journal)
                if amount is None:
                    continue
                evidence = list(
                    uow.session.scalars(
                        select(JournalEvidenceModel.evidence_id).where(
                            JournalEvidenceModel.company_id == company,
                            JournalEvidenceModel.journal_entry_id == journal.id,
                        )
                    )
                )
                result.append(
                    {
                        "journal_id": journal.id,
                        "journal_no": journal.journal_no,
                        "entry_date": journal.entry_date,
                        "description": journal.description,
                        "amount": amount,
                        "approval_id": journal.approval_id,
                        "evidence_ids": evidence,
                        "status": "LINKED" if journal.id in linked else "AVAILABLE",
                    }
                )
            return result

    def payments(
        self, actor: Principal, company: UUID, declaration_id: UUID, period_id: UUID
    ) -> dict[str, object]:
        with self.equity.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            declaration = uow.session.scalar(
                select(DividendDeclarationModel).where(
                    DividendDeclarationModel.company_id == company,
                    DividendDeclarationModel.id == declaration_id,
                )
            )
            period = uow.periods.get(company_id=company, resource_id=period_id)
            if declaration is None or period is None:
                raise ResourceNotFound()
            linked = list(
                uow.session.execute(
                    select(DividendPaymentModel, CashFlowEventModel)
                    .join(
                        CashFlowEventModel,
                        (CashFlowEventModel.company_id == company)
                        & (CashFlowEventModel.id == DividendPaymentModel.cash_flow_event_id),
                    )
                    .where(DividendPaymentModel.company_id == company)
                )
            )
            paid = sum(
                (
                    payment.amount
                    for payment, _ in linked
                    if payment.declaration_id == declaration_id
                ),
                ZERO,
            )
            used = {(event.cash_line_id, event.counterpart_line_id) for _, event in linked}
            # Latest frozen revision only. A stale latest revision is shown as blocked,
            # never silently replaced by a different older revision.
            statement = uow.session.scalar(
                select(CashFlowStatementModel)
                .where(
                    CashFlowStatementModel.company_id == company,
                    CashFlowStatementModel.period_id == period_id,
                )
                .order_by(
                    CashFlowStatementModel.generated_at.desc(), CashFlowStatementModel.id.desc()
                )
                .limit(1)
            )
            source_current = statement is not None and self.equity._current_cash_source(
                uow, company, statement
            )
            candidates = []
            if statement is not None:
                rows = uow.session.execute(
                    select(CashFlowEventModel, JournalModel)
                    .join(
                        JournalModel,
                        (JournalModel.company_id == company)
                        & (JournalModel.id == CashFlowEventModel.journal_id),
                    )
                    .where(
                        CashFlowEventModel.company_id == company,
                        CashFlowEventModel.statement_id == statement.id,
                        CashFlowEventModel.cash_outflow > ZERO,
                        CashFlowEventModel.activity_type == "FINANCING",
                    )
                    .order_by(JournalModel.entry_date, CashFlowEventModel.id)
                )
                for event, journal in rows:
                    issue = (
                        "PAYMENT_ALREADY_LINKED"
                        if (event.cash_line_id, event.counterpart_line_id) in used
                        else self.equity._payment_issue(
                            uow,
                            company,
                            declaration,
                            event,
                            statement,
                            source_current=source_current,
                        )
                    )
                    candidates.append(
                        {
                            "event_id": event.id,
                            "journal_id": journal.id,
                            "journal_no": journal.journal_no,
                            "entry_date": journal.entry_date,
                            "amount": event.cash_outflow,
                            "evidence_id": event.evidence_id,
                            "status": "BLOCKED" if issue else "AVAILABLE",
                            "issue": issue,
                        }
                    )
            return {
                "declaration_id": declaration_id,
                "period_id": period_id,
                "paid_amount": paid,
                "remaining_amount": declaration.total_amount - paid,
                "statement_id": statement.id if statement else None,
                "source_digest": statement.source_digest if statement else None,
                "issue": "PERIOD_NOT_CLOSED"
                if period.status != "CLOSED"
                else "CF_SNAPSHOT_MISSING"
                if statement is None
                else "PAYMENT_SOURCE_STALE"
                if not source_current
                else None,
                "candidates": candidates,
            }
