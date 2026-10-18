"""CLOSED 기간의 기존 Closing source를 BS/IS 관계형 스냅샷으로 투영합니다."""

import re
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from app.accounting.ledger.domain.entities import LedgerFact
from app.accounting.templates.domain.defaults import (
    DEFAULT_ACCOUNTS,
    LEGACY_ACCOUNTS,
    PREVIOUS_ACCOUNTS,
)
from app.closing.application.service import ClosingService
from app.closing.domain.errors import ClosingRunStale
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, StateConflict
from app.core.digests import digest
from app.identity.users.domain.entities import Principal
from app.reporting.financial_statements.application.contracts import ReportingUnitOfWork
from app.reporting.financial_statements.domain.entities import (
    SourceLine,
    StatementSet,
    StatementView,
)
from app.reporting.financial_statements.domain.rules import (
    LEAF_BY_TYPE,
    LINE_BY_CODE,
    LINES,
    ReportMappingIncomplete,
    ReportSourceStale,
    calculate,
    default_line,
)

TEMPLATE_CODES = {
    account.id: (account.account_code, account.account_type)
    for account in (*LEGACY_ACCOUNTS, *PREVIOUS_ACCOUNTS, *DEFAULT_ACCOUNTS)
}
ZERO = Decimal("0")
DRILLDOWN_CHILDREN = {
    "ASSETS": ("ASSET_ACCOUNTS",),
    "LIABILITIES": ("LIABILITY_ACCOUNTS",),
    "EQUITY": ("EQUITY_ACCOUNTS", "UNTRANSFERRED_PROFIT"),
    "LIABILITIES_EQUITY": ("LIABILITY_ACCOUNTS", "EQUITY_ACCOUNTS", "UNTRANSFERRED_PROFIT"),
    "GROSS_PROFIT": ("REVENUE", "COGS"),
    "OPERATING_PROFIT": ("REVENUE", "COGS", "OPERATING_EXPENSE"),
    "PROFIT_BEFORE_TAX": (
        "REVENUE",
        "COGS",
        "OPERATING_EXPENSE",
        "NON_OPERATING_INCOME",
        "NON_OPERATING_EXPENSE",
    ),
    "NET_PROFIT": (
        "REVENUE",
        "COGS",
        "OPERATING_EXPENSE",
        "NON_OPERATING_INCOME",
        "NON_OPERATING_EXPENSE",
        "TAX_EXPENSE",
    ),
}


def source_amount(fact: LedgerFact, code: str) -> Decimal:
    sign = LINE_BY_CODE[code].normal_sign
    return (
        fact.debit_amount - fact.credit_amount
        if sign == "DEBIT"
        else fact.credit_amount - fact.debit_amount
    )


