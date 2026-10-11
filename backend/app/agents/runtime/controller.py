"""결정론 검증 실패는 모델의 신뢰도와 관계없이 차단합니다."""

from typing import Literal


def verdict(
    errors: list[str], evidence_sufficient: bool, category: str
) -> Literal["PASS", "REVIEW", "BLOCK"]:
    if errors:
        return "BLOCK"
    if not evidence_sufficient or category == "OTHER":
        return "REVIEW"
    return "PASS"
