"""API와 persistence 구현체를 조립합니다. 생성 시 DB에 연결하지 않습니다."""

from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID

from sqlalchemy import Engine

from app.accounting.application.catalog import prepare_accounts
from app.accounting.application.contracts import MasterUnitOfWork
from app.accounting.application.service import AccountingMasterService
from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork
from app.accounting.journals.application.commands import JournalCommands
from app.accounting.journals.application.service import JournalService
from app.accounting.journals.infrastructure.unit_of_work import JournalSQLAlchemyUnitOfWork
from app.accounting.ledger.application.service import AccountingReports
from app.accounting.opening_balances.application.service import OpeningService
from app.accounting.transactions.application.service import TransactionService
from app.accounting.transactions.infrastructure.unit_of_work import TransactionSQLAlchemyUnitOfWork
from app.approvals.infrastructure.unit_of_work import AccountingSQLAlchemyUnitOfWork
from app.companies.application.service import CompanyService
from app.core.config import Settings
from app.core.database.engine import create_database_engine
from app.core.database.session import create_session_factory
from app.core.security import PasswordSecurity, TokenSecurity
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
from app.master_data.application.service import MasterDataService
from app.onboarding.application.merge import OnboardingImportService
from app.onboarding.application.service import OnboardingService
from app.onboarding.infrastructure.template import parse_onboarding
from app.onboarding.infrastructure.unit_of_work import OnboardingSQLAlchemyUnitOfWork
from app.storage.infrastructure.local import LocalObjectStorage


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
    return engine, Services(
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
        OpeningService(lambda: AccountingSQLAlchemyUnitOfWork(sessions)),
        FinanceService(lambda: FinanceSQLAlchemyUnitOfWork(sessions)),
        FinanceReports(lambda: FinanceSQLAlchemyUnitOfWork(sessions)),
    )


def _prepare_company_accounts(uow: MasterUnitOfWork, company: UUID) -> None:
    prepare_accounts(uow, company)