class StatementService:
    def __init__(self, factory: Callable[[], ReportingUnitOfWork]) -> None:
        self.factory = factory

    def map_account(
        self, actor: Principal, company: UUID, period_id: UUID, account_id: UUID, line_code: str
    ) -> tuple[UUID, str]:
        """회사 소유 계정의 최초 명시적 표시 매핑만 등록합니다."""
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            period = uow.periods.get(company_id=company, resource_id=period_id)
            account = uow.accounts.get(company_id=company, resource_id=account_id)
            if period is None or account is None:
                raise ResourceNotFound()
            if not account.posting_allowed or line_code not in LEAF_BY_TYPE.get(
                account.account_type, set()
            ):
                raise InvalidInput()
            taxonomy = uow.statements.active_taxonomy(period.end_date)
            if taxonomy is None:
                raise ReportMappingIncomplete()
            taxonomy_id, _ = taxonomy
            existing = {
                row_account: code
                for row_account, code, _ in uow.statements.mappings(
                    company, taxonomy_id, period.end_date
                )
            }
            if account_id in existing:
                if existing[account_id] != line_code:
                    raise StateConflict()
                return account_id, line_code
            uow.statements.add_mapping(
                company,
                taxonomy_id,
                account_id,
                uow.statements.line_ids(taxonomy_id)[line_code],
                period.start_date,
            )
            return account_id, line_code

    def generate(self, actor: Principal, company: UUID, period_id: UUID, key: str) -> StatementSet:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.generate")
            try:
                period, run, source_digest, rows, facts = ClosingService.closed_adjusted_source(
                    uow, company, period_id
                )
            except ClosingRunStale:
                raise ReportSourceStale() from None
            taxonomy = uow.statements.active_taxonomy(period.end_date)
            if taxonomy is None:
                raise ReportMappingIncomplete()
            taxonomy_id, taxonomy_version = taxonomy
            line_ids = uow.statements.line_ids(taxonomy_id)
            accounts = {account.id: account for account in uow.accounts.list(company)}
            current = {
                account
                for account, _, _ in uow.statements.mappings(company, taxonomy_id, period.end_date)
            }
            for account in accounts.values():
                if account.id in current or account.template_account_id not in TEMPLATE_CODES:
                    continue
                template_code, template_type = TEMPLATE_CODES[account.template_account_id]
                if account.account_type != template_type:
                    continue
                code = default_line(account.account_type, template_code)
                uow.statements.add_mapping(
                    company, taxonomy_id, account.id, line_ids[code], date(1900, 1, 1)
                )
            mappings = uow.statements.mappings(company, taxonomy_id, period.end_date)
            mapping_pairs = [(account, code) for account, code, _ in mappings]
            values = calculate(
                rows, mapping_pairs, {a.id: a.account_type for a in accounts.values()}
            )
            mapping_digest = digest([(str(a), code, version) for a, code, version in mappings])
            fingerprint = digest(
                (
                    str(period_id),
                    period.close_version,
                    taxonomy_version,
                    source_digest,
                    mapping_digest,
                )
            )
            uow.lock_command(company, actor.user_id, "financial_statement.generate", key)
            replay = uow.statements.replay(company, actor.user_id, key, fingerprint)
            if replay is not None:
                result = uow.statements.set(company, replay)
                assert result is not None
                return result
            existing = uow.statements.set_for_source(
                company, period_id, period.close_version, taxonomy_id, source_digest, mapping_digest
            )
            if existing is not None:
                uow.statements.record(
                    company, actor.user_id, key, fingerprint, existing.id, uow.now()
                )
                return existing
            now = uow.now()
            result = StatementSet(
                id=uuid4(),
                company_id=company,
                period_id=period_id,
                closing_run_id=run.id,
                close_version=period.close_version,
                taxonomy_id=taxonomy_id,
                taxonomy_version=taxonomy_version,
                status="GENERATED",
                trial_balance_digest=source_digest,
                mapping_digest=mapping_digest,
                generated_at=now,
            )
            uow.statements.add_set(result, actor.user_id)
            by_account = {account: code for account, code in mapping_pairs}
            for kind in ("BALANCE_SHEET", "INCOME_STATEMENT"):
                statement_id, snapshot_id = uuid4(), uuid4()
                statement_lines = [line for line in LINES if line.statement_type == kind]
                snapshot_digest = digest(
                    [(line.line_code, str(values[line.line_code])) for line in statement_lines]
                )
                uow.statements.add_statement(
                    company,
                    result.id,
                    statement_id,
                    kind,
                    snapshot_id,
                    snapshot_digest,
                    source_digest,
                    mapping_digest,
                    now,
                )
                for line in statement_lines:
                    statement_line_id = uuid4()
                    uow.statements.add_line(
                        company,
                        snapshot_id,
                        statement_line_id,
                        line_ids[line.line_code],
                        values[line.line_code],
                        source_digest,
                    )
                    if line.subtotal_type == "TOTAL":
                        continue
                    for fact in facts:
                        mapped = by_account.get(fact.account_id)
                        if line.line_code == "UNTRANSFERRED_PROFIT":
                            if mapped not in (*LEAF_BY_TYPE["REVENUE"], *LEAF_BY_TYPE["EXPENSE"]):
                                continue
                            amount = fact.credit_amount - fact.debit_amount
                        elif mapped == line.line_code:
                            if kind == "INCOME_STATEMENT" and fact.entry_date < period.start_date:
                                continue
                            amount = source_amount(fact, mapped)
                        else:
                            continue
                        uow.statements.add_source(
                            company, statement_line_id, fact.account_id, fact.line_id, amount
                        )
            uow.statements.record(company, actor.user_id, key, fingerprint, result.id, now)
            return result

    def set(self, actor: Principal, company: UUID, identifier: UUID) -> StatementSet:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            result = uow.statements.set(company, identifier)
            if result is None:
                raise ResourceNotFound()
            return result

    def sets(self, actor: Principal, company: UUID, period_id: UUID) -> list[StatementSet]:
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            if uow.periods.get(company_id=company, resource_id=period_id) is None:
                raise ResourceNotFound()
            return uow.statements.sets(company, period_id)

    def metric_source(
        self, actor: Principal, company: UUID, period_id: UUID
    ) -> tuple[StatementSet, StatementView, StatementView]:
        """Read the latest CLOSED version and both statements in one transaction."""
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            period = uow.periods.get(company_id=company, resource_id=period_id)
            if period is None:
                raise ResourceNotFound()
            if period.status != "CLOSED":
                raise ReportSourceStale()
            sets = uow.statements.sets(company, period_id)
            current = next(
                (item for item in sets if item.close_version == period.close_version), None
            )
            if current is None:
                raise ResourceNotFound()
            balance = uow.statements.statement(company, current.id, "BALANCE_SHEET")
            income = uow.statements.statement(company, current.id, "INCOME_STATEMENT")
            if balance is None or income is None:
                raise ResourceNotFound()
            return current, balance, income

    def statement(self, actor: Principal, company: UUID, set_id: UUID, kind: str) -> StatementView:
        if kind not in {"BALANCE_SHEET", "INCOME_STATEMENT"}:
            raise InvalidInput()
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            if uow.statements.set(company, set_id) is None:
                raise ResourceNotFound()
            result = uow.statements.statement(company, set_id, kind)
            if result is None:
                raise ResourceNotFound()
            return result

    def drilldown(
        self, actor: Principal, company: UUID, set_id: UUID, kind: str, code: str
    ) -> tuple[SourceLine, ...]:
        view = self.statement(actor, company, set_id, kind)
        if code not in {line.line_code for line in view.lines}:
            raise ResourceNotFound()
        codes = DRILLDOWN_CHILDREN.get(code, (code,))
        with self.factory() as uow:
            require_company(uow, actor, company, "financial_statement.read")
            return tuple(
                replace(source, amount=-source.amount)
                if code in DRILLDOWN_CHILDREN
                and line.line_code
                in {"COGS", "OPERATING_EXPENSE", "NON_OPERATING_EXPENSE", "TAX_EXPENSE"}
                else source
                for line in view.lines
                if line.line_code in codes
                for source in uow.statements.sources(company, line.id)
            )
