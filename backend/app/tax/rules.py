from datetime import date, timedelta
from decimal import Decimal

from app.accounting.transactions.domain.entities import Transaction
from app.core.digests import digest
from app.tax.contracts import Check, Period, Preparation, Profile, Vat, Withholding

ZERO = Decimal("0")


def source_digest(transaction: Transaction) -> str:
    return digest(
        {
            "id": str(transaction.id),
            "version": transaction.version,
            "date": transaction.transaction_date.isoformat(),
            "status": transaction.status,
            "amount": str(transaction.amount),
            "tax_amount": str(transaction.tax_amount),
            "direction": transaction.direction,
            "payee": str(transaction.counterparty_id),
            "evidence": str(transaction.evidence_id),
        }
    )


def profile_coverage(profiles: tuple[Profile, ...], start: date, end: date) -> bool:
    cursor = start
    for profile in profiles:
        if profile.effective_from > cursor:
            return False
        last = profile.effective_to or date.max
        if last >= end:
            return True
        if last >= cursor:
            cursor = last + timedelta(days=1)
    return False


def prepare(
    period: Period,
    profiles: tuple[Profile, ...],
    vat: tuple[Vat, ...],
    withholding: tuple[Withholding, ...],
    transactions: tuple[Transaction, ...],
) -> Preparation:
    profiles = tuple(
        p
        for p in profiles
        if p.effective_from <= period.period_end
        and (p.effective_to is None or p.effective_to >= period.period_start)
    )
    vat = tuple(row for row in vat if row.period_id == period.id)
    withholding = tuple(row for row in withholding if row.period_id == period.id)
    checks = [
        Check(
            code="PROFILE_COMPLETE",
            severity="PASS"
            if profile_coverage(profiles, period.period_start, period.period_end)
            else "BLOCK",
        )
    ]
    source = {row.id: row for row in transactions}
    facts = vat if period.tax_type == "VAT" else withholding
    for row in facts:
        transaction = source.get(row.transaction_id)
        if transaction is None or source_digest(transaction) != row.source_digest:
            checks.append(Check(code="TRANSACTION_STALE", severity="BLOCK", source_id=row.id))
        if row.evidence_id is None:
            checks.append(Check(code="EVIDENCE_MISSING", severity="BLOCK", source_id=row.id))
    if period.tax_type == "VAT":
        classified = {row.transaction_id for row in vat}
        for transaction in transactions:
            if transaction.status != "EXCLUDED" and transaction.id not in classified:
                checks.append(
                    Check(code="VAT_TREATMENT_MISSING", severity="BLOCK", source_id=transaction.id)
                )
        for row in vat:
            if row.deductible_status == "REVIEW_REQUIRED":
                checks.append(
                    Check(code="DEDUCTION_UNRESOLVED", severity="BLOCK", source_id=row.id)
                )
        if any(p.tax_regime != "VAT_GENERAL" for p in profiles):
            checks.append(Check(code="VAT_REGIME_REQUIRES_RULE", severity="BLOCK"))
    else:
        checks.append(Check(code="PAYMENT_COMPLETENESS_UNVERIFIED", severity="BLOCK"))
    # User-supplied references are provenance, never proof of statutory rule verification.
    checks.extend(
        Check(code=code, severity="BLOCK")
        for code in (
            "RULES_UNVERIFIED",
            "REQUIRED_FORMS_UNRESOLVED",
            "ACCOUNTING_ACCEPTANCE_REQUIRED",
            "REVIEW_REQUIRED",
        )
    )
    output = sum((r.tax_amount for r in vat if r.direction == "INFLOW"), ZERO)
    deductible = sum(
        (
            r.tax_amount
            for r in vat
            if r.direction == "OUTFLOW" and r.deductible_status == "DEDUCTIBLE"
        ),
        ZERO,
    )
    return Preparation(
        period=period,
        profile_ids=tuple(p.id for p in profiles),
        vat_items=vat,
        withholding_items=withholding,
        output_tax=output,
        deductible_input_tax=deductible,
        vat_balance=output - deductible,
        withholding_tax=sum((r.withholding_tax for r in withholding), ZERO),
        local_tax=sum((r.local_tax for r in withholding), ZERO),
        net_payments=sum((r.net_amount for r in withholding), ZERO),
        source_digest=digest(
            {
                "period": period.model_dump(mode="json"),
                "profiles": [p.model_dump(mode="json") for p in profiles],
                "facts": [r.model_dump(mode="json") for r in facts],
                "sources": [source_digest(t) for t in transactions],
            }
        ),
        checks=tuple(checks),
        status="NEEDS_REVIEW" if facts else "NOT_STARTED",
    )
