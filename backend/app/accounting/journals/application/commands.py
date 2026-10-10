"""승인·확정·역분개의 원자적 명령입니다. 자동승인은 제공하지 않습니다."""

import re
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import date, timedelta
from uuid import UUID, uuid4

from app.accounting.domain.rules import journal_number
from app.accounting.journals.application.service import validate_journal
from app.accounting.journals.domain.entities import Journal, transition
from app.accounting.journals.domain.errors import AccountingError
from app.approvals.application.contracts import AccountingUnitOfWork
from app.approvals.domain.entities import Approval
from app.companies.application.service import require_company
from app.contracts.access_errors import (
    AuthorizationDenied,
    InvalidInput,
    ResourceNotFound,
    VersionConflict,
)
from app.identity.users.domain.entities import Principal
from app.intake.domain.digest import digest


def journal_digest(value: Journal) -> str:
    data = asdict(value)
    # 승인 대상은 회계 의미와 출처이며 상태전이 시각·버전 자체는 별도로 검증합니다.
    for key in (
        "status",
        "version",
        "updated_at",
        "approved_at",
        "approved_by",
        "approval_id",
        "posted_at",
        "posted_by",
        "journal_no",
    ):
        data.pop(key)
    import json

    return digest(json.loads(json.dumps(data, default=str)))


