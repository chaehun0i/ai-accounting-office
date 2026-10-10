"""전표 초안의 검증과 저장을 조정합니다. 확정 전표는 변경하지 않습니다."""

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from uuid import UUID

from app.accounting.journals.application.contracts import JournalUnitOfWork
from app.accounting.journals.domain.entities import Journal, totals, validate_lines
from app.accounting.journals.domain.errors import AccountingError
from app.companies.application.service import require_company
from app.contracts.access_errors import ResourceNotFound, VersionConflict
from app.identity.users.domain.entities import Principal


def validate_journal(uow: JournalUnitOfWork, value: Journal, *, balanced: bool = True) -> None:
    if (value.source_type == "TRANSACTION") != (value.source_transaction_id is not None):
        raise AccountingError(
            "BUSINESS_RULE_VIOLATION", "거래 출처와 연결 거래를 함께 확인해 주세요."
        )
    validate_lines(value.lines, balanced=balanced)
    uow.lock_period(value.company_id, value.accounting_period_id)
    period = uow.periods.get(company_id=value.company_id, resource_id=value.accounting_period_id)
    if period is None:
        raise ResourceNotFound()
    if period.status != "OPEN" or not period.start_date <= value.entry_date <= period.end_date:
        raise AccountingError(
            "PERIOD_NOT_OPEN", "전표 날짜에 해당하는 열린 회계기간을 선택해 주세요.", 409
        )
    uow.lock_accounts(value.company_id, tuple(line.account_id for line in value.lines))
    for line in value.lines:
        account = uow.accounts.get(company_id=value.company_id, resource_id=line.account_id)
        if account is None:
            raise ResourceNotFound()
        if account.status != "ACTIVE":
            raise AccountingError("ACCOUNT_INACTIVE", "비활성 계정은 분개에 사용할 수 없습니다.")
        if not account.posting_allowed:
            raise AccountingError(
                "ACCOUNT_NOT_POSTABLE", "집계용 계정에는 분개를 입력할 수 없습니다."
            )
        if (
            line.counterparty_id
            and uow.counterparties.get(
                company_id=value.company_id, resource_id=line.counterparty_id
            )
            is None
        ):
            raise ResourceNotFound()
    for evidence in value.evidence_ids:
        if not uow.reference_exists(value.company_id, "evidence", evidence):
            raise ResourceNotFound()
    if value.source_transaction_id:
        source = uow.transactions.get(value.company_id, value.source_transaction_id, lock=True)
        if source is None:
            raise ResourceNotFound()
        if balanced and totals(value.lines)[0] != source.amount:
            raise AccountingError(
                "BUSINESS_RULE_VIOLATION", "전표 합계가 연결된 거래 금액과 일치하지 않습니다."
            )
        if source.status != "READY_FOR_ACCOUNTING":
            raise AccountingError(
                "BUSINESS_RULE_VIOLATION", "회계 처리 준비가 된 거래만 연결할 수 있습니다."
            )
    settings = uow.settings.get(value.company_id)
    if settings is None or (value.source_type == "MANUAL" and not settings.allow_manual_journal):
        raise AccountingError(
            "BUSINESS_RULE_VIOLATION", "회사의 수동 전표 입력 설정을 확인해 주세요."
        )


class JournalService:
    def __init__(self, factory: Callable[[], JournalUnitOfWork]) -> None:
        self.factory = factory

    def get(self, actor: Principal, company: UUID, resource: UUID) -> Journal:
        with self.factory() as uow:
            require_company(uow, actor, company, "journal.read")
            value = uow.journals.get(company, resource)
            if value is None:
                raise ResourceNotFound()
            return value

    def list(
        self, actor: Principal, company: UUID, date_from: date, date_to: date
    ) -> list[Journal]:
        with self.factory() as uow:
            require_company(uow, actor, company, "journal.read")
            return uow.journals.list(company, date_from, date_to)

    def save(
        self, actor: Principal, value: Journal, expected_version: int | None = None
    ) -> Journal:
        with self.factory() as uow:
            require_company(uow, actor, value.company_id, "journal.propose")
            if expected_version is not None:
                old = uow.journals.get(value.company_id, value.id, lock=True)
                if old is None:
                    raise ResourceNotFound()
                if old.status == "POSTED":
                    raise AccountingError(
                        "POSTED_JOURNAL_IMMUTABLE",
                        "확정된 전표는 수정할 수 없습니다. 역분개를 이용해 주세요.",
                        409,
                    )
                if old.source_type in ("OPENING", "REVERSAL"):
                    raise AccountingError(
                        "BUSINESS_RULE_VIOLATION",
                        "원천에서 생성된 기초·역분개 초안은 직접 수정할 수 없습니다.",
                        409,
                    )
                if old.status != "DRAFT":
                    raise AccountingError(
                        "STATE_TRANSITION_NOT_ALLOWED", "작성 중인 전표만 수정할 수 있습니다.", 409
                    )
                if old.version != expected_version:
                    raise VersionConflict()
                value = replace(
                    value,
                    version=old.version + 1,
                    created_by=old.created_by,
                    created_at=old.created_at,
                    updated_at=uow.now(),
                )
            validate_journal(uow, value, balanced=False)
            if expected_version is None:
                uow.journals.add(value)
            elif not uow.journals.update(value, expected_version, replace_lines=True):
                raise VersionConflict()
            return value
