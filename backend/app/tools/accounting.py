"""실제 Application Service를 사용하는 Canonical Tool을 조립합니다."""

from datetime import date
from typing import cast
from uuid import UUID

from pydantic import BaseModel, Field

from app.accounting.accounts.domain.entities import Account
from app.accounting.application.service import AccountingMasterService
from app.accounting.journals.application.agent_proposals import AgentProposalService
from app.accounting.journals.domain.entities import Journal
from app.accounting.ledger.application.service import AccountingReports
from app.accounting.ledger.domain.entities import LedgerRow, TrialRow
from app.accounting.transactions.application.evidence import (
    EvidenceReferences,
    TransactionEvidenceQuery,
)
from app.accounting.transactions.application.service import TransactionService
from app.accounting.transactions.domain.entities import Transaction
from app.closing.application.service import ClosingService
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput
from app.finance.receivables.domain.entities import Obligation
from app.finance.reconciliation.application.service import FinanceReports
from app.finance.reconciliation.domain.reports import Reconciliation
from app.finance.settlements.application.service import FinanceService
from app.reporting.financial_statements.application.service import StatementService
from app.tools.contracts import (
    AsOfInput,
    Input,
    LedgerInput,
    PeriodInput,
    ResourceInput,
    Result,
    SearchInput,
    ToolContext,
    ToolDefinition,
)
from app.tools.registry import ToolRegistry
from app.tools.reporting import definitions as reporting_definitions


class ProposalInput(Input):
    transaction_id: UUID
    source_version: int = Field(ge=1)
    debit_account_id: UUID
    credit_account_id: UUID
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=20)


class HandoffInput(ProposalInput):
    # 내부 실행 컨텍스트의 run_id를 사용하며 모델이 재시도 식별자를 지정하지 않습니다.
    pass


