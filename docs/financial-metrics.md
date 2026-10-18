# 재무비율 1차 구현

`GET /financial-metrics?period_id=...`는 회사 권한을 확인하고 현재 `CLOSED` 기간의 최신 BS/IS 스냅샷에서 비율을 계산한다. 응답에는 스냅샷 ID와 digest, 공식 버전, 분자·분모 금액과 제표 항목 코드, 비율값, 데이터 상태가 포함된다. 계산은 `Decimal`이며 저장된 제표 숫자를 변경하지 않는다.

현재 제공하는 공식은 부채비율(`LIABILITIES / ASSETS`), 부채자본비율(`LIABILITIES / EQUITY`), 자기자본비율(`EQUITY / ASSETS`), 매출총이익률(`GROSS_PROFIT / REVENUE`), 영업이익률(`OPERATING_PROFIT / REVENUE`), 순이익률(`NET_PROFIT / REVENUE`)이다. 분모가 0이면 `value=null`, `status=ZERO_DENOMINATOR`로 반환한다.

유동·당좌비율은 현행 BS가 유동/비유동 자산·부채를 구분하지 않아 계산하지 않는다. ROA/ROE, 회전율, 성장률, 현금전환주기는 비교기간 및 평균잔액 원천이 필요하다. 정본의 재무비율 문서에 정의된 해당 지표의 개발은 분류체계와 비교기간이 구현된 뒤 진행한다. 이 1차 API는 조회 모델이며 정본의 `financial_metric_runs`/`financial_metric_values` 저장 및 trend/drilldown API는 후속 범위다.
