"""결정론 검증 실패는 모델의 신뢰도와 관계없이 차단합니다."""

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


def verdict(
    errors: list[str], evidence_sufficient: bool, category: str
) -> Literal["PASS", "REVIEW", "BLOCK"]:
    if errors:
        return "BLOCK"
    if not evidence_sufficient or category == "OTHER":
        return "REVIEW"
    return "PASS"


class AccountingAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    amount: Decimal | None
    resource_id: UUID
    source_digest: str
    source_ids: list[UUID]


def reporting_answer(
    tool_code: str, result: dict[str, Any], line_code: str | None
) -> AccountingAnswer:
    """모델 서술 대신 Tool의 숫자·상태·출처만으로 답변을 고정합니다."""
    data = result["data"]
    if tool_code == "closing.readiness":
        status = data["period_status"]
        blockers = data["blocker_count"]
        stale = data["stale"]
        text = f"회계기간 상태는 {status}이며 차단 검사는 {blockers}건입니다."
        blocked = [check for check in data["checks"] if check["severity"] == "BLOCKER"]
        if blocked:
            details = ", ".join(
                f"{check['check_code']} (영향 금액 {Decimal(check['amount_impact'])})"
                for check in blocked
            )
            text += f" 차단 항목: {details}."
        if stale:
            text += " 마감 검사 기준이 변경되어 다시 검사해야 합니다."
        return AccountingAnswer(
            text=text,
            amount=None,
            resource_id=UUID(data["run_id"] or data["period_id"]),
            source_digest=data["source_digest"],
            source_ids=[UUID(check["source_id"]) for check in data["checks"] if check["source_id"]],
        )
    line = next(row for row in data["lines"] if row["line_code"] == line_code)
    amount = Decimal(line["current_amount"])
    text = (
        f"{line['label']}은(는) {amount}입니다. "
        f"마감 버전 {data['close_version']}의 스냅샷 기준입니다."
    )
    accounts = sorted(
        {
            f"{source['account_code']} {source['account_name']}"
            for source in data["sources"]
            if source.get("account_code") and source.get("account_name")
        }
    )
    if accounts:
        text += f" 연결 계정: {', '.join(accounts[:5])}"
        if len(accounts) > 5:
            text += f" 외 {len(accounts) - 5}개"
        text += "."
    return AccountingAnswer(
        text=text,
        amount=amount,
        resource_id=UUID(data["statement_set_id"]),
        source_digest=data["snapshot_digest"],
        source_ids=[UUID(source["journal_line_id"]) for source in data["sources"]],
    )


def reporting_verdict(
    tool_code: str, result: dict[str, Any], line_code: str | None, answer: AccountingAnswer
) -> Literal["PASS", "BLOCK"]:
    data = result["data"]
    if tool_code == "closing.readiness" and data["blocker_count"] != sum(
        check["severity"] == "BLOCKER" for check in data["checks"]
    ):
        return "BLOCK"
    if tool_code == "financial_statement.read" and (
        data["period_status"] != "CLOSED"
        or data["statement_status"] != "GENERATED"
        or not line_code
    ):
        return "BLOCK"
    expected = reporting_answer(tool_code, result, line_code)
    return "PASS" if answer == expected else "BLOCK"
