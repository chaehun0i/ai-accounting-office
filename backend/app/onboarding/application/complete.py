"""미지원 업무는 차단하며 현재 Domain Command만 원자적으로 승격합니다."""

import re
from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from app.accounting.accounts.domain.entities import Account
from app.accounting.application.onboarding import promote_accounting
from app.accounting.settings.domain.entities import AccountingSettings
from app.companies.application.onboarding import promote_company
from app.companies.application.service import require_company
from app.identity.users.domain.entities import Principal
from app.intake.domain.digest import digest
from app.intake.domain.errors import IdempotencyConflict
from app.master_data.application.onboarding import (
    promote_counterparties,
    promote_counterparty_roles,
)
from app.master_data.counterparties.domain.entities import Counterparty
from app.onboarding.application.service import OnboardingService
from app.onboarding.domain.entities import Receipt
from app.onboarding.domain.errors import InvalidValue, NotReady
from app.onboarding.domain.validation import recalculate, validate


class CompleteOnboarding:
    def __init__(self, workspace: OnboardingService) -> None:
        self.workspace = workspace

    def complete(self, actor: Principal, company: UUID, expected_version: int, key: str) -> Receipt:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", key):
            raise InvalidValue()
        fingerprint = digest(
            {
                "company": str(company),
                "version": expected_version,
                "command": "onboarding-complete-1",
            }
        )
        with self.workspace.factory() as uow:
            current = self.workspace.workspace(uow, actor, company, "onboarding.complete")
            replay = uow.onboarding.receipt(company, key, promotion=True)
            if replay:
                if replay.fingerprint != fingerprint:
                    raise IdempotencyConflict()
                return replay
            self.workspace.writable(current, expected_version)
            cells = recalculate(current.cells)
            if validate(cells):
                raise NotReady()
            profile = require_company(uow, actor, company, "company.read").company
            values = {(c.field_code, c.row_key): c.value for c in cells}

            def text(section: str, code: str, row: str = "singleton") -> str:
                return str(values[(f"{section}.{code}", row)])

            opening = date.fromisoformat(text("Company", "opening_date"))
            promoted = replace(
                profile,
                company_name=text("Company", "company_name"),
                business_number=text("Company", "business_number"),
                corporation_number=str(values[("Company.corporation_number", "singleton")])
                if ("Company.corporation_number", "singleton") in values
                else None,
                taxpayer_type=text("Company", "taxpayer_type"),
                opening_date=opening,
                timezone=text("Company", "timezone"),
            )
            promote_company(uow, actor, promoted)
            settings = AccountingSettings(
                company_id=company,
                functional_currency_code=text("Accounting_Settings", "functional_currency_code"),
                fiscal_year_start_month=int(
                    Decimal(text("Accounting_Settings", "fiscal_year_start_month"))
                ),
                journal_number_prefix=text("Accounting_Settings", "journal_number_prefix"),
                accounting_framework_code=text("Accounting_Settings", "accounting_framework_code"),
                reporting_taxonomy_code=text("Accounting_Settings", "reporting_taxonomy_code"),
                created_at=uow.now(),
                updated_at=uow.now(),
            )
            accounts = [
                Account(
                    company_id=company,
                    account_code=text("COA", "account_code", row),
                    account_name=text("COA", "account_name", row),
                    account_type=text("COA", "account_type", row),
                    normal_balance=text("COA", "normal_balance", row),
                    posting_allowed=values[("COA.posting_allowed", row)] is True,
                    created_at=uow.now(),
                    updated_at=uow.now(),
                )
                for row in sorted({c.row_key for c in cells if c.field_code.startswith("COA.")})
            ]
            account_count = promote_accounting(uow, actor, settings, accounts, opening.year)
            terms = {term.term_code: term for term in uow.payment_terms.list(company)}
            counterparties: list[Counterparty] = []
            for row in sorted(
                {c.row_key for c in cells if c.field_code.startswith("Counterparties.")}
            ):
                term_code = values.get(("Counterparties.payment_term_code", row))
                if term_code and str(term_code) not in terms:
                    raise NotReady()
                counterparties.append(
                    Counterparty(
                        company_id=company,
                        counterparty_code=text("Counterparties", "counterparty_code", row),
                        display_name=text("Counterparties", "legal_name", row),
                        legal_name=text("Counterparties", "legal_name", row),
                        normalized_legal_name="",
                        business_number=str(values[("Counterparties.business_number", row)])
                        if ("Counterparties.business_number", row) in values
                        else None,
                        counterparty_type=text("Counterparties", "counterparty_type", row),
                        payment_term_id=terms[str(term_code)].id if term_code else None,
                        created_at=uow.now(),
                        updated_at=uow.now(),
                    )
                )
            counterparty_count = promote_counterparties(uow, actor, counterparties)
            promote_counterparty_roles(
                uow,
                actor,
                company,
                {
                    c.row_key: str(c.value)
                    for c in cells
                    if c.field_code == "Counterparties.role_code"
                },
                opening,
            )
            saved = uow.onboarding.save(
                current, cells, actor.user_id, uow.now(), status="COMPLETED"
            )
            receipt = Receipt(
                uuid4(),
                saved.id,
                None,
                fingerprint,
                account_count,
                counterparty_count,
                0,
                0,
                0,
                uow.now(),
            )
            uow.onboarding.record(saved, receipt, key, promotion=True)
            return receipt
