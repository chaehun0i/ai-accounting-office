from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, update

from app.companies.application.service import CompanyService
from app.companies.infrastructure.models import (
    CompanyModel,
    MembershipModel,
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    TenantModel,
)
from app.companies.infrastructure.seed import seed_permissions
from app.companies.infrastructure.unit_of_work import CompanySQLAlchemyUnitOfWork
from app.core.database.base import Base
from app.core.database.session import create_session_factory
from app.core.security import PasswordSecurity, TokenSecurity
from app.identity.auth.application.service import AuthService
from app.identity.infrastructure.unit_of_work import IdentitySQLAlchemyUnitOfWork
from app.identity.sessions.domain.entities import RequestFacts
from app.identity.sessions.infrastructure.models import (
    IdentitySecurityEventModel,
    RefreshSessionModel,
)
from app.identity.users.domain.entities import Principal
from app.identity.users.infrastructure.models import UserModel
from app.intake.application.service import IntakeService
from app.intake.domain.canonical_fields import SourceType, TargetContext
from app.intake.infrastructure.models import ImportReceiptModel
from app.intake.infrastructure.parser import parse_file
from app.intake.infrastructure.unit_of_work import IntakeSQLAlchemyUnitOfWork
from app.storage.infrastructure.local import LocalObjectStorage


def test_concurrent_confirm_replays_one_receipt(identity_database, tmp_path: Path):
    factory = create_session_factory(identity_database)
    with factory.begin() as session:
        old_roles = set(session.scalars(select(RoleModel.code)))
        old_permissions = set(session.scalars(select(PermissionModel.code)))
        seed_permissions(session)
        new_roles = set(session.scalars(select(RoleModel.code))) - old_roles
        new_permissions = set(session.scalars(select(PermissionModel.code))) - old_permissions
    auth = AuthService(
        lambda: IdentitySQLAlchemyUnitOfWork(factory),
        PasswordSecurity(),
        TokenSecurity("intake-concurrency-only-signing-key-32-bytes"),
    )
    request_id = uuid4()
    registered = auth.register(
        f"{uuid4()}@example.com", "StrongPassword!2026", RequestFacts(request_id, "198.51.100.0/24")
    )
    with identity_database.connect() as connection:
        session_id = connection.scalar(
            select(RefreshSessionModel.id).where(RefreshSessionModel.user_id == registered.user.id)
        )
    actor = Principal(registered.user.id, session_id, registered.user.email)
    company = (
        CompanyService(lambda: CompanySQLAlchemyUnitOfWork(factory))
        .create(
            actor,
            company_name="동시 확정 검증",
            business_number="9999999999",
            taxpayer_type="CORPORATION",
            opening_date=date(2026, 1, 1),
            address="테스트 주소",
        )
        .company
    )
    with factory.begin() as session:
        session.execute(
            update(MembershipModel)
            .where(MembershipModel.company_id == company.id)
            .values(role_code="ACCOUNTANT")
        )
    intake = IntakeService(
        lambda: IntakeSQLAlchemyUnitOfWork(factory), LocalObjectStorage(tmp_path), parse_file
    )
    try:
        uploaded = intake.upload(
            actor,
            company.id,
            source=SourceType.SALES,
            target=TargetContext.TRANSACTION_CANONICAL,
            source_system="CONCURRENCY",
            filename="data.csv",
            content=b"source_id,date,amount,currency\ns1,2026-01-01,1,KRW\n",
            content_type="text/csv",
        )
        preview = intake.preview(actor, company.id, uploaded.id, 1)
        barrier = Barrier(2)

        def confirm(_: int):
            barrier.wait(timeout=20)
            return intake.confirm(
                actor,
                company.id,
                uploaded.id,
                expected_version=preview.version,
                preview_digest=preview.preview_digest,
                idempotency_key="same-command",
                confirmed=True,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(confirm, range(2)))
        assert results[0] == results[1]
        with identity_database.connect() as connection:
            assert (
                connection.scalar(
                    select(func.count())
                    .select_from(ImportReceiptModel)
                    .where(ImportReceiptModel.company_id == company.id)
                )
                == 1
            )
    finally:
        # 생성한 회사·계정의 데이터만 FK 역순으로 정리합니다.
        with identity_database.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                if table.name.startswith("import_") or table.name in {
                    "imports",
                    "evidences",
                    "storage_objects",
                }:
                    if "company_id" in table.c:
                        connection.execute(delete(table).where(table.c.company_id == company.id))
                    elif "import_id" in table.c:
                        connection.execute(delete(table).where(table.c.import_id == uploaded.id))
                    elif "import_sheet_id" in table.c:
                        sheets = Base.metadata.tables["import_sheets"]
                        connection.execute(
                            delete(table).where(
                                table.c.import_sheet_id.in_(
                                    select(sheets.c.id).where(sheets.c.import_id == uploaded.id)
                                )
                            )
                        )
            connection.execute(
                delete(MembershipModel).where(MembershipModel.company_id == company.id)
            )
            connection.execute(delete(CompanyModel).where(CompanyModel.id == company.id))
            connection.execute(delete(TenantModel).where(TenantModel.id == company.tenant_id))
            connection.execute(
                delete(IdentitySecurityEventModel).where(
                    or_(
                        IdentitySecurityEventModel.user_id == registered.user.id,
                        IdentitySecurityEventModel.request_id == request_id,
                    )
                )
            )
            connection.execute(
                delete(RefreshSessionModel).where(RefreshSessionModel.user_id == registered.user.id)
            )
            connection.execute(delete(UserModel).where(UserModel.id == registered.user.id))

            connection.execute(
                delete(RolePermissionModel).where(
                    or_(
                        RolePermissionModel.role_code.in_(new_roles),
                        RolePermissionModel.permission_code.in_(new_permissions),
                    )
                )
            )
            connection.execute(delete(RoleModel).where(RoleModel.code.in_(new_roles)))
            connection.execute(
                delete(PermissionModel).where(PermissionModel.code.in_(new_permissions))
            )
