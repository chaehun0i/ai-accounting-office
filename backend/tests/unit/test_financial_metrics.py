from decimal import Decimal

from app.reporting.financial_metrics.rules import calculate


def test_supported_formulas_use_statement_facts_without_rounding():
    metrics = {
        m.metric_code: m
        for m in calculate(
            {
                "ASSETS": Decimal("100"),
                "LIABILITIES": Decimal("40"),
                "EQUITY": Decimal("60"),
                "REVENUE": Decimal("80"),
                "GROSS_PROFIT": Decimal("24"),
                "OPERATING_PROFIT": Decimal("16"),
                "NET_PROFIT": Decimal("8"),
            }
        )
    }
    assert metrics["DEBT_RATIO"].value == Decimal("0.4")
    assert metrics["DEBT_TO_EQUITY"].value == Decimal("40") / Decimal("60")
    assert metrics["EQUITY_RATIO"].value == Decimal("0.6")
    assert metrics["GROSS_MARGIN"].value == Decimal("0.3")
    assert metrics["OPERATING_MARGIN"].value == Decimal("0.2")
    assert metrics["NET_MARGIN"].value == Decimal("0.1")


def test_zero_denominator_retains_facts_and_explicit_status():
    metrics = calculate(
        {
            "ASSETS": Decimal("0"),
            "LIABILITIES": Decimal("10"),
            "EQUITY": Decimal("0"),
            "REVENUE": Decimal("0"),
            "GROSS_PROFIT": Decimal("0"),
            "OPERATING_PROFIT": Decimal("-5"),
            "NET_PROFIT": Decimal("-5"),
        }
    )
    assert all(metric.value is None and metric.status == "ZERO_DENOMINATOR" for metric in metrics)
    assert metrics[-1].numerator == Decimal("-5")
