"""온보딩 기초잔액을 불변 입력 스냅샷과 승인 대상 전표 초안으로 연결합니다."""

import re
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol
from uuid import UUID, uuid4

from app.accounting.journals.application.service import validate_journal
from app.accounting.journals.domain.entities import Journal, JournalLine
from app.accounting.journals.domain.errors import AccountingError
from app.approvals.application.contracts import AccountingUnitOfWork
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, VersionConflict
from app.identity.users.domain.entities import Principal
from app.intake.domain.digest import digest
from app.onboarding.domain.entities import Workspace


class DraftReader(Protocol):
    def get(self, *, company_id: UUID) -> Workspace | None: ...


class OpeningStore(Protocol):
    def evidence_ids(self, company: UUID, session_id: UUID) -> tuple[UUID, ...]: ...

    def existing(self, company: UUID, session_id: UUID, version: int) -> UUID | None: ...
    def add(
        self,
        journal: Journal,
        session_id: UUID,
        version: int,
        fingerprint: str,
        row_keys: tuple[str, ...],
        now: datetime,
    ) -> None: ...


class OpeningUnitOfWork(AccountingUnitOfWork, Protocol):
    @property
    def onboarding(self) -> DraftReader: ...
    @property
    def openings(self) -> OpeningStore: ...


class OpeningService:
    def __init__(self, factory: Callable[[], OpeningUnitOfWork]) -> None:
        self.factory = factory

    def create(self, actor: Principal, company: UUID, expected_version: int, key: str) -> Journal:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidInput()
        fingerprint = digest({"version": expected_version, "command": "opening-journal-v1"})
        with self.factory() as uow:
            require_company(uow, actor, company, "journal.propose")
            require_company(uow, actor, company, "onboarding.read")
            replay = uow.governance.replay(
                company, actor.user_id, "opening.create", key, fingerprint
            )
            if replay:
                journal = uow.journals.get(company, replay)
                if journal is None:
                    raise ResourceNotFound()
                return journal
            draft = uow.onboarding.get(company_id=company)
            if draft is None:
                raise ResourceNotFound()
            if draft.version != expected_version:
                raise VersionConflict()
            previous = uow.openings.existing(company, draft.id, draft.version)
            if previous:
                journal = uow.journals.get(company, previous)
                if journal is None:
                    raise ResourceNotFound()
                return journal
            values = {(c.field_code, c.row_key): c.value for c in draft.cells}
            keys = sorted(
                {c.row_key for c in draft.cells if c.field_code == "Opening_Balances.account_code"}
            )
            if not keys:
                raise AccountingError("BUSINESS_RULE_VIOLATION", "입력된 기초잔액이 없습니다.")
            accounts = {a.account_code: a for a in uow.accounts.list(company)}
            counterparties = {c.counterparty_code: c for c in uow.counterparties.list(company)}
            lines: list[JournalLine] = []
            dates: set[date] = set()
            for key in keys:

                def value(code: str, row_key: str = key) -> object:
                    return values.get(("Opening_Balances." + code, row_key))

                try:
                    day = date.fromisoformat(str(value("as_of_date")))
                    account = accounts[str(value("account_code"))]
                    debit = Decimal(str(value("debit_amount") or "0"))
                    credit = Decimal(str(value("credit_amount") or "0"))
                except (ValueError, KeyError, InvalidOperation):
                    raise InvalidInput() from None
                if value("currency_code") not in (None, "", "KRW"):
                    raise AccountingError("FX_NOT_SUPPORTED", "기초잔액은 원화만 지원합니다.")
                dates.add(day)
                cp = value("counterparty_code")
                if cp and str(cp) not in counterparties:
                    raise ResourceNotFound()
                lines.append(
                    JournalLine(
                        id=uuid4(),
                        line_no=len(lines) + 1,
                        account_id=account.id,
                        counterparty_id=counterparties[str(cp)].id if cp else None,
                        debit_amount=debit,
                        credit_amount=credit,
                        memo="온보딩 기초잔액",
                    )
                )
            if len(dates) != 1:
                raise AccountingError(
                    "BUSINESS_RULE_VIOLATION", "기초잔액 기준일을 하나로 맞춰 주세요."
                )
            day = dates.pop()
            period = next(
                (p for p in uow.periods.list(company) if p.start_date <= day <= p.end_date), None
            )
            if period is None:
                raise AccountingError(
                    "PERIOD_NOT_OPEN", "기초잔액 기준일의 회계기간을 먼저 준비해 주세요.", 409
                )
            now = uow.now()
            journal = Journal(
                id=uuid4(),
                company_id=company,
                accounting_period_id=period.id,
                entry_date=day,
                description="온보딩 기초잔액",
                source_type="OPENING",
                proposal_origin="HUMAN",
                status="DRAFT",
                version=1,
                created_by=actor.user_id,
                created_at=now,
                updated_at=now,
                lines=tuple(lines),
                evidence_ids=uow.openings.evidence_ids(company, draft.id),
            )
            validate_journal(uow, journal)
            uow.journals.add(journal)
            source_digest = digest(
                {
                    "version": draft.version,
                    "cells": sorted(
                        (c.field_code, c.row_key, str(c.value))
                        for c in draft.cells
                        if c.field_code.startswith("Opening_Balances.")
                    ),
                }
            )
            uow.openings.add(journal, draft.id, draft.version, source_digest, tuple(keys), now)
            uow.governance.record(
                company, actor.user_id, "opening.create", key, fingerprint, journal.id, 1, now
            )
            uow.governance.audit(
                company,
                actor.user_id,
                "opening.create",
                journal.id,
                "",
                fingerprint,
                fingerprint,
                now,
            )
            return journal
