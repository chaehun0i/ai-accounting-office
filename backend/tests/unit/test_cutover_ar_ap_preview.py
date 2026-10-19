"""기초 채권·채무 집계는 계정과 거래처가 정확히 일치해야 합니다."""

from datetime import date
from decimal import Decimal

from app.accounting.opening_balances.application.ar_ap_preview import preview_ar_ap
from app.onboarding.domain.values import Cell, Scalar


def row(section: str, key: str, **values: Scalar) -> list[Cell]:
    return [Cell(f"{section}.{name}", key, value) for name, value in values.items()]


def source() -> list[Cell]:
    return [
        *row(
            "Opening_Balances",
            "2026-01-01|110|C1",
            as_of_date=date(2026, 1, 1),
            account_code="110",
            counterparty_code="C1",
            debit_amount=Decimal("100"),
            credit_amount=Decimal("0"),
        ),
        *row(
            "AR_Opening",
            "C1|INV-1",
            counterparty_code="C1",
            reference_code="INV-1",
            original_amount=Decimal("60"),
            due_date=date(2026, 2, 1),
            account_code="110",
        ),
        *row(
            "AR_Opening",
            "C1|INV-2",
            counterparty_code="C1",
            reference_code="INV-2",
            original_amount=Decimal("40"),
            due_date=date(2026, 2, 2),
            account_code="110",
        ),
    ]


def test_matching_open_items_and_stable_digest() -> None:
    cells = source()
    first = preview_ar_ap(cells, 3, {"AR": "110", "AP": "210"}, {"C1"})
    assert first.ready
    assert first.as_of_date == date(2026, 1, 1)
    assert first.totals[0].opening_amount == first.totals[0].item_amount == Decimal("100")
    changed = cells + [Cell("Company.company_name", "singleton", "다른 이름")]
    assert (
        preview_ar_ap(changed, 4, {"AR": "110", "AP": "210"}, {"C1"}).source_digest
        == first.source_digest
    )


def test_mismatch_and_unmapped_account_are_blocking() -> None:
    cells = source()
    changed = [
        Cell(cell.field_code, cell.row_key, Decimal("39"), cell.source_type)
        if cell.field_code == "AR_Opening.original_amount" and cell.row_key == "C1|INV-2"
        else cell
        for cell in cells
    ]
    result = preview_ar_ap(changed, 3, {"AR": "110"}, {"C1"})
    assert not result.ready
    assert {issue.code for issue in result.issues} == {"OPEN_ITEM_TOTAL_MISMATCH"}
    result = preview_ar_ap(cells, 3, {"AR": "111"}, {"C1"})
    assert not result.ready
    assert "CONTROL_ACCOUNT_MISMATCH" in {issue.code for issue in result.issues}


def test_unknown_counterparty_and_wrong_control_side() -> None:
    cells = source()
    result = preview_ar_ap(cells, 3, {"AR": "110"}, set())
    assert not result.ready
    assert "UNKNOWN_COUNTERPARTY" in {issue.code for issue in result.issues}
    wrong = [
        Cell(cell.field_code, cell.row_key, Decimal("100"), cell.source_type)
        if cell.field_code == "Opening_Balances.credit_amount"
        else cell
        for cell in cells
    ]
    result = preview_ar_ap(wrong, 3, {"AR": "110"}, {"C1"})
    assert not result.ready
    assert "INVALID_CONTROL_LINE" in {issue.code for issue in result.issues}


def test_payable_and_multiple_cutover_dates() -> None:
    cells = [
        *row(
            "Opening_Balances",
            "2025-12-31|210|S1",
            as_of_date=date(2025, 12, 31),
            account_code="210",
            counterparty_code="S1",
            debit_amount=Decimal("0"),
            credit_amount=Decimal("80"),
        ),
        *row(
            "AP_Opening",
            "S1|BILL-1",
            counterparty_code="S1",
            reference_code="BILL-1",
            original_amount=Decimal("80"),
            due_date=date(2026, 1, 31),
            account_code="210",
        ),
    ]
    result = preview_ar_ap(cells, 1, {"AP": "210"}, {"S1"})
    assert result.ready
    result = preview_ar_ap(cells + source(), 1, {"AR": "110", "AP": "210"}, {"S1", "C1"})
    assert not result.ready
    assert "CUTOVER_DATE_MISMATCH" in {issue.code for issue in result.issues}


def test_open_item_row_key_must_match_reference() -> None:
    cells = source()
    changed = [
        Cell(cell.field_code, "arbitrary", cell.value, cell.source_type)
        if cell.row_key == "C1|INV-2"
        else cell
        for cell in cells
    ]
    result = preview_ar_ap(changed, 3, {"AR": "110"}, {"C1"})
    assert not result.ready
    assert "OPEN_ITEM_KEY_MISMATCH" in {issue.code for issue in result.issues}
