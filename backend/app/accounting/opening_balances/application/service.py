"""온보딩 기초잔액을 불변 입력 스냅샷과 승인 대상 전표 초안으로 연결합니다."""

import re
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol
from uuid import UUID, uuid4

from app.accounting.journals.application.posted_facts import posted_journal
from app.accounting.journals.application.service import validate_journal
from app.accounting.journals.domain.entities import Journal, JournalLine
from app.accounting.journals.domain.errors import AccountingError
from app.accounting.opening_balances.application.ar_ap_preview import ArApPreview, preview_ar_ap
from app.approvals.application.contracts import AccountingUnitOfWork
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, VersionConflict
from app.finance.receivables.domain.entities import Obligation
from app.identity.users.domain.entities import Principal
from app.intake.domain.digest import digest
from app.onboarding.domain.entities import Workspace


class DraftReader(Protocol):
    def get(self, *, company_id: UUID) -> Workspace | None: ...


class OpeningStore(Protocol):
    def evidence_ids(self, company: UUID, session_id: UUID) -> tuple[UUID, ...]: ...

    def existing(self, company: UUID, session_id: UUID) -> tuple[UUID, int, str] | None: ...
    def for_promotion(self, company: UUID, session_id: UUID) -> "PromotionRecord | None": ...
    def add(
        self,
        journal: Journal,
        session_id: UUID,
        version: int,
        fingerprint: str,
        row_keys: tuple[str, ...],
        now: datetime,
    ) -> None: ...


class PromotionRecord(Protocol):
    id: UUID
    journal_id: UUID
    as_of_date: date
    source_version: int
    source_digest: str
    ar_ap_digest: str | None
    ar_ap_promoted_at: datetime | None


class OpeningUnitOfWork(AccountingUnitOfWork, Protocol):
    @property
    def onboarding(self) -> DraftReader: ...
    @property
    def openings(self) -> OpeningStore: ...
    def obligations(self, kind: str) -> "OpeningObligations": ...


class OpeningObligations(Protocol):
    def opening_items(self, company: UUID, opening_import: UUID) -> list[Obligation]: ...

    def origin(self, company: UUID, journal: UUID, line_no: int) -> Obligation | None: ...

    def add_opening(
        self,
        company: UUID,
        opening_import: UUID,
        journal: UUID,
        row_key: str,
        reference: str,
        counterparty: UUID,
        account: UUID,
        amount: Decimal,
        due: date,
        recognized: date,
    ) -> UUID: ...


def active_source_counterparties(
    uow: OpeningUnitOfWork, draft: Workspace, company: UUID
) -> dict[str, UUID]:
    codes = {
        str(cell.value)
        for cell in draft.cells
        if cell.field_code.endswith(".counterparty_code")
        and cell.field_code.split(".", 1)[0] in ("Opening_Balances", "AR_Opening", "AP_Opening")
    }
    return {
        code: cp.id
        for code in codes
        if (cp := uow.counterparties.by_code(company_id=company, code=code)) is not None
        and cp.status == "ACTIVE"
    }


