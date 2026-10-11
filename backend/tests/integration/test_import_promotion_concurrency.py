from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, or_, select, update

from app.accounting.settings.infrastructure.models import AccountingSettingsModel
from app.accounting.transactions.infrastructure.models import TransactionModel
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
from app.intake.infrastructure.parser import parse_file
from app.intake.infrastructure.unit_of_work import IntakeSQLAlchemyUnitOfWork
from app.intake.promotion.application.service import PromotionService
from app.intake.promotion.infrastructure.unit_of_work import PromotionSQLAlchemyUnitOfWork
from app.storage.infrastructure.local import LocalObjectStorage


@pytest.mark.parametrize("mode", ["same-key", "different-key", "different-import"])
def test_concurrent_promotion_has_one_transaction(identity_database, tmp_path: Path, mode):
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
        with factory.begin() as session:
            session.add(
                AccountingSettingsModel(
                    company_id=company.id,
                    functional_currency_code="KRW",
                    fiscal_year_start_month=1,
                    journal_number_prefix="JE",
                    numbering_reset_policy="FISCAL_YEAR",
                    allow_manual_journal=True,
                )
            )
        promotion = PromotionService(lambda: PromotionSQLAlchemyUnitOfWork(factory), intake)
        uploads = []
        receipts = []
        for n in range(2 if mode == "different-import" else 1):
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
            draft = intake.preview(actor, company.id, uploaded.id, 1)
            receipt = intake.confirm(
                actor,
                company.id,
                uploaded.id,
                expected_version=draft.version,
                preview_digest=draft.preview_digest,
                idempotency_key=f"confirm-{n}",
                confirmed=True,
            )
            uploads.append(uploaded)
            receipts.append(receipt)
        barrier = Barrier(2)

        def promote(n):
            index = n if mode == "different-import" else 0
            barrier.wait(timeout=20)
            return promotion.promote(
                actor,
                company.id,
                uploads[index].id,
                expected_version=receipts[index].confirmed_version,
                receipt_id=receipts[index].id,
                source_digest=receipts[index].source_digest,
                idempotency_key="same-key" if mode == "same-key" else f"key-{n}",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(promote, range(2)))
        assert all(r.transaction_count == 1 for r in results)
        assert results[0].rows[0].transaction_id == results[1].rows[0].transaction_id
        with identity_database.connect() as connection:
            assert (
                connection.scalar(
                    select(func.count())
                    .select_from(TransactionModel)
                    .where(TransactionModel.company_id == company.id)
                )
                == 1
            )
    finally:
        # 생성한 회사·계정의 데이터만 FK 역순으로 정리합니다.
        with identity_database.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                if table.name not in {"companies", "company_memberships"}:
                    if "company_id" in table.c:
                        connection.execute(delete(table).where(table.c.company_id == company.id))
                    elif "import_id" in table.c:
                        connection.execute(
                            delete(table).where(table.c.import_id.in_([v.id for v in uploads]))
                        )
                    elif "import_sheet_id" in table.c:
                        sheets = Base.metadata.tables["import_sheets"]
                        connection.execute(
                            delete(table).where(
                                table.c.import_sheet_id.in_(
                                    select(sheets.c.id).where(
                                        sheets.c.import_id.in_([v.id for v in uploads])
                                    )
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
