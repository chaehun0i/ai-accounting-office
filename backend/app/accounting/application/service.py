from collections.abc import Callable
from dataclasses import replace
from uuid import UUID

from app.accounting.accounts.domain.entities import Account
from app.accounting.application.catalog import prepare_accounts
from app.accounting.application.contracts import MasterUnitOfWork
from app.accounting.domain.rules import (
    ResetPolicy,
    journal_number,
    monthly_periods,
    validate_account,
    validate_hierarchy,
)
from app.accounting.periods.domain.entities import Period
from app.accounting.settings.domain.entities import AccountingSettings
from app.accounting.templates.domain.defaults import (
    DEFAULT_ACCOUNTS,
    DEFAULT_TEMPLATE,
    LEGACY_ACCOUNTS,
    LEGACY_TEMPLATE,
    PREVIOUS_ACCOUNTS,
    PREVIOUS_TEMPLATE,
)
from app.accounting.templates.domain.entities import Template
from app.companies.application.service import require_company
from app.contracts.access_errors import (
    InvalidInput,
    ResourceNotFound,
    StateConflict,
    VersionConflict,
)
from app.identity.users.domain.entities import Principal
from app.master_data.domain.rules import validate_currency


class AccountingMasterService:
    @staticmethod
    def map_control_in(
        uow: MasterUnitOfWork, actor: Principal, company: UUID, account_id: UUID, role: str
    ) -> Account:
        require_company(uow, actor, company, "control_account.manage")
        value = uow.accounts.get(company_id=company, resource_id=account_id)
        if value is None:
            raise ResourceNotFound()
        expected_type = {"BANK_CASH": "ASSET", "CARD_PAYABLE": "LIABILITY"}.get(role)
        if (
            value.account_type != expected_type
            or value.status != "ACTIVE"
            or not value.posting_allowed
        ):
            raise InvalidInput()
        result = uow.accounts.map_control(company, account_id, role)
        assert result is not None
        return result

    def __init__(self, factory: Callable[[], MasterUnitOfWork]) -> None:
        self.factory = factory

    def settings(self, principal: Principal, company_id: UUID) -> AccountingSettings:
        with self.factory() as uow:
            require_company(uow, principal, company_id, "account.read")
            value = uow.settings.get(company_id)
            if value is None:
                raise ResourceNotFound()
            return value

    def initialize(
        self,
        principal: Principal,
        company_id: UUID,
        *,
        fiscal_year: int,
        template_id: UUID = DEFAULT_TEMPLATE.id,
        functional_currency_code: str = "KRW",
        fiscal_year_start_month: int = 1,
        numbering_reset_policy: str = "FISCAL_YEAR",
    ) -> AccountingSettings:
        validate_currency(functional_currency_code)
        if numbering_reset_policy not in ResetPolicy:
            raise InvalidInput()
        dates = monthly_periods(fiscal_year, fiscal_year_start_month)
        with self.factory() as uow:
            require_company(uow, principal, company_id, "company.accounting_settings.update")
            if template_id not in {DEFAULT_TEMPLATE.id, LEGACY_TEMPLATE.id, PREVIOUS_TEMPLATE.id}:
                raise InvalidInput()
            current = uow.settings.get(company_id)
            if current:
                accounts = uow.accounts.list(company_id)
                source_ids = {
                    row.id for row in (*DEFAULT_ACCOUNTS, *LEGACY_ACCOUNTS, *PREVIOUS_ACCOUNTS)
                }
                years = {row.fiscal_year for row in uow.periods.list(company_id)}
                if (
                    current.functional_currency_code != functional_currency_code
                    or current.fiscal_year_start_month != fiscal_year_start_month
                    or current.numbering_reset_policy != numbering_reset_policy
                    or fiscal_year not in years
                    or not accounts
                    or any(
                        row.template_account_id is not None
                        and row.template_account_id not in source_ids
                        for row in accounts
                    )
                ):
                    raise StateConflict()
                return current
            template = next((row for row in uow.templates.list() if row.id == template_id), None)
            if template is None or template.valid_from > dates[0][1]:
                raise ResourceNotFound()
            source = uow.templates.accounts(template.id)
            if not source:
                raise StateConflict()
            validate_hierarchy({row.account_code: row.parent_code for row in source})
            current = AccountingSettings(
                company_id=company_id,
                functional_currency_code=functional_currency_code,
                fiscal_year_start_month=fiscal_year_start_month,
                numbering_reset_policy=numbering_reset_policy,
                created_at=uow.now(),
                updated_at=uow.now(),
            )
            uow.settings.add(current)
            prepare_accounts(uow, company_id)
            for no, start, end in dates:
                uow.periods.add(
                    Period(
                        company_id=company_id,
                        fiscal_year=fiscal_year,
                        period_no=no,
                        start_date=start,
                        end_date=end,
                        created_at=uow.now(),
                        updated_at=uow.now(),
                    )
                )
            uow.sequences.ensure(
                company_id, fiscal_year if numbering_reset_policy == "FISCAL_YEAR" else 0, "JOURNAL"
            )
            return current

    def update_settings(
        self,
        principal: Principal,
        company_id: UUID,
        expected_version: int,
        *,
        journal_number_prefix: str | None = None,
        allow_manual_journal: bool | None = None,
    ) -> AccountingSettings:
        if journal_number_prefix is not None:
            journal_number(journal_number_prefix, 2026, 1)
        with self.factory() as uow:
            require_company(uow, principal, company_id, "company.accounting_settings.update")
            current = uow.settings.get(company_id)
            if current is None:
                raise ResourceNotFound()
            if current.version != expected_version:
                raise VersionConflict()
            value = replace(
                current,
                journal_number_prefix=journal_number_prefix
                if journal_number_prefix is not None
                else current.journal_number_prefix,
                allow_manual_journal=allow_manual_journal
                if allow_manual_journal is not None
                else current.allow_manual_journal,
                version=current.version + 1,
                updated_at=uow.now(),
            )
            if not uow.settings.update(value, expected_version):
                raise VersionConflict()
            return value

    def accounts(self, principal: Principal, company_id: UUID) -> list[Account]:
        with self.factory() as uow:
            require_company(uow, principal, company_id, "account.read")
            return uow.accounts.list(company_id)

    def create_account(
        self,
        principal: Principal,
        company_id: UUID,
        *,
        account_code: str,
        account_name: str,
        account_type: str,
        is_contra: bool = False,
        parent_account_id: UUID | None = None,
    ) -> Account:
        """인증된 회사 범위에 사용자 계정을 추가하며 기본 목록은 변경하지 않습니다."""
        import re

        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,19}", account_code):
            raise InvalidInput()
        account_name = account_name.strip()
        if not account_name or len(account_name) > 200:
            raise InvalidInput()
        debit = (account_type in {"ASSET", "EXPENSE"}) != is_contra
        normal_balance = "DEBIT" if debit else "CREDIT"
        validate_account(account_type, normal_balance, is_contra)
        with self.factory() as uow:
            require_company(uow, principal, company_id, "account.create")
            current = uow.accounts.list(company_id)
            if any(row.account_code == account_code for row in current):
                raise StateConflict()
            if parent_account_id is not None:
                parent = uow.accounts.get(company_id=company_id, resource_id=parent_account_id)
                if parent is None:
                    raise ResourceNotFound()
                if parent.status != "ACTIVE" or parent.account_type != account_type:
                    raise InvalidInput()
            value = Account(
                company_id=company_id,
                account_code=account_code,
                account_name=account_name,
                account_type=account_type,
                normal_balance=normal_balance,
                is_contra=is_contra,
                parent_account_id=parent_account_id,
                posting_allowed=True,
                created_at=uow.now(),
                updated_at=uow.now(),
            )
            uow.accounts.add(value)
            return value

    def periods(self, principal: Principal, company_id: UUID) -> list[Period]:
        with self.factory() as uow:
            require_company(uow, principal, company_id, "period.read")
            return uow.periods.list(company_id)

    def templates(self, principal: Principal, company_id: UUID) -> list[Template]:
        with self.factory() as uow:
            require_company(uow, principal, company_id, "account.read")
            return uow.templates.list()
