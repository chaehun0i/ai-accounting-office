# CLOSED 기간 BS/IS

재무제표 메뉴는 CLOSED 회계기간의 최신 완료된 Closing Run과 조정 시산표를 읽어 재무상태표(BS)와 손익계산서(IS)를 생성합니다. 생성 결과는 `GENERATED` 상태의 관계형 스냅샷이며 승인된 공식 보고서가 아닙니다. Journal과 GL은 변경하지 않습니다.

`KR_INTERNAL` taxonomy v1의 계정 매핑은 기본 KR 계정 템플릿 ID와 안정된 계정 코드로 명시적으로 등록합니다. 회사가 추가한 계정은 재무제표 화면에서 계정 유형에 맞는 표시 항목에 먼저 연결해야 합니다. POSTED 장부에서 사용된 계정에 매핑이 없거나 중복되면 생성을 차단합니다. 이 버전에서는 최초 매핑만 등록할 수 있으며 기존 매핑 재분류와 taxonomy 개정은 후속 범위입니다.

BS는 마감일 누적 잔액을, IS는 선택 기간의 수익·비용 movement를 사용합니다. 월별 soft close는 손익 계정을 물리적으로 자본으로 대체하지 않으므로 BS에는 누적 손익을 `미대체 누적손익`으로 명시해 자산 = 부채 + 자본을 검증합니다. 이는 새 분개가 아닙니다. 비용과 차감계정의 부호는 Decimal 차대 잔액과 taxonomy의 normal sign으로 계산하며 임의 `abs()` 보정은 하지 않습니다.

`POST /financial-statements/generate`에는 회사 헤더와 Idempotency-Key가 필요합니다. 동일 마감 버전·시산표 digest·taxonomy·매핑 digest의 재요청은 기존 세트를 반환합니다. 마감 장부가 바뀌면 생성은 실패합니다. 세트, BS/IS, 항목별 계정·전표 라인 출처는 각각 조회 API로 확인할 수 있습니다. 다른 회사의 세트는 조회되지 않습니다.

