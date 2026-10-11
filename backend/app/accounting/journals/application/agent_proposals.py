"""Agent의 후보를 기존 회계 검증·초안 명령으로 연결합니다. 승인·확정하지 않습니다."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.accounting.journals.application.commands import JournalCommands
from app.accounting.journals.application.service import JournalService, validate_journal
from app.accounting.journals.domain.entities import Journal, JournalLine
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, VersionConflict
from app.identity.users.domain.entities import Principal


class AgentProposalService:
    def __init__(self, journals: JournalService, commands: JournalCommands) -> None:
        self.journals = journals
        self.commands = commands

    def candidate(
        self,
        actor: Principal,
        company: UUID,
        transaction: UUID,
        source_version: int,
        debit_account: UUID,
        credit_account: UUID,
        evidence_ids: tuple[UUID, ...],
    ) -> Journal:
        with self.journals.factory() as uow:
            require_company(uow, actor, company, "journal.propose")
            if debit_account == credit_account:
                raise InvalidInput()
            source = uow.transactions.get(company, transaction)
            if source is None:
                raise ResourceNotFound()
            if source.version != source_version:
                raise VersionConflict()
            if set(evidence_ids) != ({source.evidence_id} if source.evidence_id else set()):
                raise InvalidInput()
            periods = [
                p
                for p in uow.periods.list(company)
                if p.start_date <= source.accounting_date <= p.end_date
            ]
            if len(periods) != 1:
                raise ResourceNotFound()
            now = datetime.now(UTC)
            value = Journal(
                id=uuid4(),
                company_id=company,
                accounting_period_id=periods[0].id,
                entry_date=source.accounting_date,
                description="거래 기반 분개 제안",
                source_type="TRANSACTION",
                proposal_origin="AGENT",
                status="DRAFT",
                version=1,
                created_by=actor.user_id,
                created_at=now,
                updated_at=now,
                source_transaction_id=source.id,
                evidence_ids=evidence_ids,
                lines=(
                    JournalLine(
                        id=uuid4(),
                        line_no=1,
                        account_id=debit_account,
                        debit_amount=source.amount,
                        credit_amount=source.amount * 0,
                        counterparty_id=source.counterparty_id,
                    ),
                    JournalLine(
                        id=uuid4(),
                        line_no=2,
                        account_id=credit_account,
                        debit_amount=source.amount * 0,
                        credit_amount=source.amount,
                        counterparty_id=source.counterparty_id,
                    ),
                ),
            )
            validate_journal(uow, value)
            return value

    def handoff(
        self, actor: Principal, value: Journal, run_id: UUID, source_version: int
    ) -> Journal:
        # 사람의 Graph 응답은 회계 승인이 아닙니다. 기존 초안 생성 명령까지만 호출합니다.
        return self.commands.create(actor, value, f"agent:{run_id}", source_version=source_version)
