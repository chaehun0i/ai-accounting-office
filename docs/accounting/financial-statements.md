# CLOSED 기간 BS/IS

재무제표 메뉴는 CLOSED 회계기간의 최신 완료된 Closing Run과 조정 시산표를 읽어 재무상태표(BS)와 손익계산서(IS)를 생성합니다. 생성 결과는 `GENERATED` 상태의 관계형 스냅샷이며 승인된 공식 보고서가 아닙니다. Journal과 GL은 변경하지 않습니다.

`KR_INTERNAL` taxonomy v1의 계정 매핑은 기본 KR 계정 템플릿 ID와 안정된 계정 코드로 명시적으로 등록합니다. 회사가 추가한 계정은 재무제표 화면에서 계정 유형에 맞는 표시 항목에 먼저 연결해야 합니다. POSTED 장부에서 사용된 계정에 매핑이 없거나 중복되면 생성을 차단합니다. 이 버전에서는 최초 매핑만 등록할 수 있으며 기존 매핑 재분류와 taxonomy 개정은 후속 범위입니다.

BS는 마감일 누적 잔액을, IS는 선택 기간의 수익·비용 movement를 사용합니다. 월별 soft close는 손익 계정을 물리적으로 자본으로 대체하지 않으므로 BS에는 누적 손익을 `미대체 누적손익`으로 명시해 자산 = 부채 + 자본을 검증합니다. 이는 새 분개가 아닙니다. 비용과 차감계정의 부호는 Decimal 차대 잔액과 taxonomy의 normal sign으로 계산하며 임의 `abs()` 보정은 하지 않습니다.

`POST /financial-statements/generate`에는 회사 헤더와 Idempotency-Key가 필요합니다. 동일 마감 버전·시산표 digest·taxonomy·매핑 digest의 재요청은 기존 세트를 반환합니다. 마감 장부가 바뀌면 생성은 실패합니다. 세트, BS/IS, 항목별 계정·전표 라인 출처는 각각 조회 API로 확인할 수 있습니다. 다른 회사의 세트는 조회되지 않습니다.

