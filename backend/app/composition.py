"""API와 persistence 구현체를 조립합니다. 생성 시 DB에 연결하지 않습니다."""

from dataclasses import dataclass

from sqlalchemy import Engine

from app.companies.application.service import CompanyService
from app.companies.infrastructure.unit_of_work import CompanySQLAlchemyUnitOfWork
from app.core.config import Settings
from app.core.database.engine import create_database_engine
from app.core.database.session import create_session_factory
from app.core.security import PasswordSecurity, TokenSecurity
from app.identity.auth.application.service import AuthService
from app.identity.infrastructure.unit_of_work import IdentitySQLAlchemyUnitOfWork
from app.identity.invitations.application.service import InvitationService
from app.identity.invitations.infrastructure.unit_of_work import InvitationSQLAlchemyUnitOfWork


@dataclass(frozen=True)
class Services:
    auth: AuthService | None
    companies: CompanyService
    invitations: InvitationService


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
    return engine, Services(
        auth,
        CompanyService(lambda: CompanySQLAlchemyUnitOfWork(sessions)),
        InvitationService(lambda: InvitationSQLAlchemyUnitOfWork(sessions)),
    )
