"""고정 계정목록의 회사별 준비와 재실행 안전성을 검증합니다."""

from typing import cast

import pytest

from app.accounting.application.catalog import prepare_accounts
from app.accounting.application.contracts import MasterUnitOfWork
from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork
from app.accounting.templates.domain.defaults import DEFAULT_ACCOUNTS
from app.companies.application.contracts import CompanyUnitOfWork
from app.companies.application.service import CompanyService
from app.contracts.access_errors import InvalidInput, StateConflict
from app.onboarding.application.service import OnboardingService
from app.onboarding.domain.errors import InvalidValue
from app.onboarding.infrastructure.unit_of_work import OnboardingSQLAlchemyUnitOfWork

pytest_plugins = ("tests.integration.test_accounting_master_service",)


def test_company_accounts_are_prepared_before_fiscal_setup(master):
    principal, first, accounting, _, factory, _ = master

    def provision(uow: CompanyUnitOfWork, company) -> None:
        prepare_accounts(cast(MasterUnitOfWork, uow), company)

    companies = CompanyService(lambda: MasterSQLAlchemyUnitOfWork(factory), provision)
    second = companies.create(
        principal,
        company_name="기본 계정 제공 회사",
        business_number="2234567890",
        taxpayer_type="INDIVIDUAL",
        opening_date=first.opening_date,
        address="테스트 주소",
    ).company
    before = accounting.accounts(principal, second.id)
    assert {row.account_code for row in before} == {row.account_code for row in DEFAULT_ACCOUNTS}
    assert not accounting.periods(principal, second.id)
    with MasterSQLAlchemyUnitOfWork(factory) as uow:
        assert prepare_accounts(uow, second.id) == 0
    accounting.initialize(principal, second.id, fiscal_year=2026)
    assert accounting.accounts(principal, second.id) == before
    assert len(accounting.periods(principal, second.id)) == 12
    assert not accounting.accounts(principal, first.id)
    onboarding = OnboardingService(lambda: OnboardingSQLAlchemyUnitOfWork(factory))
    workspace = onboarding.get(principal, second.id)
    assert len([cell for cell in workspace.cells if cell.field_code == "COA.account_code"]) == len(
        DEFAULT_ACCOUNTS
    )
    with pytest.raises(InvalidValue):
        onboarding.save(
            principal, second.id, workspace.version, [("COA.account_name", "1020", "변경")]
        )
    assert onboarding.get(principal, second.id) == workspace


def test_client_cannot_select_arbitrary_account_template(master):
    principal, company, accounting, _, _, _ = master
    with pytest.raises(InvalidInput):
        accounting.initialize(principal, company.id, fiscal_year=2026, template_id=company.id)


def test_account_preparation_failure_rolls_back_company_and_membership(master):
    principal, first, _, _, factory, _ = master

    def fail_after_accounts(uow: CompanyUnitOfWork, company) -> None:
        prepare_accounts(cast(MasterUnitOfWork, uow), company)
        raise StateConflict()

    companies = CompanyService(lambda: MasterSQLAlchemyUnitOfWork(factory), fail_after_accounts)
    before = companies.list(principal)
    with pytest.raises(StateConflict):
        companies.create(
            principal,
            company_name="생성 실패 테스트",
            business_number="3234567890",
            taxpayer_type="INDIVIDUAL",
            opening_date=first.opening_date,
            address="테스트 주소",
        )
    assert companies.list(principal) == before


def test_catalog_upgrade_preserves_existing_account_ids_and_template_references(master):
    from sqlalchemy import delete
    from sqlalchemy.orm import Session

    from app.accounting.accounts.infrastructure.models import AccountModel
    from app.accounting.templates.domain.defaults import LEGACY_ACCOUNTS

    principal, company, accounting, _, factory, _ = master
    settings = accounting.initialize(principal, company.id, fiscal_year=2026)
    legacy = {row.account_code: row for row in LEGACY_ACCOUNTS}
    with Session(factory.kw["bind"], join_transaction_mode="create_savepoint") as session:
        session.execute(
            delete(AccountModel).where(
                AccountModel.company_id == company.id,
                AccountModel.account_code.not_in(legacy),
            )
        )
        from sqlalchemy import select

        for account in session.scalars(
            select(AccountModel).where(AccountModel.company_id == company.id)
        ):
            account.template_account_id = legacy[account.account_code].id
        session.commit()
    before = {row.account_code: row for row in accounting.accounts(principal, company.id)}
    assert len(before) == len(LEGACY_ACCOUNTS)
    with MasterSQLAlchemyUnitOfWork(factory) as uow:
        assert prepare_accounts(uow, company.id) == len(DEFAULT_ACCOUNTS) - len(LEGACY_ACCOUNTS)
    after = {row.account_code: row for row in accounting.accounts(principal, company.id)}
    for code, account in before.items():
        assert after[code] == account
    assert accounting.initialize(principal, company.id, fiscal_year=2026) == settings
    with MasterSQLAlchemyUnitOfWork(factory) as uow:
        assert prepare_accounts(uow, company.id) == 0
