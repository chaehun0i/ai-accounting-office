"""회계정책과 계정 승격은 하나의 외부 Application UoW에 참여합니다."""

from dataclasses import replace

from app.accounting.accounts.domain.entities import Account
from app.accounting.application.contracts import MasterUnitOfWork
from app.accounting.domain.rules import journal_number, monthly_periods, validate_account
from app.accounting.periods.domain.entities import Period
from app.accounting.settings.domain.entities import AccountingSettings
from app.companies.application.service import require_company
from app.contracts.access_errors import StateConflict, VersionConflict
from app.identity.users.domain.entities import Principal


def promote_accounting(
    uow: MasterUnitOfWork,
    actor: Principal,
    settings: AccountingSettings,
    accounts: list[Account],
    fiscal_year: int,
) -> int:
    current = uow.settings.get(settings.company_id)
    journal_number(settings.journal_number_prefix, fiscal_year, 1)
    keys = (
        "functional_currency_code",
        "fiscal_year_start_month",
        "journal_number_prefix",
        "accounting_framework_code",
        "reporting_taxonomy_code",
    )
    if current is None:
        require_company(uow, actor, settings.company_id, "company.accounting_settings.update")
        uow.settings.add(settings)
    elif any(getattr(current, key) != getattr(settings, key) for key in keys):
        require_company(uow, actor, settings.company_id, "company.accounting_settings.update")
        if (
            uow.periods.list(settings.company_id)
            and current.fiscal_year_start_month != settings.fiscal_year_start_month
        ):
            raise StateConflict()
        updated = replace(
            current,
            **{key: getattr(settings, key) for key in keys},
            version=current.version + 1,
            updated_at=uow.now(),
        )
        if not uow.settings.update(updated, current.version):
            raise VersionConflict()
    known = {a.account_code: a for a in uow.accounts.list(settings.company_id)}
    count = 0
    for value in accounts:
        # 서버에서 준비한 회사 계정목록은 온보딩으로 확장하거나 덮어쓰지 않습니다.
        if known and value.account_code not in known:
            raise StateConflict()
        validate_account(value.account_type, value.normal_balance, value.is_contra)
        existing = known.get(value.account_code)
        if existing:
            if any(
                getattr(existing, key) != getattr(value, key)
                for key in ("account_name", "account_type", "normal_balance", "posting_allowed")
            ):
                raise StateConflict()
        else:
            require_company(uow, actor, settings.company_id, "account.create")
            uow.accounts.add(value)
            count += 1
    if not uow.periods.list(settings.company_id):
        for number, start, end in monthly_periods(fiscal_year, settings.fiscal_year_start_month):
            uow.periods.add(
                Period(
                    company_id=settings.company_id,
                    fiscal_year=fiscal_year,
                    period_no=number,
                    start_date=start,
                    end_date=end,
                    created_at=uow.now(),
                    updated_at=uow.now(),
                )
            )
        uow.sequences.ensure(settings.company_id, fiscal_year, "GENERAL")
    return count
