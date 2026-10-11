"""native Sheet의 읽기 전용 CSV snapshot으로 연간 보조부를 검증합니다."""

import csv
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from time import monotonic
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.accounting.periods.infrastructure.models import PeriodModel
from tests.integration.test_finance_allocations import confirm
from tests.integration.test_finance_flow import (
    allocate,
    create_settlement,
    finance_setup,
    post_journal,
)

ROOT = Path(__file__).parents[1] / "fixtures/finance/native-2025-v1"


def rows(sheet):
    with (ROOT / f"{sheet}.csv").open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def amount(value):
    return Decimal(value.replace(",", ""))


def test_syn_mfg_001_full_year(api_client, auth_service):
    owner, writer, payload, accounts, _, connection = finance_setup(api_client, auth_service)
    renewed_at = monotonic()

    def renew_access():
        nonlocal renewed_at
        if monotonic() - renewed_at < 240:
            return
        # 연간 회귀가 오래 걸려도 운영 토큰 수명을 늘리지 않고 다시 인증합니다.
        for headers, email in (
            (owner, "onboarding@example.com"),
            (writer, "accountant@example.com"),
        ):
            response = api_client.post(
                "/auth/login", json={"email": email, "password": "StrongPassword!2026"}
            )
            assert response.status_code == 200, response.text
            headers["Authorization"] = "Bearer " + response.json()["access_token"]
        renewed_at = monotonic()

    company = UUID(writer["X-Company-ID"])
    # 과거 회계기간만 테스트 DB에 준비합니다. 운영 migration이나 양식은 수정하지 않습니다.
    periods = {}
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        for month in range(1, 13):
            resource = uuid4()
            periods[f"2025-{month:02d}"] = str(resource)
            session.add(
                PeriodModel(
                    id=resource,
                    company_id=company,
                    fiscal_year=2025,
                    period_no=month,
                    start_date=date(2025, month, 1),
                    end_date=date(2025, month, monthrange(2025, month)[1]),
                    status="OPEN",
                    version=1,
                )
            )
        session.commit()
    for period in api_client.get("/accounting/periods", headers=writer).json():
        periods[period["start_date"][:7]] = period["id"]
    counterparties = {}
    for row in rows("Counterparties"):
        response = api_client.post(
            "/counterparties",
            headers=writer,
            json={
                "display_name": row["legal_name"],
                "legal_name": row["legal_name"],
                "roles": [{"role_code": row["counterparty_type"], "effective_from": "2025-01-01"}],
            },
        )
        assert response.status_code == 201, response.text
        counterparties[row["counterparty_code"]] = response.json()["id"]

    def posted(day, lines, description):
        renew_access()
        return post_journal(
            api_client,
            owner,
            writer,
            {**payload, "entry_date": day, "accounting_period_id": periods[day[:7]]},
            lines,
            description,
        )

    for kind, source_sheet, settlement_sheet, day_column, header_column in [
        ("AR", "Sales_Invoices", "AR_Collections", "received_date", "collection_id"),
        ("AP", "Purchase_Invoices", "AP_Payments", "payment_date", "payment_id"),
    ]:
        targets = "receivables" if kind == "AR" else "payables"
        invoices = rows(source_sheet)
        assert len(invoices) == (240 if kind == "AR" else 74)
        sources = {row["invoice_no"]: row for row in invoices}
        obligations = {}
        control = accounts["매출채권" if kind == "AR" else "매입채무"]
        for row in invoices:
            cp = counterparties[row["counterparty_code"]]
            journal = posted(
                row["invoice_date"],
                [
                    {
                        "account_id": control,
                        "counterparty_id": cp,
                        "debit_amount" if kind == "AR" else "credit_amount": str(
                            amount(row["total_amount"])
                        ),
                    },
                    {
                        "account_id": accounts["매출" if kind == "AR" else "소모품비"],
                        "credit_amount" if kind == "AR" else "debit_amount": str(
                            amount(row["supply_amount"])
                        ),
                    },
                    {
                        "account_id": accounts["부가세예수금" if kind == "AR" else "부가세대급금"],
                        "credit_amount" if kind == "AR" else "debit_amount": str(
                            amount(row["vat_amount"])
                        ),
                    },
                ],
                row["invoice_no"],
            )
            response = api_client.post(
                f"/{targets}/from-journals",
                headers=writer,
                json={"journal_id": journal["id"], "due_date": row["due_date"]},
            )
            assert response.status_code == 200, response.text
            obligations[row["invoice_no"]] = response.json()[0]
        groups = defaultdict(list)
        for row in rows(settlement_sheet):
            groups[row[header_column]].append(row)
        rejected = []
        applied = defaultdict(lambda: Decimal(0))
        for identifier, lines in groups.items():
            # 정본에 실제로 존재하는 선행일자 오류를 명시적으로 보고하고 전체 batch를 거부합니다.
            # 원본 날짜를 고치거나 유효한 일부 행만 몰래 승격하지 않습니다.
            if any(row[day_column] < sources[row["invoice_no"]]["invoice_date"] for row in lines):
                rejected.append(identifier)
                continue
            total = sum((amount(row["allocated_amount"]) for row in lines), Decimal(0))
            day = lines[0][day_column]
            journal_lines = [
                {
                    "account_id": accounts["보통예금"],
                    "debit_amount" if kind == "AR" else "credit_amount": str(total),
                }
            ]
            for row in lines:
                journal_lines.append(
                    {
                        "account_id": control,
                        "counterparty_id": counterparties[
                            sources[row["invoice_no"]]["counterparty_code"]
                        ],
                        "credit_amount" if kind == "AR" else "debit_amount": str(
                            amount(row["allocated_amount"])
                        ),
                    }
                )
            journal = posted(day, journal_lines, identifier)
            path, record = create_settlement(api_client, writer, journal, kind, total)
            record = allocate(
                api_client,
                writer,
                path,
                record,
                [
                    (obligations[row["invoice_no"]], amount(row["allocated_amount"]))
                    for row in lines
                ],
            )
            response = confirm(api_client, writer, path, record)
            assert response.status_code == 200, response.text
            if day <= "2025-12-31":
                for row in lines:
                    applied[row["invoice_no"]] += amount(row["allocated_amount"])
        assert rejected == (["COLL_MULTI_001"] if kind == "AR" else ["PAY_MULTI_001"])
        expected = sum(
            (amount(row["total_amount"]) - applied[row["invoice_no"]] for row in invoices),
            Decimal(0),
        )
        result = api_client.get(f"/{targets}?as_of=2025-12-31", headers=writer).json()
        assert len(result) == len(invoices)
        assert sum(Decimal(row["outstanding_amount"]) for row in result) == expected
        assert {row["status"] for row in result} >= {"OPEN", "PARTIAL"}
        report = api_client.get(
            f"/{targets}/reconciliation?as_of=2025-12-31", headers=writer
        ).json()
        assert report["status"] == "MATCHED"
        assert Decimal(report["subledger_amount"]) == Decimal(report["gl_amount"]) == expected
        aging = api_client.get(f"/{targets}/aging?as_of=2025-12-31", headers=writer).json()
        assert Decimal(aging["total_outstanding"]) == expected
        assert sum(Decimal(value) for value in aging["buckets"].values()) == expected
        assert Decimal(aging["overdue"]) > 0
        assert len(aging["counterparties"]) == (12 if kind == "AR" else 8)