`/financial-statements`는 BS/IS 스냅샷 생성·조회·출처 확인 화면입니다. 파일 생성은 이 스냅샷을 읽는 [Report Center V1](report-periods.md#report-center-v1-사용자-경로)의 `/reports` 화면에서 제공합니다. Report Center의 PDF/XLSX/CSV 파일은 스냅샷을 표현하는 파생 산출물이며 승인된 공식 재무제표가 아닙니다. 승인, 비교재무제표, 완성된 현금흐름표(CF)·자본변동표(SCE)·주석은 후속 범위입니다. CF의 선행 점검 범위는 아래에서 구분합니다.

## 현금흐름표 Phase 2 선행 점검

`/cash-flow` API는 현금흐름표 생성 전 필요한 **현금 범위와 활동 분류의 명시적 설정** 및 CLOSED 기간 사전 점검을 제공합니다. `POST /cash-flow/cash-scope`는 회사 소유의 활성·전기 가능한 자산 계정을 `CASH` 또는 `CASH_EQUIVALENT`로 등록합니다. `POST /cash-flow/classifications`는 현금 상대 계정에 `OPERATING`, `INVESTING`, `FINANCING`, `EXCHANGE_EFFECT` 활동과 line code를 등록합니다. 조회는 각각 `GET /cash-flow/cash-scope`, `GET /cash-flow/classifications`입니다. 등록은 `financial_statement.generate`, 조회와 사전 점검은 `financial_statement.read` 권한 및 회사 범위를 확인합니다. 같은 등록의 재요청은 기존 매핑을 반환하고 서로 다른 내용으로의 변경은 현재 409로 거부합니다.

`GET /cash-flow/preflight?period_id=…`는 기존 CLOSED 마감의 조정 장부와 source digest를 읽어 기초·기말 현금, 기간 순증감, 활동별 명시적 분류 금액과 차이를 Decimal로 검사합니다. 현금 범위가 없거나 기간 전체에 유효하지 않으면 차단합니다. Opening 전표는 해당 기간의 영업·투자·재무 현금흐름으로 세지 않고 기초현금에 포함합니다. 현금 계정 간 순증감 0인 내부 이체도 제외합니다. 상대 계정 분류가 없거나 복합분개를 신뢰할 수 있게 배분할 수 없으면 `CASH_FLOW_UNCLASSIFIED` 또는 `CASH_FLOW_COMPLEX_JOURNAL`을 반환하며 잔차를 임의 활동으로 채우지 않습니다. 분류 총액과 기초·기말 현금 차이가 맞지 않으면 `CASH_FLOW_RECONCILIATION_MISMATCH`를 반환합니다.

복합분개는 연결된 증빙을 지정해 `POST /cash-flow/allocations`로 현금 라인과 상대 라인의 금액을 명시적으로 배분할 수 있습니다. 현금 라인은 전액 배분하고 상대 라인은 원래 금액을 넘기지 않아야 합니다. 미배분이나 초과 배분은 차단하며 잔차를 자동 활동으로 분류하지 않습니다. 잘못된 배분은 `PUT /cash-flow/allocations/{allocation_id}`로 새 관계형 이력을 추가해 바로잡습니다. 금액 `0`은 해당 쌍의 철회이며, 철회 후 복구도 최신 이력에 대한 수정으로 수행합니다. `GET /cash-flow/allocations?journal_id=…`는 수정 이력을 읽습니다. 동일 요청 재시도는 같은 배분 또는 직접 후속 수정 이력을 반환하고 오래된 수정 요청은 거부합니다.

`GET /cash-flow/events?period_id=…`는 사전 점검을 통과한 CLOSED 장부에서 직접법 현금 이벤트를 결정적으로 **읽기 투영**합니다. 전표·라인·상대 계정·활동·line code·연결 증빙까지 추적할 수 있습니다. 이것은 저장된 현금흐름표 스냅샷이 아니며 GL을 다시 기표하지 않습니다. 현금 계정만 움직이는 이체는 제외합니다. 현금 계정 간 이체와 외부 거래가 하나의 복합분개에 섞인 경우에는 아직 자동 분할하지 않고 차단합니다.

`POST /cash-flow/adjustment-rules`는 회사 계정에 간접법 역할을 명시적으로 등록합니다. 현재 지원하는 `ACCOUNT_LEDGER` 규칙은 손익 계정, 운전자본 자산·부채, 두 계정으로 근거가 닫히는 비현금 비용과 조정 제외 잔액입니다. 같은 규칙의 재요청은 기존 행을 반환하고 다른 내용으로의 변경은 거부합니다. 유효기간 전체, 계정 유형, 회사 범위와 `TAX_INTEREST_OPERATING` 정책 v1을 검사합니다. Asset Register·Inventory Subledger 원천과 다른 정책 버전은 아직 사용할 수 없으며 명시적으로 차단합니다.

`GET /cash-flow/indirect-bridge?period_id=…`는 동일 CLOSED 장부 및 최신 BS/IS 스냅샷을 확인한 뒤 IS 당기순이익, 계정별 기초·기말 잔액과 POSTED 전표 라인 출처, 비현금 가산 및 운전자본 변동을 Decimal로 계산합니다. 직접법 영업활동 순액과 간접법 순액이 정확히 같아야 `READY`입니다. 미분류 계정, 지원되지 않는 복합 원천, 변조되거나 오래된 BS/IS, 정책·유효일 오류, 직접·간접 차이는 코드와 근거를 포함한 `BLOCKED`로 표시하며 잔차를 임의 조정하지 않습니다. 응답의 close version, source digest, statement set·snapshot 식별자와 mapping digest는 계산에 사용한 원천을 추적합니다.

`POST /cash-flow/generate`는 같은 CLOSED 기간의 현재 BS/IS 세트, 간접법 `READY`, 직접 현금 원천과 정확한 현금 대사를 다시 확인한 뒤 `RECONCILED` 관계형 스냅샷을 생성합니다. `Idempotency-Key`로 같은 요청의 중복 생성을 막고, 회사·기간·마감 버전·원천 및 매핑 digest를 고정합니다. `GET /cash-flow/statements?period_id=…`는 현재 유효한 결과를, `GET /cash-flow/{id}`는 동결된 과거 결과를 조회합니다. 항목과 원천은 `/cash-flow/{id}/lines`, `/cash-flow/{id}/drilldown?line_id=…`에서 확인할 수 있습니다. 현금 이벤트·간접법 조정·기초/기말 현금의 전표 행·증빙·적용 버전은 관계형 이력으로 저장하고, 동결 후 변경을 데이터베이스에서도 차단합니다. 현재 원천이 바뀌면 현재 결과 조회와 새 생성은 재검증을 요구하지만 과거 결과의 의미는 변하지 않습니다.

`RECONCILED`는 **간접법 금액과 직접 현금 원천의 대사 상태**입니다. 별도 비현금거래 공시 Fact, 투자 처분손익 재분류, 승인된 공식 현금흐름표와 Report Center Export는 아직 제공하지 않습니다. 사용자 화면은 후속 PR 범위입니다. 전체 완료조건은 [후속 Issue #87](https://github.com/chaehun0i/ai-accounting-office/issues/87)에서 추적합니다.

PostgreSQL API 회귀 검증은 현금 범위·활동 분류 및 증빙 배분, CLOSED 장부 직접 이벤트, 간접법 규칙과 비현금·운전자본 조정, BS/IS 원천 변조·버전 불일치, 직접·간접 대사, 회사 간 접근 차단을 확인합니다. 이 검증은 실제 API와 서비스 구성을 통해 수행합니다.

Bookkeeper의 `financial_statement.read`는 기존 읽기 Application Service와 `financial_statement.read` 사용자 권한을 재사용합니다. `AI 회계팀` 화면은 CLOSED 기간의 기존 스냅샷 금액·버전·digest를 표시하며 재무제표를 새로 생성하거나 승인하지 않습니다.

BS/IS 각 항목의 **계정·전표 보기**는 원장 출처 조회이며, **AI에게 묻기**는 해당 기간·제표 종류·항목 코드만 `/ai-team` 질문 초안으로 전달합니다. 회사 ID와 금액은 URL에 넣지 않습니다. AI 회계팀은 현재 회사의 기간 목록을 다시 확인하고 사용자가 질문을 제출한 뒤에만 기존 `financial_statement.read`를 호출합니다. 항목 코드는 기존 taxonomy에서 검증하며, 답변 금액과 출처는 Reporting Application의 스냅샷이 정본입니다.
