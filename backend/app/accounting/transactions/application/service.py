"""원천 중복과 회사 범위를 변경 전 검증하고 UoW에 저장을 위임합니다."""

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from uuid import UUID

from app.accounting.transactions.application.contracts import TransactionUnitOfWork
from app.accounting.transactions.domain.entities import Transaction
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, VersionConflict
from app.identity.users.domain.entities import Principal
from app.intake.domain.errors import IdempotencyConflict


class TransactionService:
    def __init__(self, factory: Callable[[], TransactionUnitOfWork]) -> None:
        self.factory = factory

    def list(
        self, actor: Principal, company: UUID, date_from: date, date_to: date
    ) -> list[Transaction]:
        if date_from > date_to:
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "transaction.read")
            return uow.transactions.list(company, date_from, date_to)

    def get(self, actor: Principal, company: UUID, resource: UUID) -> Transaction:
        with self.factory() as uow:
            require_company(uow, actor, company, "transaction.read")
            value = uow.transactions.get(company, resource)
            if value is None:
                raise ResourceNotFound()
            return value

    def save(
        self, actor: Principal, value: Transaction, expected_version: int | None = None
    ) -> Transaction:
        with self.factory() as uow:
            require_company(
                uow,
                actor,
                value.company_id,
                "transaction.create" if expected_version is None else "transaction.update",
            )
            settings = uow.settings.get(value.company_id)
            if (
                settings is None
                or value.currency_code != settings.functional_currency_code
                or value.currency_code != "KRW"
            ):
                raise InvalidInput()
            if (
                value.counterparty_id
                and uow.counterparties.get(
                    company_id=value.company_id, resource_id=value.counterparty_id
                )
                is None
            ):
                raise ResourceNotFound()
            for kind, resource in [("import", value.import_id), ("evidence", value.evidence_id)]:
                if resource and not uow.reference_exists(value.company_id, kind, resource):
                    raise ResourceNotFound()
            if expected_version is None:
                old = uow.transactions.source(
                    value.company_id, value.source_system, value.source_id
                )
                if old:
                    if old.source_fingerprint != value.source_fingerprint:
                        raise IdempotencyConflict()
                    return old
                uow.transactions.add(value)
            else:
                old = uow.transactions.get(value.company_id, value.id, lock=True)
                if old is None:
                    raise ResourceNotFound()
                if old.version != expected_version:
                    raise VersionConflict()
                # 회계 연결 후 원천 사실 변경은 후속 correction 명령으로만 허용합니다.
                if old.status != "READY_FOR_ACCOUNTING" or uow.has_journal(
                    value.company_id, value.id
                ):
                    raise InvalidInput()
                value = replace(
                    old,
                    description=value.description,
                    version=old.version + 1,
                    updated_at=uow.now(),
                )
                if not uow.transactions.update(value, expected_version):
                    raise VersionConflict()
            return value