`/financial-statements`는 BS/IS 스냅샷 생성·조회·출처 확인과 현금흐름표 점검·조회 화면입니다. 파일 생성은 스냅샷을 읽는 [Report Center V1](report-periods.md#report-center-v1-사용자-경로)의 `/reports` 화면에서 제공합니다. Report Center의 PDF/XLSX/CSV 파일은 스냅샷을 표현하는 파생 산출물이며 승인된 공식 재무제표가 아닙니다. 승인, 비교재무제표와 주석은 후속 범위입니다.

## 자본변동표 원천·대사 API

`/equity/components`와 `/equity/mappings`는 회사별 자본 구성요소와 실제 전기 가능 자본 계정의 명시적 연결을 관리합니다. `POST /equity/events`는 승인 후 POSTED 상태인 전표의 자본 라인만 분류하며 장부 금액을 변경하지 않습니다. 증자·감자, 배당, 자기주식 취득·처분, 손익대체, OCI 대체와 기타 조정을 구분합니다. 중복 원천 라인과 중복·누락 계정 매핑은 차단합니다.

`/equity/dividends`는 결의일·예정 지급일·회계 원천을 기록하고, `/equity/dividends/{id}/payments`는 실제 POSTED 지급 전표와 대사 완료된 CF 재무활동 현금유출 이벤트를 별도로 연결합니다. 배당결의 자체는 현금유출이 아닙니다. 여기서 `APPROVED`는 연결 전표의 회계 승인 원천이 확인됐다는 뜻이며, 법정 결의나 재무제표 최종 승인을 뜻하지 않습니다.

`GET /equity/reconciliation?period_id=…`는 CLOSED 마감 장부, 현재 BS/IS Snapshot, 전기 BS 기말자본, 계정 매핑과 분류 이벤트를 검사합니다. 기초자본은 검증된 Opening 전표 또는 전기 CLOSED BS에서만 확정합니다. 이익잉여금에는 전기 미대체 손익을 기초로, 당기순이익은 현재 IS Snapshot의 결정적 금액으로 한 번만 연결합니다. 구성요소별 기초 + 소유주거래 + 당기손익 + OCI + 기타조정 = 기말을 계산하고 BS 자본총계와 일치하지 않으면 `BLOCKED`입니다. 연결된 배당 지급은 CF의 현재 Snapshot·원천 이벤트와 다시 대사합니다.

전기말 BS의 마감 원천이 stale이면 당기초 자본을 확정하지 않습니다. 실제 손익 대체 전표는 미대체 전기손익을 다시 자본변동으로 더하지 않고 원천만 보존합니다. 현재 BS/IS 생성 계약에서 대체 전표가 당월 IS 순이익에 섞인 경우에는 `PROFIT_TRANSFER_IS_MISMATCH`로 SCE 생성을 차단합니다. 표시용 IS 순이익을 임의로 재계산하지 않습니다. 배당 지급 연결은 결의 행 잠금과 CF 이벤트 고유 제약으로 동시 초과 지급·중복 연결을 막고, 지급 누계가 결의액을 넘으면 거부합니다.

`POST /equity/statements/generate`는 `READY`일 때만 관계형 SCE Snapshot을 추가합니다. 동일 원천·버전의 재요청은 기존 결과를 반환하고, 같은 Idempotency-Key의 다른 원천 요청은 거부합니다. 헤더·행·출처는 PostgreSQL 트리거로 UPDATE/DELETE 및 생성 트랜잭션 이후 행 추가가 차단됩니다. `/equity/statements`, `/equity/statements/{id}`, `/equity/statements/{id}/lines/{line_id}/sources`에서 회사 범위로 조회합니다. 원천에는 POSTED 전표·계정·증빙 ID 또는 IS Snapshot ID가 남습니다. `/financial-statements`는 구성요소를 열, 변동유형을 행으로 표시하고 차단 사유·원천을 조회합니다. 현재 SCE 상태는 내부 대사 완료를 뜻하며 법정 승인·감사 완료를 뜻하지 않습니다. Report Center는 대사된 SCE Snapshot digest를 고정한 PDF/XLSX/CSV와 이력·다운로드를 제공합니다.

## 현금흐름표 Phase 2 선행 점검

`/cash-flow` API는 현금흐름표 생성 전 필요한 **현금 범위와 활동 분류의 명시적 설정** 및 CLOSED 기간 사전 점검을 제공합니다. `POST /cash-flow/cash-scope`는 회사 소유의 활성·전기 가능한 자산 계정을 `CASH` 또는 `CASH_EQUIVALENT`로 등록합니다. `POST /cash-flow/classifications`는 현금 상대 계정에 `OPERATING`, `INVESTING`, `FINANCING`, `EXCHANGE_EFFECT` 활동과 line code를 등록합니다. 조회는 각각 `GET /cash-flow/cash-scope`, `GET /cash-flow/classifications`입니다. 등록은 `financial_statement.generate`, 조회와 사전 점검은 `financial_statement.read` 권한 및 회사 범위를 확인합니다. 같은 등록의 재요청은 기존 매핑을 반환하고 서로 다른 내용으로의 변경은 현재 409로 거부합니다.

`GET /cash-flow/preflight?period_id=…`는 기존 CLOSED 마감의 조정 장부와 source digest를 읽어 기초·기말 현금, 기간 순증감, 활동별 명시적 분류 금액과 차이를 Decimal로 검사합니다. 현금 범위가 없거나 기간 전체에 유효하지 않으면 차단합니다. Opening 전표는 해당 기간의 영업·투자·재무 현금흐름으로 세지 않고 기초현금에 포함합니다. 현금 계정 간 순증감 0인 내부 이체도 제외합니다. 상대 계정 분류가 없거나 복합분개를 신뢰할 수 있게 배분할 수 없으면 `CASH_FLOW_UNCLASSIFIED` 또는 `CASH_FLOW_COMPLEX_JOURNAL`을 반환하며 잔차를 임의 활동으로 채우지 않습니다. 분류 총액과 기초·기말 현금 차이가 맞지 않으면 `CASH_FLOW_RECONCILIATION_MISMATCH`를 반환합니다.

복합분개는 연결된 증빙을 지정해 `POST /cash-flow/allocations`로 현금 라인과 상대 라인의 금액을 명시적으로 배분할 수 있습니다. 현금 라인은 전액 배분하고 상대 라인은 원래 금액을 넘기지 않아야 합니다. 미배분이나 초과 배분은 차단하며 잔차를 자동 활동으로 분류하지 않습니다. 잘못된 배분은 `PUT /cash-flow/allocations/{allocation_id}`로 새 관계형 이력을 추가해 바로잡습니다. 금액 `0`은 해당 쌍의 철회이며, 철회 후 복구도 최신 이력에 대한 수정으로 수행합니다. `GET /cash-flow/allocations?journal_id=…`는 수정 이력을 읽습니다. 동일 요청 재시도는 같은 배분 또는 직접 후속 수정 이력을 반환하고 오래된 수정 요청은 거부합니다.

`GET /cash-flow/events?period_id=…`는 사전 점검을 통과한 CLOSED 장부에서 직접법 현금 이벤트를 결정적으로 **읽기 투영**합니다. 전표·라인·상대 계정·활동·line code·연결 증빙까지 추적할 수 있습니다. 이것은 저장된 현금흐름표 스냅샷이 아니며 GL을 다시 기표하지 않습니다. 현금 계정만 움직이는 이체는 제외합니다. 현금 계정 간 이체와 외부 거래가 하나의 복합분개에 섞인 경우에는 아직 자동 분할하지 않고 차단합니다.

`POST /cash-flow/adjustment-rules`는 회사 계정에 간접법 역할을 명시적으로 등록합니다. 현재 지원하는 `ACCOUNT_LEDGER` 규칙은 손익 계정, 운전자본 자산·부채, 두 계정으로 근거가 닫히는 비현금 비용, 조정 제외 잔액과 검증된 처분손익입니다. 같은 규칙의 재요청은 기존 행을 반환하고 다른 내용으로의 변경은 거부합니다. 유효기간 전체, 계정 유형, 회사 범위와 기본 `TAX_INTEREST_OPERATING` 규칙 버전을 검사합니다. 회사별 이자·세금 활동 정책은 별도 관계형 이력으로 적용합니다. Asset Register·Inventory Subledger가 필요한 복잡한 원천은 추정하지 않고 차단합니다.

`GET /cash-flow/indirect-bridge?period_id=…`는 동일 CLOSED 장부 및 최신 BS/IS 스냅샷을 확인한 뒤 IS 당기순이익, 계정별 기초·기말 잔액과 POSTED 전표 라인 출처, 비현금 가산 및 운전자본 변동을 Decimal로 계산합니다. 직접법 영업활동 순액과 간접법 순액이 정확히 같아야 `READY`입니다. 미분류 계정, 지원되지 않는 복합 원천, 변조되거나 오래된 BS/IS, 정책·유효일 오류, 직접·간접 차이는 코드와 근거를 포함한 `BLOCKED`로 표시하며 잔차를 임의 조정하지 않습니다. 응답의 close version, source digest, statement set·snapshot 식별자와 mapping digest는 계산에 사용한 원천을 추적합니다.

`POST /cash-flow/generate`는 같은 CLOSED 기간의 현재 BS/IS 세트, 간접법 `READY`, 직접 현금 원천과 정확한 현금 대사를 다시 확인한 뒤 `RECONCILED` 관계형 스냅샷을 생성합니다. `Idempotency-Key`로 같은 요청의 중복 생성을 막고, 회사·기간·마감 버전·원천 및 매핑 digest를 고정합니다. `GET /cash-flow/statements?period_id=…`는 현재 유효한 결과를, `GET /cash-flow/{id}`는 동결된 과거 결과를 조회합니다. 항목과 원천은 `/cash-flow/{id}/lines`, `/cash-flow/{id}/drilldown?line_id=…`에서 확인할 수 있습니다. 현금 이벤트·간접법 조정·기초/기말 현금의 전표 행·증빙·적용 버전은 회사 범위 인덱스가 있는 관계형 이력으로 저장하고, 동결 후 변경을 데이터베이스에서도 차단합니다. 현재 원천이 바뀌면 현재 결과 조회와 새 생성은 재검증을 요구하지만 과거 결과의 의미는 변하지 않습니다.

`/financial-statements`에서 CLOSED 기간과 현재 BS/IS 세트를 선택하면 현금흐름표 영역이 사전 점검, 차단 코드와 대사 차이를 보여줍니다. `financial_statement.generate` 권한자는 현재 원천이 `READY`일 때 간접법 스냅샷을 생성할 수 있습니다. 생성 결과에서는 항목별 금액과 전표·증빙·배분·조정 규칙·기초/기말 현금 원천을 조회합니다. 회사나 기간을 전환하면 이전 회사의 조회 상태를 버립니다. 오래된 원천의 결과는 현재 결과로 표시하지 않고 재점검을 안내합니다.

`RECONCILED`는 **간접법 금액과 직접 현금 원천의 대사 상태**입니다. 회사별 이자·세금 정책, 관계형 비현금 공시 Fact, 근거가 닫히는 처분손익 조정과 Report Center Export는 [현금흐름표 회계 계약](cash-flow-policy-remaining-work.md)에 기록합니다. 승인된 공식 현금흐름표는 제공하지 않습니다. 전체 완료조건은 [Issue #87](https://github.com/chaehun0i/ai-accounting-office/issues/87)에서 추적합니다.

PostgreSQL API 회귀 검증은 현금 범위·활동 분류 및 증빙 배분, CLOSED 장부 직접 이벤트, 간접법 규칙과 비현금·운전자본 조정, BS/IS 원천 변조·버전 불일치, 직접·간접 대사, 회사 간 접근 차단을 확인합니다. 이 검증은 실제 API와 서비스 구성을 통해 수행합니다.

Bookkeeper의 `financial_statement.read`는 기존 읽기 Application Service와 `financial_statement.read` 사용자 권한을 재사용합니다. `AI 회계팀` 화면은 CLOSED 기간의 기존 스냅샷 금액·버전·digest를 표시하며 재무제표를 새로 생성하거나 승인하지 않습니다.

BS/IS 각 항목의 **계정·전표 보기**는 원장 출처 조회이며, **AI에게 묻기**는 해당 기간·제표 종류·항목 코드만 `/ai-team` 질문 초안으로 전달합니다. 현금흐름표는 지원되는 합계 항목에서 **원천·전표 보기**와 **AI에게 묻기**를 제공합니다. 회사 ID와 금액은 URL에 넣지 않습니다. AI 회계팀은 현재 회사의 기간 목록을 다시 확인하고 사용자가 질문을 제출한 뒤에만 기존 `financial_statement.read` 또는 `cash_flow.read`를 호출합니다. 항목 코드는 허용 목록으로 검증하며, 답변 금액과 출처는 Reporting Application의 스냅샷이 정본입니다.

## 재무제표 주석 · Disclosure Registry

`/disclosures/templates`는 v1 `INTERNAL_CORE_NOTES` Registry와 BS/IS/CF/SCE 섹션을 제공합니다. 이 template은 내부 검증용이며 K-IFRS·일반기업회계기준 공식 공시 목록으로 검증되지 않았습니다. 법정 공시 요구사항으로 표현하지 않습니다.

`GET /disclosures/readiness?period_id=…`는 CLOSED 마감 버전의 BS/IS와 대사 완료 CF/SCE Snapshot을 확인합니다. 제표 digest, CF/SCE source digest, 현재 마감·원천 상태를 재검증하고 BS 등식, IS 순이익과 CF 순이익, SCE 기말 자본과 BS 자본을 Decimal로 교차 확인합니다. 필수 원천이 없거나 stale·차이가 있으면 `BLOCKED`와 오류 코드를 반환합니다. 필수 숫자를 0 또는 추정치로 채우지 않습니다.

`POST /disclosures/instances/generate`는 네 Snapshot 식별자와 digest, template version을 고정하고 제표 line, CF line, SCE component/movement를 관계형 Decimal Fact로 복사합니다. BS/IS Fact에는 별도로 제표 mapping에 실제 연결된 GL 계정별 합계도 생성하며, 원천 journal line을 따라가고 계정별 합계와 제표 leaf line의 차이가 있으면 생성을 차단합니다. 계정명으로 현금·채권·채무 등 공시 유형을 추정하지 않습니다. 동일 기간·source digest 재요청은 기존 revision을 재사용하며 동일 idempotency key의 다른 payload는 거부합니다. Fact와 audit는 DB trigger로 수정·삭제할 수 없습니다. Asset Register, Inventory Subledger, AR aging/대손충당, Tax computation 또는 accounting policy 원천이 필요한 세부 주석은 제공하지 않습니다.

`PUT /disclosures/instances/{id}/narratives`는 네 필수 섹션의 사용자 설명 초안을 작성합니다. `POST …/request-review`는 필수 설명과 현재 source digest를 재검증합니다. 독립 Reviewer/Owner가 `POST …/approve` 또는 `/reject`에 expected version을 보내 상태를 전이합니다. 작성자는 자신의 revision을 승인할 수 없습니다. 승인 이후 instance, Fact, narrative 및 audit는 불변이며 원천이 바뀌면 새 revision을 생성합니다. 기존 승인본은 생성 당시 원천을 보존하지만 현재 원천과 달라지면 stale 표시를 하며 Export에서 제외합니다.

각 Fact의 `/disclosures/instances/{id}/values/{value_id}/source` 응답은 제표 drill-down 경로와 POSTED Journal·Evidence 식별자를 제공합니다. `/financial-statements`의 Notes 영역은 원천 준비, 차단 사유, Fact, 설명 초안, 독립 승인과 원천 상세를 표시합니다. AI는 금액·정책·근거를 생성하지 않으며 현재 경로는 결정론적 Fact와 사용자 작성 설명을 사용합니다.

Report Center `NOTES`는 현재 원천 digest와 일치하는 독립 승인 revision에서만 PDF/XLSX/CSV Run을 생성합니다. 기존 Artifact/History/Download 및 SHA-256 검증을 재사용하고 파일에 revision·template/source digest·`INTERNAL_VALIDATION_ONLY`를 표시합니다. 승인된 Notes는 내부 검토본이며 법정 승인·감사 완료·외부 제출 적합성을 뜻하지 않습니다.

Notes의 PostgreSQL 핵심 회귀는 `test_equity_statement.py`의 CLOSED 원천 생성·Fact/전표 추적·작성자와 Reviewer 분리·승인 불변성·세 형식 Export 정상 경로, `test_disclosures.py`의 미완료 원천 차단, Report Center 회사 범위 및 migration lifecycle 테스트를 포함합니다. 로컬 PostgreSQL 없이 이 검증을 통과로 표시하지 않으며, CI PostgreSQL job에서 실제 DB로 실행합니다.
