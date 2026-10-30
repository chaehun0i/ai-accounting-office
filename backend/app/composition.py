"""API와 persistence 구현체를 조립합니다. 생성 시 DB에 연결하지 않습니다."""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from app.accounting.application.catalog import prepare_accounts
from app.accounting.application.contracts import MasterUnitOfWork
from app.accounting.application.service import AccountingMasterService
from app.accounting.dimensions.application.service import DimensionService
from app.accounting.dimensions.infrastructure.unit_of_work import DimensionSQLAlchemyUnitOfWork
from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork
from app.accounting.journals.application.agent_proposals import AgentProposalService
from app.accounting.journals.application.commands import JournalCommands
from app.accounting.journals.application.service import JournalService
from app.accounting.journals.infrastructure.unit_of_work import JournalSQLAlchemyUnitOfWork
from app.accounting.ledger.application.service import AccountingReports
from app.accounting.opening_balances.application.service import OpeningService
from app.accounting.transactions.application.service import TransactionService
from app.accounting.transactions.infrastructure.unit_of_work import TransactionSQLAlchemyUnitOfWork
from app.agents.checkpoints.postgres import PostgresCheckpoints
from app.agents.runtime.service import AgentRuntime
from app.approvals.infrastructure.unit_of_work import AccountingSQLAlchemyUnitOfWork
from app.closing.application.service import ClosingService
from app.closing.infrastructure.unit_of_work import ClosingSQLAlchemyUnitOfWork
from app.companies.application.service import CompanyService
from app.core.config import Settings
from app.core.database.engine import create_database_engine
from app.core.database.session import create_session_factory
from app.core.security import PasswordSecurity, TokenSecurity
from app.finance.banking.application.service import BankingService
from app.finance.banking.infrastructure.unit_of_work import BankingSQLAlchemyUnitOfWork
from app.finance.invoices.application.service import DocumentService
from app.finance.invoices.infrastructure.unit_of_work import DocumentSQLAlchemyUnitOfWork
from app.finance.reconciliation.application.bank_service import BankReconciliationService
from app.finance.reconciliation.application.service import FinanceReports
from app.finance.settlements.application.service import FinanceService
from app.finance.settlements.infrastructure.unit_of_work import FinanceSQLAlchemyUnitOfWork
from app.identity.auth.application.service import AuthService
from app.identity.infrastructure.unit_of_work import IdentitySQLAlchemyUnitOfWork
from app.identity.invitations.application.service import InvitationService
from app.identity.invitations.infrastructure.unit_of_work import InvitationSQLAlchemyUnitOfWork
from app.intake.application.service import IntakeService
from app.intake.infrastructure.parser import parse_file
from app.intake.infrastructure.unit_of_work import IntakeSQLAlchemyUnitOfWork
from app.intake.promotion.application.service import PromotionService
from app.intake.promotion.infrastructure.unit_of_work import PromotionSQLAlchemyUnitOfWork
from app.jobs.application.runtime import RuntimeAudit
from app.jobs.infrastructure.unit_of_work import RuntimeSQLAlchemyUnitOfWork
from app.llm.gateway import LLMGateway
from app.llm.providers.fake import FakeProvider
from app.llm.providers.gemini import GeminiProvider
from app.master_data.application.service import MasterDataService
from app.onboarding.application.merge import OnboardingImportService
from app.onboarding.application.service import OnboardingService
from app.onboarding.infrastructure.template import parse_onboarding
from app.onboarding.infrastructure.unit_of_work import OnboardingSQLAlchemyUnitOfWork
from app.reporting.cash_flow.service import CashFlowService
from app.reporting.cash_flow.unit_of_work import CashFlowUnitOfWork
from app.reporting.center.service import ReportCenterService
from app.reporting.center.unit_of_work import ReportCenterUnitOfWork
from app.reporting.equity.service import EquityService
from app.reporting.financial_statements.application.service import StatementService
from app.reporting.financial_statements.infrastructure.unit_of_work import (
    ReportingSQLAlchemyUnitOfWork,
)
from app.storage.infrastructure.local import LocalObjectStorage
from app.tax.service import TaxService
from app.tax.unit_of_work import TaxUnitOfWork
from app.tools.accounting import build_registry
from app.tools.registry import ToolRegistry


@dataclass(frozen=True)
class Services:
    auth: AuthService | None
    companies: CompanyService
    invitations: InvitationService
    accounting: AccountingMasterService | None = None
    master_data: MasterDataService | None = None
    intake: IntakeService | None = None
    onboarding: OnboardingService | None = None
    onboarding_imports: OnboardingImportService | None = None
    transactions: TransactionService | None = None
    journals: JournalService | None = None
    journal_commands: JournalCommands | None = None
    accounting_reports: AccountingReports | None = None
    opening_balances: OpeningService | None = None
    finance: FinanceService | None = None
    finance_reports: FinanceReports | None = None
    tools: ToolRegistry | None = None
    agent_runtime: AgentRuntime | None = None
    runtime_audit: RuntimeAudit | None = None

    dimensions: DimensionService | None = None
    promotion: PromotionService | None = None
    documents: DocumentService | None = None
    banking: BankingService | None = None
    bank_reconciliation: BankReconciliationService | None = None
    closing: ClosingService | None = None
    statements: StatementService | None = None
    equity: EquityService | None = None
    report_center: ReportCenterService | None = None
    cash_flow: CashFlowService | None = None
    tax: TaxService | None = None


