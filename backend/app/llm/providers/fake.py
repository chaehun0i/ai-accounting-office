"""외부 네트워크 없이 동일 계약을 검증하는 결정론적 Provider입니다."""

import json

from app.llm.contracts import T


class FakeProvider:
    code = "fake"
    model = "deterministic-v1"

    def generate(self, task: str, facts: str, schema: type[T], timeout_seconds: int) -> T:
        data = json.loads(facts)
        if task == "classify":
            return schema.model_validate({"category": "OTHER", "query_text": ""})
        if task == "route_accounting_question":
            question = data["question"]
            if "마감" in question or "결산" in question:
                return schema.model_validate({"capability": "CLOSING"})
            if "현금흐름" in question:
                return schema.model_validate(
                    {"capability": "CASH_FLOW", "line_code": "NET_OPERATING"}
                )
            if "자산" in question:
                return schema.model_validate({"capability": "BALANCE_SHEET", "line_code": "ASSETS"})
            if "부채" in question:
                return schema.model_validate(
                    {"capability": "BALANCE_SHEET", "line_code": "LIABILITIES"}
                )
            if "자본" in question:
                return schema.model_validate({"capability": "BALANCE_SHEET", "line_code": "EQUITY"})
            if "매출" in question:
                return schema.model_validate(
                    {"capability": "INCOME_STATEMENT", "line_code": "REVENUE"}
                )
            if "손익" in question or "순이익" in question:
                return schema.model_validate(
                    {"capability": "INCOME_STATEMENT", "line_code": "NET_PROFIT"}
                )
            return schema.model_validate({"capability": "UNSUPPORTED"})
        accounts = data["accounts"]
        return schema.model_validate(
            {
                "debit_account_id": accounts[0]["id"],
                "credit_account_id": accounts[1]["id"],
                "evidence_ids": data["evidence_ids"],
            }
        )