def build_registry(
    master: AccountingMasterService,
    transactions: TransactionService,
    reports: AccountingReports,
    finance: FinanceService,
    finance_reports: FinanceReports,
    proposals: AgentProposalService,
    closing: ClosingService | None = None,
    statements: StatementService | None = None,
) -> ToolRegistry:
    def authorize(context: ToolContext, permission: str) -> None:
        with master.factory() as uow:
            require_company(uow, context.principal, context.company_id, permission)

    registry = ToolRegistry(authorize)
    evidence = TransactionEvidenceQuery(transactions)

    def search(context: ToolContext, payload: BaseModel) -> BaseModel:
        query = cast(SearchInput, payload)
        values = master.accounts(context.principal, context.company_id)
        selected = [
            a
            for a in values
            if a.status == "ACTIVE"
            and a.posting_allowed
            and (not query.account_type or a.account_type == query.account_type)
            and query.query_text.casefold() in (a.account_code + " " + a.account_name).casefold()
        ]
        return Result[list[Account]](as_of=date.today(), data=selected[: query.limit])

    def transaction(context: ToolContext, payload: BaseModel) -> BaseModel:
        value = transactions.get(
            context.principal, context.company_id, cast(ResourceInput, payload).transaction_id
        )
        return Result[Transaction](
            as_of=value.accounting_date,
            data=value,
            evidence_refs=[value.evidence_id] if value.evidence_id else [],
        )

    def sources(context: ToolContext, payload: BaseModel) -> BaseModel:
        value = evidence.get(
            context.principal, context.company_id, cast(ResourceInput, payload).transaction_id
        )
        return Result[EvidenceReferences](
            as_of=date.today(), data=value, evidence_refs=list(value.evidence_ids)
        )

    def ledger(context: ToolContext, payload: BaseModel) -> BaseModel:
        q = cast(LedgerInput, payload)
        return Result[list[LedgerRow]](
            as_of=q.date_to,
            data=reports.ledger(
                context.principal, context.company_id, q.account_id, q.date_from, q.date_to
            ),
        )

    def trial(context: ToolContext, payload: BaseModel) -> BaseModel:
        return Result[list[TrialRow]](
            as_of=date.today(),
            data=reports.trial(
                context.principal, context.company_id, cast(PeriodInput, payload).period_id
            ),
        )

    def obligation(context: ToolContext, payload: BaseModel, kind: str) -> BaseModel:
        q = cast(AsOfInput, payload)
        return Result[list[Obligation]](
            as_of=q.as_of, data=finance.list(context.principal, context.company_id, kind, q.as_of)
        )

    def reconciliation(context: ToolContext, payload: BaseModel, kind: str) -> BaseModel:
        q = cast(AsOfInput, payload)
        return Result[Reconciliation](
            as_of=q.as_of,
            data=finance_reports.reconcile(context.principal, context.company_id, kind, q.as_of),
        )

    def validate(context: ToolContext, payload: BaseModel) -> BaseModel:
        q = cast(ProposalInput, payload)
        value = proposals.candidate(
            context.principal,
            context.company_id,
            q.transaction_id,
            q.source_version,
            q.debit_account_id,
            q.credit_account_id,
            tuple(q.evidence_ids),
        )
        return Result[Journal](
            as_of=value.entry_date, data=value, evidence_refs=list(value.evidence_ids)
        )

    def propose(context: ToolContext, payload: BaseModel) -> BaseModel:
        command_id = context.run_id or context.invocation_id
        if command_id is None:
            raise InvalidInput()
        checked = cast(Result[Journal], validate(context, payload))
        value = proposals.handoff(
            context.principal, checked.data, command_id, cast(ProposalInput, payload).source_version
        )
        return Result[Journal](
            as_of=value.entry_date, data=value, evidence_refs=list(value.evidence_ids)
        )

    definitions = [
        ToolDefinition(
            "accounting.search_accounts",
            "회사의 활성 분개 계정을 검색합니다.",
            "account.read",
            SearchInput,
            Result[list[Account]],
            search,
        ),
        ToolDefinition(
            "accounting.get_transaction",
            "회사의 원천 거래를 조회합니다.",
            "transaction.read",
            ResourceInput,
            Result[Transaction],
            transaction,
        ),
        ToolDefinition(
            "evidence.get_transaction_evidence",
            "거래의 증빙 출처를 조회합니다.",
            "evidence.read",
            ResourceInput,
            Result[EvidenceReferences],
            sources,
        ),
        ToolDefinition(
            "accounting.get_ledger",
            "확정 전표에서 원장을 조회합니다.",
            "ledger.read",
            LedgerInput,
            Result[list[LedgerRow]],
            ledger,
        ),
        ToolDefinition(
            "accounting.get_trial_balance",
            "회계기간의 시산표를 조회합니다.",
            "trial_balance.read",
            PeriodInput,
            Result[list[TrialRow]],
            trial,
        ),
        ToolDefinition(
            "finance.list_receivables",
            "기준일의 매출채권을 조회합니다.",
            "receivable.read",
            AsOfInput,
            Result[list[Obligation]],
            lambda c, p: obligation(c, p, "AR"),
        ),
        ToolDefinition(
            "finance.list_payables",
            "기준일의 매입채무를 조회합니다.",
            "payable.read",
            AsOfInput,
            Result[list[Obligation]],
            lambda c, p: obligation(c, p, "AP"),
        ),
        ToolDefinition(
            "finance.get_ar_reconciliation",
            "채권과 원장의 차이를 조회합니다.",
            "receivable.read",
            AsOfInput,
            Result[Reconciliation],
            lambda c, p: reconciliation(c, p, "AR"),
        ),
        ToolDefinition(
            "finance.get_ap_reconciliation",
            "채무와 원장의 차이를 조회합니다.",
            "payable.read",
            AsOfInput,
            Result[Reconciliation],
            lambda c, p: reconciliation(c, p, "AP"),
        ),
        ToolDefinition(
            "accounting.validate_journal",
            "원천 금액으로 만든 분개 후보를 검증합니다.",
            "journal.propose",
            ProposalInput,
            Result[Journal],
            validate,
        ),
    ]
    for definition in definitions:
        registry.register(definition)
    registry.register(
        ToolDefinition(
            "accounting.propose_journal",
            "사람 검토를 위한 전표 초안을 생성합니다. 승인하거나 확정하지 않습니다.",
            "journal.propose",
            ProposalInput,
            Result[Journal],
            propose,
            tool_class="PROPOSE",
            side_effect_level="PROPOSAL",
        )
    )
    if closing is not None and statements is not None:
        for definition in reporting_definitions(closing, statements):
            registry.register(definition)
    return registry
