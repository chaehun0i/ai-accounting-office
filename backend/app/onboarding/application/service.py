"""직접 입력과 검증의 Application 경계입니다. 서버 초안이 상태의 정본입니다."""

from collections.abc import Callable
from dataclasses import replace
from uuid import UUID

from app.companies.application.service import require_company
from app.contracts.access_errors import StateConflict
from app.identity.users.domain.entities import Principal
from app.onboarding.application.contracts import OnboardingUnitOfWork
from app.onboarding.domain.catalog import BY_CODE, KEYS
from app.onboarding.domain.entities import Workspace
from app.onboarding.domain.errors import InvalidValue, StaleDraft
from app.onboarding.domain.validation import Issue, invalidate, recalculate, validate
from app.onboarding.domain.values import Cell, Scalar, editable, parse_value, row_key


class OnboardingService:
    def __init__(self, factory: Callable[[], OnboardingUnitOfWork]) -> None:
        self.factory = factory

    def workspace(
        self, uow: OnboardingUnitOfWork, actor: Principal, company: UUID, permission: str
    ) -> Workspace:
        access = require_company(uow, actor, company, permission)
        current = uow.onboarding.get(company_id=company)
        if current is not None:
            return current
        # 조회 권한만으로 다른 사용자의 초안을 생성하지 않습니다.
        require_company(uow, actor, company, "onboarding.edit")
        current = uow.onboarding.start(company, actor.user_id, uow.now())
        profile = access.company
        defaults: dict[str, object] = {
            "Company.company_name": profile.company_name,
            "Company.business_number": profile.business_number,
            "Company.taxpayer_type": profile.taxpayer_type,
            "Company.opening_date": profile.opening_date,
            "Company.timezone": profile.timezone,
            "Accounting_Settings.functional_currency_code": "KRW",
            "Accounting_Settings.fiscal_year_start_month": "1",
            "Accounting_Settings.accounting_framework_code": "K_GAAP",
            "Accounting_Settings.reporting_taxonomy_code": "STANDARD",
            "Accounting_Settings.journal_number_prefix": "J",
        }
        if profile.corporation_number:
            defaults["Company.corporation_number"] = profile.corporation_number
        settings = uow.settings.get(company)
        if settings:
            for code in tuple(defaults):
                if code.startswith("Accounting_Settings."):
                    defaults[code] = getattr(settings, code.split(".")[1])
        cells = [
            Cell(code, "singleton", parse_value(BY_CODE[code], value), "SYSTEM_DEFAULT")
            for code, value in defaults.items()
        ]
        return uow.onboarding.save(current, recalculate(cells), actor.user_id, uow.now())

    def get(self, actor: Principal, company: UUID) -> Workspace:
        with self.factory() as uow:
            return self.workspace(uow, actor, company, "onboarding.read")

    @staticmethod
    def writable(current: Workspace, expected_version: int) -> None:
        if current.status == "COMPLETED":
            raise StateConflict()
        if current.version != expected_version:
            raise StaleDraft()

    def save(
        self,
        actor: Principal,
        company: UUID,
        expected_version: int,
        values: list[tuple[str, str, object]],
    ) -> Workspace:
        if not values or len(values) > 500 or len({(f, r) for f, r, _ in values}) != len(values):
            raise InvalidValue()
        with self.factory() as uow:
            current = self.workspace(uow, actor, company, "onboarding.edit")
            self.writable(current, expected_version)
            cells = {(c.field_code, c.row_key): c for c in current.cells}
            changed: set[str] = set()
            for code, key, raw in values:
                field = editable(code)
                if len(key) > 260 or not key:
                    raise InvalidValue()
                cell = Cell(code, key, parse_value(field, raw))
                cells[(code, key)] = cell
                changed.add(field.section_code)
            for section in changed:
                for key in {
                    c.row_key
                    for c in cells.values()
                    if BY_CODE[c.field_code].section_code == section and c.source_type != "DERIVED"
                }:
                    row: dict[str, Scalar] = {
                        c.field_code.split(".")[1]: c.value
                        for c in cells.values()
                        if c.row_key == key and BY_CODE[c.field_code].section_code == section
                    }
                    if (
                        section not in KEYS
                        and key != "singleton"
                        or section in KEYS
                        and row_key(section, row) != key
                    ):
                        raise InvalidValue()
            return uow.onboarding.save(
                current, invalidate(list(cells.values()), changed), actor.user_id, uow.now()
            )

    def validate(
        self, actor: Principal, company: UUID, expected_version: int
    ) -> tuple[Workspace, list[Issue]]:
        with self.factory() as uow:
            current = self.workspace(uow, actor, company, "onboarding.edit")
            self.writable(current, expected_version)
            cells = recalculate(current.cells)
            issues = validate(cells)
            status = "REVIEW_REQUIRED" if issues else "READY_TO_COMPLETE"
            result = uow.onboarding.save(current, cells, actor.user_id, uow.now(), status=status)
            uow.onboarding.validation(result, issues, uow.now())
            return replace(result, status=status), issues
