# 회사별 보고기간 조회 계약

`GET /report-periods/resolve`는 `X-Company-ID`와 재무제표 조회 권한을 확인한 뒤 기간 preset을 실제 날짜로 해석한다. `TODAY`, `THIS_WEEK`, `THIS_MONTH`, `THIS_YEAR`, `CUSTOM`을 지원하며 `period_mode=RANGE`는 `date_from/date_to`, `period_mode=AS_OF`는 `as_of`를 반환한다. 서버는 회사 timezone, 회계연도 시작월, 회계 설정의 `reporting_week_start`(월요일 0~일요일 6)를 사용한다.

`CUSTOM`의 RANGE는 시작·종료일을, AS_OF는 기준일을 명시해야 한다. 역전 범위, 회사 개업일 이전 및 현지 오늘 이후 조회는 오류로 처리한다. Preset 범위가 개업일을 걸치면 시작일을 개업일로 제한하고 `partial=true`를 반환한다. 현재 기간의 AS_OF는 회사 현지 오늘 날짜를 기준으로 한다. 기간 해석은 장부나 제표를 생성하지 않는 읽기 작업이다.

## Report Center V1 사용자 경로

`/reports`에서 다음 순서로 진행합니다.

1. 재무상태표(BS), 손익계산서(IS), 재무비율, 현금흐름표(CF), 자본변동표(SCE) 중 하나와 **마감된 회계기간**을 선택합니다. 마감된 기간이 없다면 `/closing`에서 마감 상태를 확인합니다.
2. 기간 preset 또는 사용자 지정 날짜를 고르고 **서버가 해석한 실제 기간**을 확인합니다. BS는 기준일(`AS_OF`), IS·재무비율·CF·SCE는 시작·종료일(`RANGE`)을 사용합니다. 회사 timezone·회계연도·주 시작일은 서버의 기존 Resolver가 적용합니다.
3. 선택한 CLOSED 기간의 종료일 또는 시작·종료일과 해석된 기간이 정확히 일치해야 **보고서 생성** 버튼이 활성화됩니다. Preset이 다른 기간을 가리킨다면 해당 마감 기간을 선택하거나 날짜를 직접 지정합니다. 해당 기간의 BS/IS 관계형 스냅샷이 없다면 `/financial-statements`에서 먼저 생성합니다. CF와 SCE는 같은 화면에서 대사를 마친 `RECONCILED` 스냅샷도 필요합니다.
4. PDF, XLSX, CSV 중 하나를 선택하고 생성합니다. 작은 V1 산출물은 요청 중 동기 생성되며 화면에 완료 또는 실패 상태가 표시됩니다.
5. **생성 이력**에서 보고서 종류·기간·형식·상태·생성자·시각·마감 버전·스냅샷 식별 정보를 확인하고 완료된 파일을 내려받습니다. 실패한 Run은 오류 사유를 확인하고 **재시도**할 수 있습니다. 상태가 진행 중이면 화면이 이력을 다시 조회합니다.

### 지원 범위와 권한

| 보고서 코드 | 화면 이름 | 기간 의미 | 출력 형식 |
| --- | --- | --- | --- |
| `BALANCE_SHEET` | 재무상태표 | `AS_OF` | PDF/XLSX/CSV |
| `INCOME_STATEMENT` | 손익계산서 | `RANGE` | PDF/XLSX/CSV |
| `FINANCIAL_METRICS` | 재무비율 | `RANGE` | PDF/XLSX/CSV |
| `CASH_FLOW` | 현금흐름표 | `RANGE` | PDF/XLSX/CSV |
| `CHANGES_IN_EQUITY` | 자본변동표 | `RANGE` | PDF/XLSX/CSV |

`report.read`는 화면과 catalog·상세 조회, `report.generate`와 `report.export`는 생성·재시도, `report.download_history`는 이력·Artifact 조회·다운로드에 필요합니다. 다운로드 요청마다 인증, 회사 소속, Run과 Artifact의 회사, 권한을 다시 확인합니다. 회사 전환 시 이전 회사의 화면 상태를 버립니다. 화면에서 버튼을 숨기는 것은 서버 권한 검사를 대신하지 않습니다.

### 생성 기록과 오류 처리

생성 요청은 회사·해석된 기간·CLOSED 마감 버전·재무제표 스냅샷·시산표와 매핑 digest를 관계형 Run에 고정합니다. CF Run은 현재 유효한 현금흐름표 스냅샷 digest를 원천으로 고정하고, 파일은 그 스냅샷의 관계형 항목만 읽습니다. 신규 요청 시 정책·원천 변경으로 기존 CF 스냅샷이 오래됐으면 거부하며, 이미 완료된 Run의 파일은 유지합니다. 완료된 파일의 이름·SHA-256·크기는 관계형 Artifact에 기록하고 파일은 기존 회사별 Storage에 저장합니다. Financial Metrics도 기존 BS/IS 스냅샷 계산을 재사용합니다. 동일 `Idempotency-Key` 재요청은 중복 Run을 만들지 않습니다. 실패 재시도는 새 Run을 만들고 기존 완료 파일을 덮어쓰지 않습니다. 원천이 변경되면 `REPORT_SOURCE_STALE`, 저장소 오류는 `STORAGE_UNAVAILABLE`, 파일 생성 오류는 `EXPORT_GENERATION_FAILED`로 기록합니다. 보고서 생성은 전표·GL·재무제표 스냅샷을 수정하지 않습니다.

SCE Run은 현재 대사 상태를 다시 검사하고 SCE Snapshot digest를 고정합니다. 구성요소별 기초·변동·기말 금액은 관계형 Snapshot의 값을 그대로 렌더링합니다. 완료 파일에는 회사·기간·버전·`INTERNAL_VALIDATION_ONLY`를 표시하며 기존 Artifact 이력·권한·SHA-256 다운로드 검증을 재사용합니다. 이후 원천이 바뀌어도 기존 완료 파일과 과거 스냅샷은 유지됩니다.

API는 `GET /reports/catalog`, `POST /reports/generations`, `GET /reports/generations`, `GET /reports/generations/{run_id}`와 완료 Run의 `/artifact`·`/download`를 제공합니다. 생성과 재시도 요청에는 `X-Company-ID`, CSRF, `Idempotency-Key`가 적용됩니다. 지원 형식은 PDF, XLSX, UTF-8 CSV입니다.

V1은 작은 보고서를 요청 중 동기 생성합니다. CF·SCE 파일에는 `INTERNAL_VALIDATION_ONLY`를 표시합니다. `RECONCILED`는 법정 승인·감사·공시 완료를 뜻하지 않습니다. 구조화된 Notes, DOCX, LLM 설명문, 예약·이메일, Cloud Storage는 지원하지 않습니다.

현금흐름표의 회사별 정책·비현금 공시·처분손익 원천을 포함한 새 생성 요청은 현재 스냅샷의 유효성을 확인합니다. 비현금 공시는 PDF/XLSX/CSV에서 현금흐름 합계와 분리해 표시합니다. 기존에 완료된 Run과 Artifact는 생성 당시 스냅샷을 계속 가리킵니다. 세부 검증 범위는 [현금흐름표 회계 계약](cash-flow-policy-remaining-work.md)에 기록합니다.
