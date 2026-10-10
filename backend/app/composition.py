"""API와 persistence 구현체를 조립합니다. 생성 시 DB에 연결하지 않습니다."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine

from app.accounting.application.service import AccountingMasterService
from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork
from app.accounting.journals.application.service import JournalService
from app.accounting.journals.infrastructure.unit_of_work import JournalSQLAlchemyUnitOfWork
from app.accounting.transactions.application.service import TransactionService
from app.accounting.transactions.infrastructure.unit_of_work import TransactionSQLAlchemyUnitOfWork
from app.companies.application.service import CompanyService
from app.companies.infrastructure.unit_of_work import CompanySQLAlchemyUnitOfWork
from app.accounting.journals.application.commands import JournalCommands
from app.approvals.infrastructure.unit_of_work import AccountingSQLAlchemyUnitOfWork
from app.accounting.ledger.application.service import AccountingReports
from app.core.config import Settings
from app.core.database.engine import create_database_engine
from app.core.database.session import create_session_factory
from app.core.security import PasswordSecurity, TokenSecurity
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
        CompanyService(lambda: CompanySQLAlchemyUnitOfWork(sessions)),
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
    )
