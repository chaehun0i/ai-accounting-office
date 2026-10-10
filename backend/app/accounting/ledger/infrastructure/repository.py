from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounting.accounts.infrastructure.models import AccountModel
from app.accounting.journals.infrastructure.models import JournalLineModel, JournalModel
from app.accounting.ledger.domain.entities import LedgerFact
from app.accounting.transactions.infrastructure.models import TransactionModel
from app.master_data.counterparties.infrastructure.models import CounterpartyModel


class LedgerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def facts(
        self, company: UUID, date_to: date, account_id: UUID | None = None
    ) -> list[LedgerFact]:
        query = (
            select(
                JournalModel,
                JournalLineModel,
                AccountModel,
                TransactionModel.import_id,
                CounterpartyModel.display_name,
            )
            .join(
                JournalLineModel,
                (JournalLineModel.journal_entry_id == JournalModel.id)
                & (JournalLineModel.company_id == company),
            )
            .join(
                AccountModel,
                (AccountModel.id == JournalLineModel.account_id)
                & (AccountModel.company_id == company),
            )
            .outerjoin(
                TransactionModel,
                (TransactionModel.id == JournalModel.source_transaction_id)
                & (TransactionModel.company_id == company),
            )
            .outerjoin(
                CounterpartyModel,
                (CounterpartyModel.id == JournalLineModel.counterparty_id)
                & (CounterpartyModel.company_id == company),
            )
            .where(
                JournalModel.company_id == company,
                JournalModel.status == "POSTED",
                JournalModel.entry_date <= date_to,
            )
        )
        if account_id:
            query = query.where(AccountModel.id == account_id)
        query = query.order_by(
            JournalModel.entry_date,
            JournalModel.journal_no,
            JournalModel.id,
            JournalLineModel.line_no,
        )
        return [
            LedgerFact(
                journal_id=j.id,
                line_id=line.id,
                entry_date=j.entry_date,
                journal_no=j.journal_no or "",
                account_id=a.id,
                account_code=a.account_code,
                account_name=a.account_name,
                normal_balance=a.normal_balance,
                counterparty_id=line.counterparty_id,
                counterparty_name=counterparty_name,
                description=line.memo or j.description,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                source_transaction_id=j.source_transaction_id,
                import_id=import_id,
            )
            for j, line, a, import_id, counterparty_name in self.session.execute(query)
        ]
