"""native Sheet 스냅샷을 기존 Intake 계약으로 투영하며 원본은 변경하지 않습니다."""

import csv
from decimal import Decimal
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).parent


def rows(industry: str, kind: str) -> list[dict[str, str]]:
    with (ROOT / f"native-{industry}-v1" / f"{kind}_Transactions.csv").open(
        encoding="utf-8", newline=""
    ) as source:
        return list(csv.DictReader(source))


def canonical_csv(industry: str, kind: str) -> bytes:
    buffer = StringIO(newline="")
    fields = [
        "source_id",
        "date",
        "amount",
        "currency",
        "direction",
        "description",
        "counterparty",
        "raw_reference",
    ]
    if kind == "Card":
        fields.append("source_status")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for source in rows(industry, kind):
        status = source.get("source_status", source.get("status", "CAPTURED"))
        value = {
            "source_id": source["source_id"],
            "date": source["occurred_at" if kind == "Bank" else "approved_at"],
            "amount": format(Decimal(source["amount"]), "f"),
            "currency": "KRW",
            "direction": source.get(
                "direction",
                ("OUT" if status == "REFUNDED" else "IN")
                if industry == "retail"
                else ("IN" if status == "REFUNDED" else "OUT"),
            ),
            "description": source.get("description", source.get("merchant_name", "")),
            "counterparty": source.get("merchant_name", ""),
            "raw_reference": source.get(
                "reference_no", source.get("expected_match", source.get("expected_document", ""))
            ),
        }
        if kind == "Card":
            value["source_status"] = status
        writer.writerow(value)
    return buffer.getvalue().encode("utf-8")
