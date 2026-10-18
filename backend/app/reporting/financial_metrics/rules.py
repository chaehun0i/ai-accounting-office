"""Versioned formulas for metrics supported by the current BS/IS taxonomy."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class Formula:
    code: str
    numerator: str
    denominator: str
    version: int = 1


FORMULAS = (
    Formula("DEBT_RATIO", "LIABILITIES", "ASSETS"),
    Formula("DEBT_TO_EQUITY", "LIABILITIES", "EQUITY"),
    Formula("EQUITY_RATIO", "EQUITY", "ASSETS"),
    Formula("GROSS_MARGIN", "GROSS_PROFIT", "REVENUE"),
    Formula("OPERATING_MARGIN", "OPERATING_PROFIT", "REVENUE"),
    Formula("NET_MARGIN", "NET_PROFIT", "REVENUE"),
)


@dataclass(frozen=True)
class Metric:
    metric_code: str
    formula_version: int
    numerator_line_code: str
    denominator_line_code: str
    numerator: Decimal
    denominator: Decimal
    value: Decimal | None
    status: Literal["AVAILABLE", "ZERO_DENOMINATOR"]
    unit: Literal["RATIO"] = "RATIO"


def calculate(lines: dict[str, Decimal]) -> tuple[Metric, ...]:
    """Keep unrounded Decimal facts; a missing denominator is never treated as zero."""
    result = []
    for formula in FORMULAS:
        numerator = lines[formula.numerator]
        denominator = lines[formula.denominator]
        result.append(
            Metric(
                metric_code=formula.code,
                formula_version=formula.version,
                numerator_line_code=formula.numerator,
                denominator_line_code=formula.denominator,
                numerator=numerator,
                denominator=denominator,
                value=numerator / denominator if denominator else None,
                status="AVAILABLE" if denominator else "ZERO_DENOMINATOR",
            )
        )
    return tuple(result)
