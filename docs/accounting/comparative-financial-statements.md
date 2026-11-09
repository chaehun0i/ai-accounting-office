# 비교 재무제표 구현 범위

비교 재무제표는 기존 `financial_statement_snapshots`와 `financial_statement_lines`를 재사용한다. 비교 Snapshot은 현재 및 비교기간의 CLOSED BS/IS 원본 Snapshot Line을 참조하고, 전기 원본 금액과 전기 표시 금액을 별도로 보존한다. 원본 POSTED Journal이나 원본 재무제표 금액은 수정하지 않는다.

현재 지원 범위는 같은 회사의 기간 길이가 같은(윤일 차이 1일 이내) CLOSED Balance Sheet와 Income Statement 비교다. 두 기간의 taxonomy 및 표시 항목 구성이 일치해야 한다. Cash Flow, SCE, Notes 비교, taxonomy bridge 및 전기 재작성은 지원하지 않으며 추정값으로 채우지 않는다.

재분류는 설명 근거가 있는 전기 표시 금액 이동이다. 같은 재무제표 유형과 같은 차변/대변 표시 부호의 LEAF 항목끼리만 허용하며, 금액 총계와 파생 합계를 다시 계산한다. 원천 기간/매핑 digest가 바뀌거나 승인 대상 digest가 달라지면 검토·승인·Export를 차단한다.

상태는 DRAFT → REVIEW_REQUESTED → APPROVED/REJECTED다. 작성자 본인은 승인할 수 없다. 승인된 비교 Snapshot과 라인은 DB trigger 및 서비스 경계에서 동결된다. Report Center Export는 승인된 revision을 고정하고 `INTERNAL_VALIDATION_ONLY`를 표시한다. 이 상태는 법정 제출 승인이나 외부 감사 완료를 의미하지 않는다.
