"""대사는 조회 결과이며 장부나 보조부 잔액을 자동 보정하지 않습니다."""

from collections.abc import Callable
from datetime import date
from uuid import UUID

from app.companies.application.service import require_company
from app.finance.reconciliation.domain.reports import (
    AgingSummary,
    Reconciliation,
    ReconciliationRow,
    aging,
)
from app.finance.settlements.application.contracts import FinanceUnitOfWork
from app.finance.settlements.application.policy import CONTROL_NAMES, permission
from app.finance.settlements.domain.rules import ZERO
from app.identity.users.domain.entities import Principal


class FinanceReports:
    def __init__(self, factory: Callable[[], FinanceUnitOfWork]) -> None:
        self.factory = factory

    def aging(self, actor: Principal, company: UUID, kind: str, as_of: date) -> AgingSummary:
        with self.factory() as uow:
            require_company(uow, actor, company, permission(kind))
            return aging(uow.obligations(kind).list(company, as_of), as_of)

    def reconcile(self, actor: Principal, company: UUID, kind: str, as_of: date) -> Reconciliation:
        with self.factory() as uow:
            require_company(uow, actor, company, permission(kind))
            values = uow.obligations(kind).list(company, as_of)
            facts = uow.ledger.facts(company, as_of)
            rows = []
            for account in uow.accounts.list(company):
                if account.account_name not in CONTROL_NAMES[kind]:
                    continue
                selected = [fact for fact in facts if fact.account_id == account.id]
                obligations = [value for value in values if value.account_id == account.id]
                subledger = sum((value.outstanding_amount for value in obligations), ZERO)
                gl = sum((fact.debit_amount - fact.credit_amount for fact in selected), ZERO)
                if kind == "AP":
                    gl = -gl
                difference = subledger - gl
                rows.append(
                    ReconciliationRow(
                        account.id,
                        account.account_code,
                        account.account_name,
                        subledger,
                        gl,
                        difference,
                        "MATCHED" if difference == ZERO else "MISMATCH",
                        tuple(sorted({fact.journal_id for fact in selected})),
                        tuple(
                            sorted(
                                {
                                    evidence
                                    for value in obligations
                                    for evidence in value.evidence_ids
                                }
                            )
                        ),
                    )
                )
            subledger = sum((row.subledger_amount for row in rows), ZERO)
            gl = sum((row.gl_amount for row in rows), ZERO)
            return Reconciliation(
                as_of,
                "MATCHED" if all(row.status == "MATCHED" for row in rows) else "MISMATCH",
                subledger,
                gl,
                subledger - gl,
                tuple(rows),
            )
