# 현금흐름표 회계 계약과 제품 범위

현금흐름표는 CLOSED 기간의 POSTED Journal, 조정 시산표와 BS/IS 스냅샷을 원천으로 사용합니다. 직접 현금 이벤트와 간접법 영업현금흐름을 대사한 뒤 `RECONCILED` 관계형 스냅샷을 생성합니다. 이 상태는 내부 금액 검증을 뜻하며 법정 승인·감사·공시 완료를 뜻하지 않습니다.

## 회사별 이자·세금 정책

`GET/POST /cash-flow/policies`는 이자 지급·수취와 법인세 납부의 영업·투자·재무 활동 분류를 회사별로 관리합니다. 정책은 적용 시작일과 버전을 가진 추가 전용 관계형 이력입니다. 새 버전은 이전 버전보다 늦은 날짜에만 등록할 수 있습니다. 조회 응답의 종료일과 `LATEST`/`SUPERSEDED` 상태는 다음 버전의 시작일에서 계산합니다. 하나의 보고기간 중간에 정책이 바뀌면 스냅샷 생성을 차단합니다. 정책의 명시적 line code와 실제 현금 이벤트 활동이 맞지 않아도 차단합니다. 정책 미등록 기간은 기존 `TAX_INTEREST_OPERATING` v1의 영업활동 분류를 사용합니다.

정책·적용일·버전은 사전 점검과 간접법 bridge의 digest에 포함됩니다. 새 정책이 이전 CLOSED 기간에 적용되더라도 기존 스냅샷은 그대로 보존하고, 현재 조회와 신규 생성에서는 갱신된 원천을 요구합니다.

## 비현금 공시와 처분손익

`POST /cash-flow/non-cash-disclosures`는 같은 회사의 POSTED 전표에 있는 차변·대변 line, 연결 증빙, 원천 유형과 금액을 명시적으로 묶습니다. 현금 계정이 포함된 전표는 비현금 공시로 등록할 수 없고, 같은 line의 총 공시액이 POSTED 금액을 넘을 수 없습니다. 동일 원천·금액의 재요청은 기존 Fact를 반환합니다. `GET /cash-flow/non-cash-disclosures?period_id=…`는 현재 Fact를, `GET /cash-flow/{id}/disclosures`는 스냅샷에 고정된 Fact를 조회합니다. 공시액은 영업·투자·재무 현금흐름 합계에 넣지 않습니다.

`POST /cash-flow/disposal-sources`는 증빙이 연결된 POSTED 자산 처분 전표의 현금 유입 line, 자산 장부금액 감소 line과 처분손익 line을 관계형으로 연결합니다. 현재 지원하는 원천은 세 line의 금액이 정확히 닫히고, 처분 직전 POSTED 자산 잔액으로 장부금액을 확인할 수 있는 경우입니다. `DISPOSAL_GAIN` 조정 규칙과 실제 투자활동 현금 이벤트가 모두 필요합니다. 간접법에서는 이익을 차감하고 손실을 가산하며, 현금 유입은 투자활동에 한 번만 포함합니다. 근거가 부족한 복합 처분이나 미구현 자산대장 값은 추정하지 않고 차단합니다. 현재 Fact와 스냅샷 Fact는 각각 `/cash-flow/disposal-sources`와 `/cash-flow/{id}/disposals`에서 조회합니다.

정책, 공시, 처분 Fact, 전표·증빙과 조정 규칙은 스냅샷 provenance와 digest에 반영됩니다. 관계형 Fact와 스냅샷 연결은 추가 전용이며 회사별 인덱스와 회사 범위 외래키로 격리합니다. POSTED Journal이나 GL을 변경하지 않습니다.

## 조회와 Export

`/financial-statements`에서 정책 이력, 현재·스냅샷별 비현금 공시와 처분 원천, 차단 코드를 확인할 수 있습니다. `/reports`에서 CLOSED 기간의 현재 유효한 `RECONCILED` 현금흐름표를 PDF/XLSX/CSV로 생성하고 이력·다운로드를 조회합니다. 파일은 스냅샷 금액을 사용하며 `INTERNAL_VALIDATION_ONLY`를 표시합니다. 비현금 공시는 현금흐름 합계와 분리된 섹션에 표시합니다. 완료된 파일은 나중에 원천이 바뀌어도 덮어쓰지 않습니다.

## 남은 범위

Asset Register 전체 처분 업무, 복잡한 여러 line의 자산 처분 배분, SCE/Notes, 법정 승인·감사·공시, 새로운 회계 계산이나 LLM 금액 생성은 이 구현의 범위가 아닙니다. 별도 설계와 검증 없이 자동으로 추정하지 않습니다. 읽기 전용 설계 정본 `docs/AI_Accounting_Office_v0.2.6_통합설계_정본/`은 Git에 포함하지 않습니다.
