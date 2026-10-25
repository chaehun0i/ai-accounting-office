# 회사별 보고기간 조회 계약

`GET /report-periods/resolve`는 `X-Company-ID`와 재무제표 조회 권한을 확인한 뒤 기간 preset을 실제 날짜로 해석한다. `TODAY`, `THIS_WEEK`, `THIS_MONTH`, `THIS_YEAR`, `CUSTOM`을 지원하며 `period_mode=RANGE`는 `date_from/date_to`, `period_mode=AS_OF`는 `as_of`를 반환한다. 서버는 회사 timezone, 회계연도 시작월, 회계 설정의 `reporting_week_start`(월요일 0~일요일 6)를 사용한다.

`CUSTOM`의 RANGE는 시작·종료일을, AS_OF는 기준일을 명시해야 한다. 역전 범위, 회사 개업일 이전 및 현지 오늘 이후 조회는 오류로 처리한다. Preset 범위가 개업일을 걸치면 시작일을 개업일로 제한하고 `partial=true`를 반환한다. 현재 기간의 AS_OF는 회사 현지 오늘 날짜를 기준으로 한다. 기간 해석은 장부나 제표를 생성하지 않는 읽기 작업이다.

## Report Center V1 사용자 경로

`/reports`에서 재무상태표(BS), 손익계산서(IS), 재무비율 중 하나와 CLOSED 회계기간을 고릅니다. Preset 또는 사용자 지정 날짜를 서버 Resolver에 전달하고, 화면에 반환된 실제 기준일(AS_OF)이나 시작·종료일(RANGE)을 확인합니다. 현재 V1 생성은 선택한 CLOSED 회계기간과 해석된 날짜가 정확히 일치하고 해당 기간의 BS/IS 관계형 스냅샷이 있을 때만 허용합니다. 재무제표 스냅샷이 없다면 `/financial-statements`에서 먼저 생성합니다.

PDF, XLSX, UTF-8 CSV를 지원합니다. 생성 요청은 회사·기간·스냅샷·버전·원천 digest를 관계형 Run에 고정하고, 완료된 파일은 관계형 Artifact와 기존 회사별 Storage에 보관합니다. 화면은 생성 상태, 실패 코드, 요청자·시각, 이력, 파일 다운로드를 제공합니다. 동일 멱등성 키는 같은 Run을 반환하며 실패 재시도는 원래 파일을 덮어쓰지 않는 새 Run입니다. 다운로드마다 회사 소속과 권한을 다시 검사합니다. 이 산출 과정은 전표·장부·재무제표 원천을 변경하지 않습니다.

V1은 작은 BS/IS·재무비율 파일을 요청 중 동기 생성합니다. CF/SCE/Notes, DOCX, LLM 설명문, 예약·이메일, Cloud Storage는 지원하지 않습니다.