class OpeningService:
    def __init__(self, factory: Callable[[], OpeningUnitOfWork]) -> None:
        self.factory = factory

    def ar_ap_preview(self, actor: Principal, company: UUID, expected_version: int) -> ArApPreview:
        with self.factory() as uow:
            require_company(uow, actor, company, "onboarding.read")
            draft = uow.onboarding.get(company_id=company)
            if draft is None:
                raise ResourceNotFound()
            if draft.version != expected_version:
                raise VersionConflict()
            accounts = {account.id: account.account_code for account in uow.accounts.list(company)}
            mappings = {
                role: accounts[mapping.account_id]
                for role in ("AR", "AP")
                if (mapping := uow.control_accounts.mapping(company, role)) is not None
                and mapping.account_id in accounts
            }
            counterparties = active_source_counterparties(uow, draft, company)
            return preview_ar_ap(draft.cells, draft.version, mappings, set(counterparties))

    def promote_ar_ap(
        self, actor: Principal, company: UUID, expected_version: int, expected_digest: str
    ) -> tuple[UUID, tuple[Obligation, ...], tuple[Obligation, ...]]:
        with self.factory() as uow:
            require_company(uow, actor, company, "onboarding.read")
            require_company(uow, actor, company, "journal.propose")
            draft = uow.onboarding.get(company_id=company)
            if draft is None:
                raise ResourceNotFound()
            if draft.version != expected_version:
                raise VersionConflict()
            opening = uow.openings.for_promotion(company, draft.id)
            if opening is None:
                raise AccountingError(
                    "OPENING_NOT_FOUND", "기초잔액 전표를 먼저 생성해 주세요.", 409
                )
            journal = posted_journal(uow, company, opening.journal_id)
            if journal.source_type != "OPENING" or journal.entry_date != opening.as_of_date:
                raise AccountingError(
                    "OPENING_SOURCE_CONFLICT", "기초잔액 전표 원천이 일치하지 않습니다.", 409
                )
            opening_cells = sorted(
                (c.field_code, c.row_key, str(c.value))
                for c in draft.cells
                if c.field_code.startswith("Opening_Balances.")
            )
            current = digest({"cells": opening_cells})
            legacy = digest({"version": opening.source_version, "cells": opening_cells})
            if opening.source_digest not in (current, legacy):
                raise AccountingError(
                    "OPENING_SOURCE_CONFLICT", "기초잔액 원천이 변경되었습니다.", 409
                )
            accounts = {account.id: account.account_code for account in uow.accounts.list(company)}
            account_ids = {code: identifier for identifier, code in accounts.items()}
            mappings = {
                role: accounts[mapping.account_id]
                for role in ("AR", "AP")
                if (mapping := uow.control_accounts.mapping(company, role)) is not None
                and mapping.account_id in accounts
            }
            counterparties = active_source_counterparties(uow, draft, company)
            preview = preview_ar_ap(draft.cells, draft.version, mappings, set(counterparties))
            if preview.source_digest != expected_digest:
                raise AccountingError(
                    "STALE_SOURCE_DIGEST", "미결 항목 원천이 변경되었습니다.", 409
                )
            if not preview.ready or preview.as_of_date != journal.entry_date:
                raise AccountingError(
                    "OPEN_ITEM_NOT_READY", "미결 항목 사전 대조를 확인해 주세요.", 409
                )
            if not preview.totals:
                raise AccountingError(
                    "OPEN_ITEM_NOT_READY", "승격할 채권·채무 미결 항목이 없습니다.", 409
                )
            actual: dict[tuple[str, str, str], Decimal] = {}
            cp_codes = {identifier: code for code, identifier in counterparties.items()}
            for line in journal.lines:
                code = accounts.get(line.account_id)
                for role, mapped in mappings.items():
                    if code != mapped:
                        continue
                    cp_code = cp_codes.get(line.counterparty_id) if line.counterparty_id else None
                    if cp_code is None:
                        raise AccountingError(
                            "OPENING_JOURNAL_MISMATCH", "전표 거래처가 원천과 다릅니다.", 409
                        )
                    key = (role, code, cp_code)
                    amount = line.debit_amount if role == "AR" else line.credit_amount
                    opposite = line.credit_amount if role == "AR" else line.debit_amount
                    if amount <= 0 or opposite != 0:
                        raise AccountingError(
                            "OPENING_JOURNAL_MISMATCH", "전표 금액 방향이 원천과 다릅니다.", 409
                        )
                    if uow.obligations(role).origin(company, journal.id, line.line_no):
                        raise AccountingError(
                            "OPENING_SOURCE_CONFLICT", "기존 채권·채무 인식과 중복됩니다.", 409
                        )
                    actual[key] = actual.get(key, Decimal(0)) + amount
            expected = {
                (item.role, item.account_code, item.counterparty_code): item.item_amount
                for item in preview.totals
            }
            if actual != expected:
                raise AccountingError(
                    "OPENING_JOURNAL_MISMATCH", "확정 전표와 미결 항목 합계가 다릅니다.", 409
                )
            for role, _, _ in expected:
                require_company(
                    uow, actor, company, "collection.record" if role == "AR" else "payment.record"
                )
            if opening.ar_ap_digest is not None:
                if opening.ar_ap_digest != expected_digest:
                    raise AccountingError(
                        "OPENING_SOURCE_CONFLICT", "이미 승격된 미결 항목 원천과 다릅니다.", 409
                    )
                return (
                    journal.id,
                    tuple(uow.obligations("AR").opening_items(company, opening.id)),
                    tuple(uow.obligations("AP").opening_items(company, opening.id)),
                )
            values = {(c.field_code, c.row_key): c.value for c in draft.cells}
            for role, section in (("AR", "AR_Opening"), ("AP", "AP_Opening")):
                repo = uow.obligations(role)
                rows = sorted(
                    {c.row_key for c in draft.cells if c.field_code == f"{section}.reference_code"}
                )
                for row in rows:

                    def value(field: str, section: str = section, row: str = row) -> object:
                        return values[(f"{section}.{field}", row)]

                    repo.add_opening(
                        company,
                        opening.id,
                        journal.id,
                        row,
                        str(value("reference_code")),
                        counterparties[str(value("counterparty_code"))],
                        account_ids[str(value("account_code"))],
                        Decimal(str(value("original_amount"))),
                        date.fromisoformat(str(value("due_date"))),
                        journal.entry_date,
                    )
            opening.ar_ap_digest = expected_digest
            opening.ar_ap_promoted_at = uow.now()
            uow.governance.audit(
                company,
                actor.user_id,
                "opening.promote_ar_ap",
                journal.id,
                "",
                "",
                expected_digest,
                opening.ar_ap_promoted_at,
            )
            return (
                journal.id,
                tuple(uow.obligations("AR").opening_items(company, opening.id)),
                tuple(uow.obligations("AP").opening_items(company, opening.id)),
            )

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
            opening_cells = sorted(
                (c.field_code, c.row_key, str(c.value))
                for c in draft.cells
                if c.field_code.startswith("Opening_Balances.")
            )
            source_digest = digest({"cells": opening_cells})
            previous = uow.openings.existing(company, draft.id)
            if previous:
                journal_id, source_version, recorded_digest = previous
                legacy_digest = digest({"version": source_version, "cells": opening_cells})
                if recorded_digest not in (source_digest, legacy_digest):
                    raise AccountingError(
                        "OPENING_SOURCE_CONFLICT",
                        "기초잔액 원천이 기존 전표와 다릅니다. 기존 전표를 검토해 주세요.",
                        409,
                    )
                journal = uow.journals.get(company, journal_id)
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
                counterparty = (
                    uow.counterparties.by_code(company_id=company, code=str(cp)) if cp else None
                )
                if cp and counterparty is None:
                    raise ResourceNotFound()
                lines.append(
                    JournalLine(
                        id=uuid4(),
                        line_no=len(lines) + 1,
                        account_id=account.id,
                        counterparty_id=counterparty.id if counterparty else None,
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
