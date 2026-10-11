"""보조부는 확정된 회계 사실을 읽으며 전표를 직접 수정하지 않습니다."""

from uuid import UUID

from app.accounting.journals.application.contracts import JournalUnitOfWork
from app.accounting.journals.domain.entities import Journal
from app.accounting.journals.domain.errors import AccountingError
from app.contracts.access_errors import ResourceNotFound


def posted_journal(uow: JournalUnitOfWork, company: UUID, resource: UUID) -> Journal:
    value = uow.journals.get(company, resource, lock=True)
    if value is None:
        raise ResourceNotFound()
    if value.status != "POSTED":
        raise AccountingError(
            "JOURNAL_NOT_POSTED", "승인 후 장부에 반영된 전표를 선택해 주세요.", 409
        )
    return value
