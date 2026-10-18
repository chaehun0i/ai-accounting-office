# 회사별 보고기간 조회 계약

`GET /report-periods/resolve`는 `X-Company-ID`와 재무제표 조회 권한을 확인한 뒤 기간 preset을 실제 날짜로 해석한다. `TODAY`, `THIS_WEEK`, `THIS_MONTH`, `THIS_YEAR`, `CUSTOM`을 지원하며 `period_mode=RANGE`는 `date_from/date_to`, `period_mode=AS_OF`는 `as_of`를 반환한다. 서버는 회사 timezone, 회계연도 시작월, 회계 설정의 `reporting_week_start`(월요일 0~일요일 6)를 사용한다.

`CUSTOM`의 RANGE는 시작·종료일을, AS_OF는 기준일을 명시해야 한다. 역전 범위, 회사 개업일 이전 및 현지 오늘 이후 조회는 오류로 처리한다. Preset 범위가 개업일을 걸치면 시작일을 개업일로 제한하고 `partial=true`를 반환한다. 현재 기간의 AS_OF는 회사 현지 오늘 날짜를 기준으로 한다. 기간 해석은 장부나 제표를 생성하지 않는 읽기 작업이다.
