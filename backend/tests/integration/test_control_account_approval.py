"""The approval is independent from the requester and consumes current facts once."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.accounting.control_accounts.application.approval import ControlAccountApproval
from app.accounting.control_accounts.application.service import ControlAccountService
from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork
from app.companies.infrastructure.models import MembershipModel
from app.contracts.access_errors import (
    AuthorizationDenied,
    ResourceNotFound,
    StateConflict,
    VersionConflict,
)
from app.identity.sessions.domain.entities import RequestFacts

pytest_plugins = ("tests.integration.test_accounting_master_service",)


def _actors(master, auth_service):
    owner, company, accounting, _, factory, _ = master
    auth, connection = auth_service
    registered = auth.register(
        "approval-admin@example.com",
        "StrongPassword!2026",
        RequestFacts(uuid4(), "192.0.2.0/24", None),
    )
    admin = auth.authenticate(registered.access_token)
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        session.add(
            MembershipModel(
                id=uuid4(),
                company_id=company.id,
                user_id=admin.user_id,
                role_code="ADMIN",
                status="ACTIVE",
                joined_at=datetime.now(UTC),
                version=1,
            )
        )
        session.commit()
    accounting.initialize(owner, company.id, fiscal_year=2026)
    target = accounting.create_account(
        owner,
        company.id,
        account_code="CTRL_AR_NEW",
        account_name="Receivables control",
        account_type="ASSET",
    )
    core = ControlAccountService(lambda: MasterSQLAlchemyUnitOfWork(factory))
    approval = ControlAccountApproval(lambda: MasterSQLAlchemyUnitOfWork(factory))
    return owner, admin, company.id, target, core, approval


def _ar_version(core, owner, company):
    return next(row["version"] for row in core.mappings(owner, company) if row["role"] == "AR")


def test_approval_execute_replay_and_audit(master, auth_service):
    owner, admin, company, target, core, approval = _actors(master, auth_service)
    request = core.create_request(
        owner,
        company,
        role="AR",
        target_account_id=target.id,
        expected_mapping_version=_ar_version(core, owner, company),
        expected_target_account_version=target.version,
        key="ar-request-1",
    )
    with pytest.raises(AuthorizationDenied):
        approval.approve(owner, company, request.id, 1)
    approved = approval.approve(admin, company, request.id, 1)
    assert approved.status == "APPROVED" and approved.version == 2
    with pytest.raises(AuthorizationDenied):
        approval.execute(owner, company, request.id, 2, "ar-execute-1")
    executed = approval.execute(admin, company, request.id, 2, "ar-execute-1")
    assert executed.status == "EXECUTED" and executed.version == 3
    assert approval.execute(admin, company, request.id, 2, "ar-execute-1").id == request.id
    with pytest.raises(StateConflict):
        approval.execute(admin, company, request.id, 2, "different-key")
    assert (
        next(row for row in core.mappings(owner, company) if row["role"] == "AR")["account_id"]
        == target.id
    )
    assert [row.event_type for row in approval.events(owner, company, request.id)] == [
        "REQUESTED",
        "APPROVED",
        "EXECUTED",
    ]


def test_reject_and_stale_target(master, auth_service):
    owner, admin, company, target, core, approval = _actors(master, auth_service)
    request = core.create_request(
        owner,
        company,
        role="AR",
        target_account_id=target.id,
        expected_mapping_version=_ar_version(core, owner, company),
        expected_target_account_version=target.version,
        key="ar-request-2",
    )
    rejected = approval.reject(admin, company, request.id, 1, "Not justified")
    assert rejected.status == "REJECTED"
    assert approval.events(owner, company, request.id)[-1].reason == "Not justified"
    with pytest.raises(StateConflict):
        approval.execute(admin, company, request.id, 2, "reject-execute")
    pending = core.create_request(
        owner,
        company,
        role="AR",
        target_account_id=target.id,
        expected_mapping_version=_ar_version(core, owner, company),
        expected_target_account_version=target.version,
        key="ar-request-3",
    )
    approved = approval.approve(admin, company, pending.id, 1)
    # Any target-account edit invalidates both the frozen version and impact digest.
    _, _, accounting, _, _, _ = master
    accounting.update_account(owner, company, target.id, target.version, account_name="Changed")
    with pytest.raises(VersionConflict):
        approval.execute(admin, company, pending.id, approved.version, "stale-execute")


def test_competing_role_change_invalidates_approval(master, auth_service):
    owner, admin, company, target, core, approval = _actors(master, auth_service)
    _, _, accounting, _, _, companies = master
    competitor = accounting.create_account(
        owner,
        company,
        account_code="CTRL_AR_ALT",
        account_name="Alternative receivables control",
        account_type="ASSET",
    )
    version = _ar_version(core, owner, company)
    first = core.create_request(
        owner,
        company,
        role="AR",
        target_account_id=target.id,
        expected_mapping_version=version,
        expected_target_account_version=target.version,
        key="first-role-change",
    )
    second = core.create_request(
        owner,
        company,
        role="AR",
        target_account_id=competitor.id,
        expected_mapping_version=version,
        expected_target_account_version=competitor.version,
        key="second-role-change",
    )
    approved_first = approval.approve(admin, company, first.id, 1)
    approved_second = approval.approve(admin, company, second.id, 1)
    approval.execute(admin, company, first.id, approved_first.version, "first-execution")
    with pytest.raises(VersionConflict):
        approval.execute(admin, company, second.id, approved_second.version, "stale-execution")
    foreign = companies.create(
        owner,
        company_name="Other company",
        business_number="3234567890",
        taxpayer_type="INDIVIDUAL",
        opening_date=date(2026, 1, 1),
        address="Other location",
    ).company
    with pytest.raises(ResourceNotFound):
        approval.events(owner, foreign.id, first.id)