def create_services(settings: Settings) -> tuple[Engine, Services]:
    engine = create_database_engine(settings)
    sessions = create_session_factory(engine)
    auth = None
    if settings.auth_signing_key is not None:
        auth = AuthService(
            lambda: IdentitySQLAlchemyUnitOfWork(sessions),
            PasswordSecurity(),
            TokenSecurity(
                settings.auth_signing_key.get_secret_value(),
                settings.access_token_ttl_seconds,
                settings.refresh_token_ttl_seconds,
            ),
        )
    onboarding = OnboardingService(lambda: OnboardingSQLAlchemyUnitOfWork(sessions))
    container = Services(
        auth,
        CompanyService(
            lambda: MasterSQLAlchemyUnitOfWork(sessions),
            lambda uow, company: _prepare_company_accounts(cast(MasterUnitOfWork, uow), company),
        ),
        InvitationService(lambda: InvitationSQLAlchemyUnitOfWork(sessions)),
        AccountingMasterService(lambda: MasterSQLAlchemyUnitOfWork(sessions)),
        MasterDataService(lambda: MasterSQLAlchemyUnitOfWork(sessions)),
        IntakeService(
            lambda: IntakeSQLAlchemyUnitOfWork(sessions),
            LocalObjectStorage(Path(settings.storage_root)),
            parse_file,
        ),
        onboarding,
        OnboardingImportService(
            onboarding,
            IntakeService(
                lambda: IntakeSQLAlchemyUnitOfWork(sessions),
                LocalObjectStorage(Path(settings.storage_root)),
                parse_onboarding,
            ),
        ),
        TransactionService(lambda: TransactionSQLAlchemyUnitOfWork(sessions)),
        JournalService(lambda: JournalSQLAlchemyUnitOfWork(sessions)),
        JournalCommands(lambda: AccountingSQLAlchemyUnitOfWork(sessions)),
        AccountingReports(lambda: AccountingSQLAlchemyUnitOfWork(sessions)),
        OpeningService(lambda: FinanceSQLAlchemyUnitOfWork(sessions)),
        FinanceService(lambda: FinanceSQLAlchemyUnitOfWork(sessions)),
        FinanceReports(lambda: FinanceSQLAlchemyUnitOfWork(sessions)),
    )
    container = replace(
        container, dimensions=DimensionService(lambda: DimensionSQLAlchemyUnitOfWork(sessions))
    )
    container = replace(
        container,
        closing=ClosingService(
            lambda: ClosingSQLAlchemyUnitOfWork(sessions), container.journal_commands
        ),
        statements=StatementService(lambda: ReportingSQLAlchemyUnitOfWork(sessions)),
        equity=EquityService(lambda: ReportingSQLAlchemyUnitOfWork(sessions)),
        report_center=ReportCenterService(
            lambda: ReportCenterUnitOfWork(sessions),
            LocalObjectStorage(Path(settings.storage_root)),
        ),
        cash_flow=CashFlowService(lambda: CashFlowUnitOfWork(sessions)),
        tax=TaxService(lambda: TaxUnitOfWork(sessions)),
    )
    assert container.accounting and container.transactions and container.accounting_reports
    assert (
        container.finance
        and container.finance_reports
        and container.journals
        and container.journal_commands
    )
    registry = build_registry(
        container.accounting,
        container.transactions,
        container.accounting_reports,
        container.finance,
        container.finance_reports,
        AgentProposalService(container.journals, container.journal_commands),
        container.closing,
        container.statements,
        container.cash_flow,
    )
    audit = RuntimeAudit(lambda: RuntimeSQLAlchemyUnitOfWork(sessions))
    registry.record = audit.record_tool
    registry.started = audit.tool_started
    provider = (
        GeminiProvider(
            settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None,
            settings.gemini_model,
        )
        if settings.llm_provider == "gemini"
        else FakeProvider()
    )
    gateway = LLMGateway(provider, settings.llm_timeout_seconds, settings.llm_max_retries)
    checkpoints = PostgresCheckpoints(
        make_url(settings.postgres_url.get_secret_value())
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    return engine, replace(
        container,
        banking=BankingService(
            lambda: BankingSQLAlchemyUnitOfWork(sessions), cast(IntakeService, container.intake)
        ),
        bank_reconciliation=BankReconciliationService(
            lambda: BankingSQLAlchemyUnitOfWork(sessions)
        ),
        documents=DocumentService(lambda: DocumentSQLAlchemyUnitOfWork(sessions)),
        promotion=PromotionService(
            lambda: PromotionSQLAlchemyUnitOfWork(sessions), cast(IntakeService, container.intake)
        ),
        tools=registry,
        runtime_audit=audit,
        agent_runtime=AgentRuntime(registry, gateway, audit, checkpoints.open),
    )


def _prepare_company_accounts(uow: MasterUnitOfWork, company: UUID) -> None:
    prepare_accounts(uow, company)
