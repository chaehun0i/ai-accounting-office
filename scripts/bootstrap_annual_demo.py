"""로컬 합성회사 2025년 매출·매입·정산을 기존 인증 API로 준비합니다.

원본 fixture를 수정하지 않으며 실제 은행 이체나 세무 신고를 수행하지 않습니다.
사용자 계정은 비공개 .local 파일에만 저장합니다. 재실행은 저장된 자원과 키를 재사용합니다.
"""

import argparse
import configparser
import csv
import json
import secrets
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "backend/tests/fixtures/finance/native-2025-v1"
PRIVATE = ROOT / ".local/annual-demo-accounts.ini"
PROGRESS = ROOT / ".local/annual-demo-progress-v2.json"


def fixture_rows(sheet):
    with (FIXTURE / (sheet + ".csv")).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def amount(value):
    return Decimal(value.replace(",", ""))


class Demo:
    def __init__(self, origin):
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.path
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("로컬 HTTP 서버만 사용할 수 있습니다.")
        self.origin = origin
        self.config = configparser.ConfigParser()
        PRIVATE.parent.mkdir(exist_ok=True)
        if PRIVATE.exists():
            self.config.read(PRIVATE, encoding="utf-8")
        else:
            for label, email in [
                ("체험 회계담당자", "annual-demo@example.com"),
                ("체험 승인담당자", "annual-reviewer@example.com"),
            ]:
                self.config[label] = {
                    "이메일": email,
                    "비밀번호": secrets.token_urlsafe(24),
                }
            with PRIVATE.open("x", encoding="utf-8") as output:
                self.config.write(output)
        self.state = (
            json.loads(PROGRESS.read_text(encoding="utf-8"))
            if PROGRESS.exists()
            else {}
        )
        self.tokens = {}
        self.renewed = 0.0
        self.company = self.state.get("company")

    def save(self):
        temporary = PROGRESS.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(PROGRESS)

    def call(
        self, path, body=None, *, actor="writer", method=None, key=None, scoped=True
    ):
        headers = {"Content-Type": "application/json", "X-CSRF-Protection": "1"}
        if actor in self.tokens:
            headers["Authorization"] = "Bearer " + self.tokens[actor]
        if scoped and self.company:
            headers["X-Company-ID"] = self.company
        if key:
            headers["Idempotency-Key"] = "annual-demo-v2-" + key
        payload = json.dumps(body).encode() if body is not None else None
        try:
            with urlopen(
                Request(
                    self.origin + path, data=payload, headers=headers, method=method
                ),
                timeout=90,
            ) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except HTTPError as error:
            # 원문·자격 증명·토큰을 오류 메시지에 포함하지 않습니다.
            raise RuntimeError(
                f"합성 데이터 요청 실패: {method or ('POST' if body is not None else 'GET')} HTTP {error.code}"
            ) from None

    def login(self, register=False):
        for actor, label in [
            ("writer", "체험 회계담당자"),
            ("owner", "체험 승인담당자"),
        ]:
            values = self.config[label]
            credentials = {"email": values["이메일"], "password": values["비밀번호"]}
            try:
                result = self.call("/auth/login", credentials, actor=None, scoped=False)
            except RuntimeError as error:
                if not register or "HTTP 401" not in str(error):
                    raise
                result = self.call(
                    "/auth/register", credentials, actor=None, scoped=False
                )
            self.tokens[actor] = result["access_token"]
        self.renewed = monotonic()

    def renew(self):
        if monotonic() - self.renewed > 200:
            self.login()

    def prepare(self):
        self.login(register=True)
        companies = self.call("/companies", actor="owner")
        if self.company and not any(c["id"] == self.company for c in companies):
            raise ValueError(
                "저장된 체험 회사에 접근할 수 없습니다. 기존 자료는 덮어쓰지 않습니다."
            )
        if not self.company:
            name = "가온푸드웍스 · 2025 연간 체험회사"
            company = next((c for c in companies if c["company_name"] == name), None)
            if company is None:
                company = self.call(
                    "/companies",
                    {
                        "company_name": name,
                        "business_number": "9876543210",
                        "corporation_number": "1101111234567",
                        "taxpayer_type": "CORPORATION",
                        "opening_date": "2025-01-01",
                        "address": "합성 데이터 체험용 주소",
                    },
                    actor="owner",
                )
            self.company = company["id"]
            self.state["company"] = self.company
            self.save()
        if not any(c["id"] == self.company for c in self.call("/companies")):
            invite = self.call(
                f"/companies/{self.company}/invitations",
                {
                    "email": self.config["체험 회계담당자"]["이메일"],
                    "role_code": "ACCOUNTANT",
                },
                actor="owner",
            )
            self.call("/invitations/" + invite["invite_token"] + "/accept", {})
        workspace = self.call("/onboarding", actor="owner")
        if workspace["status"] != "COMPLETED":
            workspace = self.call(
                "/onboarding/values",
                {
                    "expected_version": workspace["version"],
                    "values": [
                        {"field_code": "Company.no_opening_balance", "value": True}
                    ],
                },
                actor="owner",
                method="PATCH",
            )
            self.call(
                "/onboarding/complete",
                {"expected_version": workspace["version"]},
                actor="owner",
                key="setup-" + str(workspace["version"]),
            )
        self.accounts = {a["account_name"]: a["id"] for a in self.call("/accounts")}
        self.periods = {
            p["start_date"][:7]: p["id"] for p in self.call("/accounting/periods")
        }
        self.counterparties = self.state.setdefault("counterparties", {})
        existing_parties = {
            c["display_name"]: c["id"] for c in self.call("/counterparties")
        }
        for row in fixture_rows("Counterparties"):
            label = row["counterparty_code"] + " · " + row["legal_name"]
            if label in existing_parties:
                self.counterparties[row["counterparty_code"]] = existing_parties[label]
            if row["counterparty_code"] not in self.counterparties:
                value = self.call(
                    "/counterparties",
                    {
                        "business_number": row["business_number"],
                        "display_name": label,
                        "legal_name": row["legal_name"],
                        "roles": [
                            {
                                "role_code": row["counterparty_type"],
                                "effective_from": "2025-01-01",
                            }
                        ],
                    },
                )
                self.counterparties[row["counterparty_code"]] = value["id"]
            self.save()

    def posted(self, identifier, day, lines, source_type, cp=None):
        self.renew()
        name = "journal:" + identifier
        if name in self.state:
            journal = self.call("/journals/" + self.state[name])
        else:
            total = sum(
                (Decimal(line.get("debit_amount", "0")) for line in lines), Decimal(0)
            )
            transaction = None
            if source_type != "MANUAL":
                transaction = self.call(
                    "/transactions",
                    {
                        "transaction_date": day,
                        "accounting_date": day,
                        "description": "2025 합성 체험 " + identifier,
                        "amount": str(total),
                        "direction": "INFLOW" if source_type == "SALES" else "OUTFLOW",
                        "source_type": source_type,
                        "source_system": "SYN_MFG_001_DEMO_V2",
                        "source_id": identifier,
                        "counterparty_id": cp,
                    },
                    key="txn-" + identifier,
                )
            journal = self.call(
                "/journals",
                {
                    "entry_date": day,
                    "accounting_period_id": self.periods[day[:7]],
                    "description": "2025 합성 체험 " + identifier,
                    "source_type": "TRANSACTION" if transaction else "MANUAL",
                    "source_transaction_id": transaction["id"] if transaction else None,
                    "lines": lines,
                },
                key="journal-" + identifier,
            )
            self.state[name] = journal["id"]
            self.save()
        for before, action, actor in [
            ("DRAFT", "submit", "writer"),
            ("PROPOSED", "request-review", "writer"),
            ("REVIEW_REQUIRED", "approve", "owner"),
            ("APPROVED", "post", "owner"),
        ]:
            if journal["status"] == before:
                journal = self.call(
                    f"/journals/{journal['id']}/{action}",
                    {
                        "expected_version": journal["version"],
                        "approval_id": journal["approval_id"],
                        "reason": "로컬 합성 체험 데이터 사전 승인",
                    },
                    actor=actor,
                    key=identifier + "-" + action,
                )
        if journal["status"] != "POSTED":
            raise ValueError("체험 전표 상태를 확인해야 합니다.")
        return journal

    def populate(self):
        rejected = []
        next_year = []
        for kind, invoice_sheet, settlement_sheet, day_field, id_field in [
            (
                "AR",
                "Sales_Invoices",
                "AR_Collections",
                "received_date",
                "collection_id",
            ),
            ("AP", "Purchase_Invoices", "AP_Payments", "payment_date", "payment_id"),
        ]:
            path = "receivables" if kind == "AR" else "payables"
            settlement_path = "collections" if kind == "AR" else "payments"
            control = self.accounts["매출채권" if kind == "AR" else "매입채무"]
            invoices = {r["invoice_no"]: r for r in fixture_rows(invoice_sheet)}
            targets = {}
            for index, row in enumerate(invoices.values(), 1):
                cp = self.counterparties[row["counterparty_code"]]
                lines = [
                    {
                        "account_id": control,
                        "counterparty_id": cp,
                        "debit_amount" if kind == "AR" else "credit_amount": str(
                            amount(row["total_amount"])
                        ),
                    },
                    {
                        "account_id": self.accounts[
                            "매출" if kind == "AR" else "소모품비"
                        ],
                        "credit_amount" if kind == "AR" else "debit_amount": str(
                            amount(row["supply_amount"])
                        ),
                    },
                    {
                        "account_id": self.accounts[
                            "부가세예수금" if kind == "AR" else "부가세대급금"
                        ],
                        "credit_amount" if kind == "AR" else "debit_amount": str(
                            amount(row["vat_amount"])
                        ),
                    },
                ]
                journal = self.posted(
                    row["invoice_no"],
                    row["invoice_date"],
                    lines,
                    "SALES" if kind == "AR" else "PURCHASE",
                    cp,
                )
                targets[row["invoice_no"]] = self.call(
                    f"/{path}/from-journals",
                    {"journal_id": journal["id"], "due_date": row["due_date"]},
                )[0]
                if index % 40 == 0:
                    print(f"{kind} 발생 {index}/{len(invoices)}", flush=True)
            groups = defaultdict(list)
            for row in fixture_rows(settlement_sheet):
                groups[row[id_field]].append(row)
            for index, (identifier, rows) in enumerate(groups.items(), 1):
                # 이번 체험은 2025년 말 기준입니다. 다음 해 정산은 원본에 남겨 둡니다.
                if any(r[day_field] > "2025-12-31" for r in rows):
                    next_year.append(identifier)
                    continue
                if any(
                    r[day_field] < invoices[r["invoice_no"]]["invoice_date"]
                    for r in rows
                ):
                    rejected.append(identifier)
                    continue
                total = sum((amount(r["allocated_amount"]) for r in rows), Decimal(0))
                lines = [
                    {
                        "account_id": self.accounts["보통예금"],
                        "debit_amount" if kind == "AR" else "credit_amount": str(total),
                    }
                ]
                for row in rows:
                    lines.append(
                        {
                            "account_id": control,
                            "counterparty_id": self.counterparties[
                                invoices[row["invoice_no"]]["counterparty_code"]
                            ],
                            "credit_amount" if kind == "AR" else "debit_amount": str(
                                amount(row["allocated_amount"])
                            ),
                        }
                    )
                journal = self.posted(identifier, rows[0][day_field], lines, "MANUAL")
                record = self.call(
                    f"/{settlement_path}",
                    {
                        "journal_id": journal["id"],
                        "settlement_date": rows[0][day_field],
                        "total_amount": str(total),
                    },
                    key="settlement-" + identifier,
                )
                if record["status"] == "DRAFT":
                    # 현재 version을 다시 읽어 이전 배분의 재시도와 충돌하지 않게 합니다.
                    current = {
                        r["id"]: r for r in self.call(f"/{path}?as_of=2026-12-31")
                    }
                    allocations = [
                        {
                            "target_id": targets[r["invoice_no"]]["id"],
                            "expected_version": current[targets[r["invoice_no"]]["id"]][
                                "version"
                            ],
                            "allocated_amount": str(amount(r["allocated_amount"])),
                        }
                        for r in rows
                    ]
                    if not record["allocations"]:
                        record = self.call(
                            f"/{settlement_path}/{record['id']}/allocations",
                            {
                                "expected_version": record["version"],
                                "allocations": allocations,
                            },
                            key="allocate-" + identifier,
                        )
                    self.call(
                        f"/{settlement_path}/{record['id']}/confirm",
                        {"expected_version": record["version"]},
                        key="confirm-" + identifier,
                    )
                if index % 40 == 0:
                    print(f"{kind} 정산 {index}/{len(groups)}", flush=True)
            report = self.call(f"/{path}/reconciliation?as_of=2025-12-31")
            if report["status"] != "MATCHED":
                raise ValueError("보조부와 원장 대사에 차이가 있습니다.")
            self.state[kind + "_report"] = report
            self.save()
            print(
                f"{kind} 2025-12-31 대사 일치: {report['subledger_amount']}", flush=True
            )
        self.state["rejected_source_batches"] = rejected
        self.state["next_year_batches"] = next_year
        self.state["completed"] = True
        self.save()
        print("2025년 매출·매입·수금·지급 체험 데이터를 준비했습니다.")
        print(
            f"원본 오류 정산 {len(rejected)}개와 다음 해 정산 {len(next_year)}개는 수정하지 않고 제외했습니다."
        )
        print(
            "로그인: annual-demo@example.com / 비밀번호 파일: .local/annual-demo-accounts.ini"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--approve-synthetic-fixture",
        action="store_true",
        help="합성 전표에 대해 분리된 작성자/승인자 API 실행을 허용합니다.",
    )
    args = parser.parse_args()
    if not args.approve_synthetic_fixture:
        parser.error(
            "합성 데이터 사전 승인에는 --approve-synthetic-fixture가 필요합니다."
        )
    demo = Demo(args.origin)
    if demo.state.get("completed"):
        demo.login()
        for kind, path in (("AR", "receivables"), ("AP", "payables")):
            report = demo.call(f"/{path}/reconciliation?as_of=2025-12-31")
            if report["status"] != "MATCHED":
                raise ValueError("완료된 체험 자료의 원장 대사를 확인해 주세요.")
            print(f"{kind} 기존 체험 자료 대사 일치: {report['subledger_amount']}")
        print("준비된 체험 자료를 재사용했습니다. 자료를 추가하지 않았습니다.")
        return
    demo.prepare()
    demo.populate()


if __name__ == "__main__":
    main()
