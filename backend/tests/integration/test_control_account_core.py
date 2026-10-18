"""Mapping requests preserve company scope, versions, and deterministic impact."""

from datetime import date

import pytest

from app.accounting.control_accounts.application.service import ControlAccountService
from app.accounting.control_accounts.domain.errors import ControlAccountIdempotencyConflict
from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork
from app.contracts.access_errors import ResourceNotFound, VersionConflict

pytest_plugins = ("tests.integration.test_accounting_master_service",)


def test_request_impact_key_and_company_isolation(master):
    owner, company, accounting, _, factory, companies = master
    accounting.initialize(owner, company.id, fiscal_year=2026)
    core = ControlAccountService(lambda: MasterSQLAlchemyUnitOfWork(factory))
    target = accounting.create_account(
        owner,
        company.id,
        account_code="AR_CONTROL_NEW",
        account_name="New AR control",
        account_type="ASSET",
    )
    mapping = next(row for row in core.mappings(owner, company.id) if row["role"] == "AR")
    preview = core.preview_impact(
        owner,
        company.id,
        role="AR",
        target_account_id=target.id,
        expected_mapping_version=mapping["version"],
        expected_target_account_version=target.version,
    )
    assert not preview.blocking and len(preview.digest) == 64
    request = core.create_request(
        owner,
        company.id,
        role="AR",
        target_account_id=target.id,
        expected_mapping_version=mapping["version"],
        expected_target_account_version=target.version,
        key="request-ar-1",
    )
    assert request.impact_digest == preview.digest
    assert (
        core.create_request(
            owner,
            company.id,
            role="AR",
            target_account_id=target.id,
            expected_mapping_version=mapping["version"],
            expected_target_account_version=target.version,
            key="request-ar-1",
        ).id
        == request.id
    )
    with pytest.raises(ControlAccountIdempotencyConflict):
        core.create_request(
            owner,
            company.id,
            role="AP",
            target_account_id=target.id,
            expected_mapping_version=0,
            expected_target_account_version=target.version,
            key="request-ar-1",
        )
    with pytest.raises(VersionConflict):
        core.preview_impact(
            owner,
            company.id,
            role="AR",
            target_account_id=target.id,
            expected_mapping_version=mapping["version"] + 1,
            expected_target_account_version=target.version,
        )
    second = companies.create(
        owner,
        company_name="Isolated Control",
        business_number="9234567890",
        taxpayer_type="INDIVIDUAL",
        opening_date=date(2026, 1, 1),
        address="Seoul",
    ).company
    with pytest.raises(ResourceNotFound):
        core.request(owner, second.id, request.id)
