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
        accounts = data["accounts"]
        return schema.model_validate(
            {
                "debit_account_id": accounts[0]["id"],
                "credit_account_id": accounts[1]["id"],
                "evidence_ids": data["evidence_ids"],
            }
        )