class JournalCommands:
    def __init__(self, factory: Callable[[], AccountingUnitOfWork]) -> None:
        self.factory = factory

    def execute(
        self,
        actor: Principal,
        company: UUID,
        resource: UUID,
        command: str,
        expected_version: int,
        key: str,
        reason: str = "",
        approval_id: UUID | None = None,
        reversal_date: date | None = None,
        request_id: str = "",
    ) -> Journal:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidInput()
        permission = {
            "submit": "journal.submit",
            "request_review": "journal.submit",
            "approve": "journal.approve",
            "reject": "journal.approve",
            "post": "journal.post",
            "reverse": "journal.reverse",
        }[command]
        fingerprint = digest(
            {
                "resource": str(resource),
                "version": expected_version,
                "reason": reason,
                "approval": str(approval_id),
                "date": str(reversal_date),
            }
        )
        with self.factory() as uow:
            require_company(uow, actor, company, permission)
            replay = uow.governance.replay(company, actor.user_id, command, key, fingerprint)
            if replay:
                value = uow.journals.get(company, replay)
                if value is None:
                    raise ResourceNotFound()
                return value
            current = uow.journals.get(company, resource, lock=True)
            if current is None:
                raise ResourceNotFound()
            if current.version != expected_version:
                raise VersionConflict()
            before = journal_digest(current)
            now = uow.now()
            approval: Approval | None
            if command == "reverse":
                if current.status != "POSTED" or not reason.strip() or reversal_date is None:
                    raise InvalidInput()
                if uow.journals.reversal(company, current.id):
                    raise AccountingError(
                        "REVERSAL_ALREADY_EXISTS", "이미 역분개 전표가 있습니다.", 409
                    )
                period = next(
                    (
                        p
                        for p in uow.periods.list(company)
                        if p.start_date <= reversal_date <= p.end_date and p.status == "OPEN"
                    ),
                    None,
                )
                if period is None:
                    raise AccountingError(
                        "PERIOD_NOT_OPEN", "역분개일에 열린 회계기간이 없습니다.", 409
                    )
                result = replace(
                    current,
                    id=uuid4(),
                    entry_date=reversal_date,
                    accounting_period_id=period.id,
                    description=reason,
                    source_type="REVERSAL",
                    source_transaction_id=None,
                    reversal_of_id=current.id,
                    status="DRAFT",
                    version=1,
                    created_by=actor.user_id,
                    created_at=now,
                    updated_at=now,
                    journal_no=None,
                    approval_id=None,
                    approved_by=None,
                    approved_at=None,
                    posted_by=None,
                    posted_at=None,
                    lines=tuple(
                        replace(
                            line,
                            id=uuid4(),
                            debit_amount=line.credit_amount,
                            credit_amount=line.debit_amount,
                        )
                        for line in current.lines
                    ),
                )
                validate_journal(uow, result)
                uow.journals.add(result)
            else:
                target = transition(current.status, command)
                validate_journal(uow, current)
                result = replace(
                    current, status=target, version=current.version + 1, updated_at=now
                )
                if command == "request_review":
                    approval = Approval(
                        id=uuid4(),
                        company_id=company,
                        journal_id=current.id,
                        target_version=result.version,
                        target_digest=before,
                        action_code="journal.post",
                        status="PENDING",
                        requester_id=current.created_by,
                        reviewer_id=None,
                        requested_at=now,
                        decided_at=None,
                        expires_at=now + timedelta(days=7),
                        reason="",
                    )
                    uow.governance.save_approval(approval)
                    result = replace(result, approval_id=approval.id)
                if command in ("approve", "reject", "post"):
                    approval = (
                        uow.governance.approval(company, current.approval_id)
                        if current.approval_id
                        else None
                    )
                    if approval is None:
                        raise AccountingError(
                            "APPROVAL_REQUIRED", "전표 승인 요청이 필요합니다.", 409
                        )
                    if (
                        approval.journal_id != current.id
                        or approval.target_digest != before
                        or approval.target_version != current.version
                        or approval.expires_at <= now
                    ):
                        raise AccountingError(
                            "APPROVAL_STALE",
                            "승인 대상이 변경되었거나 검토 기한이 지났습니다.",
                            409,
                        )
                    if command in ("approve", "reject"):
                        if approval.status != "PENDING" or actor.user_id == approval.requester_id:
                            raise AuthorizationDenied()
                        if not reason.strip():
                            raise InvalidInput()
                        uow.governance.save_approval(
                            replace(
                                approval,
                                status="APPROVED" if command == "approve" else "REJECTED",
                                reviewer_id=actor.user_id,
                                decided_at=now,
                                reason=reason,
                                target_version=result.version,
                            )
                        )
                        if command == "approve":
                            result = replace(result, approved_by=actor.user_id, approved_at=now)
                    else:
                        if (
                            approval_id != approval.id
                            or approval.status != "APPROVED"
                            or approval.reviewer_id is None
                        ):
                            raise AccountingError(
                                "APPROVAL_REQUIRED", "유효한 사람의 승인이 필요합니다.", 409
                            )
                        reviewer = uow.companies.accessible(
                            approval.reviewer_id, company, lock=True
                        )
                        user = uow.users.get(approval.reviewer_id)
                        if (
                            reviewer is None
                            or "journal.approve" not in reviewer.permissions
                            or user is None
                            or user.status != "ACTIVE"
                        ):
                            raise AccountingError(
                                "APPROVAL_STALE",
                                "승인자의 현재 권한을 확인할 수 없습니다. 다시 검토해 주세요.",
                                409,
                            )
                        settings = uow.settings.get(company)
                        period = uow.periods.get(
                            company_id=company, resource_id=current.accounting_period_id
                        )
                        assert settings and period
                        year = (
                            0 if settings.numbering_reset_policy == "NEVER" else period.fiscal_year
                        )
                        number = uow.sequences.allocate(company, year, "GENERAL")
                        result = replace(
                            result,
                            journal_no=journal_number(
                                settings.journal_number_prefix, period.fiscal_year, number
                            ),
                            posted_by=actor.user_id,
                            posted_at=now,
                        )
                        uow.governance.save_approval(replace(approval, status="CONSUMED"))
                if not uow.journals.update(result, current.version):
                    raise VersionConflict()
            uow.governance.audit(
                company,
                actor.user_id,
                command,
                result.id,
                request_id,
                before,
                journal_digest(result),
                now,
            )
            uow.governance.record(
                company, actor.user_id, command, key, fingerprint, result.id, result.version, now
            )
            return result
