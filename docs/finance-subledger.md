# 채권·채무 정산과 원장 대사

## 기준과 사용 순서

시작 main은 `52f173decd38189dda05f042af291487421309f9`입니다. 단일 기준선은 Google Drive의 **AI_Accounting_Office_v0.2.5_통합설계_정본**이며 fallback과 Archive 문서를 사용하지 않았습니다.

직접 읽은 활성 문서는 읽기안내_문서지도_용어집, 제품_개발로드맵_구현순서_릴리즈게이트, 재무운영_AR_AP_은행카드_자금, Physical_ERD_PostgreSQL_DDL_SQL, Complete_DDL_Migration_Map, API_Pydantic_Contract, Error_Idempotency_Concurrency_Contract, Repository_Module_Architecture, Permission_Matrix_RBAC, Relational_First_No_JSON_DB_Policy, Implementation_DoD_Review_Checklist, 전산회계운용사_1급_2급_3급_Coverage_Matrix, Golden_Dataset_Fixture, 샘플회사_페르소나_데이터셋_가이드입니다.

1. 회계 담당자가 거래처를 지정한 매출채권 또는 매입채무·미지급금 분개를 작성·제출합니다.
2. 다른 승인 권한 사용자가 승인하고 장부에 반영합니다. 본인 승인을 허용하지 않습니다.
3. 회계 담당자로 로그인하여 **채권** 또는 **채무**에서 **채권 등록 / 채무 등록**을 선택하고 확정 전표와 만기일을 지정합니다.
4. 수금·지급도 별도 전표의 사람 승인과 장부 반영을 먼저 마칩니다. 입출금일은 해당 전표일과 같아야 합니다.
5. 채권·채무 화면에서 수금·지급 내역을 등록하고 대상을 배분한 뒤 명시적으로 확정합니다.
6. 기준일의 잔액·연체·만기 예정액과 원장 대사를 확인합니다. 원장 불일치를 자동 보정하지 않습니다.

로컬 계정 준비는 기존 `python scripts/bootstrap_local.py`를 사용합니다. 비밀번호는 Git에서 제외된 `.local/development-accounts.ini`에 있습니다. 회계 담당자 계정으로 채권·채무를 테스트하세요. 회사 관리자인 OWNER는 Permission Matrix에 따라 재무 조회·수금·지급 기록 권한을 자동으로 얻지 않습니다. 관리자 권한 우회 계정은 없습니다.

## 관계형 저장과 책임

`009_finance_subledger`는 `008_governance` 뒤에 추가됩니다. 기존 migration은 수정하지 않습니다.

| 테이블 | 책임 |
| --- | --- |
| receivables / payables | 회사·거래처·확정 원천 전표 및 분개 번호, 원금·만기·버전 |
| collections / payments | 수금·지급일, 확정 회계 전표, 총액, 방법, 상태 |
| collection_allocations / payment_allocations | 헤더와 채권·채무의 다대다 배분 |
| finance_command_receipts | 회사·사용자·명령·키·지문과 결과 resource/버전 참조 |
| reconciliation_matches / reconciliation_match_lines | 최신 DDL의 후속 은행·카드 source matching 호환 구조 |

마지막 두 matching 테이블은 이번 AR/AP↔GL 조회 결과를 저장하는 테이블이 아닙니다. 해당 기능 API·작성 서비스는 만들지 않았습니다. 미구현 은행 테이블을 향한 가짜 FK도 추가하지 않았습니다.

모든 신규 업무 테이블은 UUID, 필수 company_id, 명시적 FK·인덱스·제약을 사용합니다. 금액은 NUMERIC(19,4)/Decimal입니다. 헤더·배분·대상 간 회사 복합 FK로 타 회사 연결을 DB에서도 제한합니다. 업무 JSON/JSONB, 원본 행 blob, 전체 응답 저장은 없습니다.

`receivables`의 공통 Domain과 `ObligationService`는 채무에도 사용합니다. `settlements`는 수금·지급의 공통 배분 규칙을 소유하고 `reconciliation`은 Aging/원장 대사를 소유합니다. 동일 규칙을 AR/AP별로 복제하지 않습니다. API → Application → Domain 방향을 유지하고 Infrastructure가 Repository/UoW 계약을 구현합니다.

Application/UoW만 트랜잭션을 소유합니다. Finance Repository의 commit, Journal 직접 INSERT/UPDATE, 잔액 직접 수정 API는 없습니다. Accounting Application의 확정 전표 읽기 계약과 기존 LedgerReader를 사용합니다.

## 잔액·상태·기준일

잔액은 원금에서 **확정된 배분**을 뺀 값입니다. 저장된 outstanding은 서비스가 관리하는 현재 상태 캐시이고, 기준일 조회는 해당 일자까지의 확정 배분으로 다시 계산합니다. 사용자가 캐시를 수정할 수 없습니다. 이번 범위에 adjustment/writeoff 실행 명령은 없습니다.

배분 없음은 OPEN, 일부 배분은 PARTIAL, 전액 배분은 SETTLED입니다. 연체는 저장 상태가 아니라 `outstanding > 0 AND due_date < as_of`로 계산합니다. 잔액 0인 항목은 Aging에서 제외합니다. CURRENT, 1–30, 31–60, 61–90, 90+ 구간과 거래처별 잔액, 연체액, 기준일부터 7/30일 이내 만기액을 반환합니다.

한 헤더에 여러 대상(1:N), 한 대상에 여러 헤더(N:1)를 지원합니다. 합계는 헤더 총액과 각 대상 잔액을 초과할 수 없습니다. 미배분액은 UNAPPLIED로 남습니다. 확정 후 미배분액의 추가 배분·취소·조정 워크플로는 후속 범위입니다. 확정 헤더와 배분은 DB trigger에서도 수정·삭제를 거부합니다.

현재 기능통화는 KRW입니다. 원장 통제계정은 서버의 고정 계정과목 이름 매출채권, 매입채무, 미지급금으로 식별합니다. 사용자 지정 통제계정 매핑과 외화는 후속 확장이 필요합니다.

## 정산 확정과 동시성

헤더가 참조하는 전표는 이미 사람이 승인한 POSTED 전표여야 합니다. 배분 합계는 그 전표의 통제계정·거래처별 분개와 같아야 하며 현금·예금 반대 분개도 확인합니다. 미배분 금액은 선수금·선급금 등 별도 회계 사실로 전표에 남습니다. Finance는 새로운 장부 반영을 자동 실행하지 않습니다.

명령별 `Idempotency-Key`와 길이 접두사 SHA-256 지문으로 요청을 비교합니다. 동일 지문은 typed receipt의 resource를 재조회하며, 다른 지문은 IDEMPOTENCY_CONFLICT입니다. 확정 결과는 불변이므로 확정 재시도 응답도 같습니다. 생성·배분 재시도는 같은 resource의 현재 projection을 반환합니다. 전체 응답 JSON을 저장하지 않습니다.

원천 인식은 회사·원천 전표·분개 번호 unique와 원천 전표 lock으로 중복을 막습니다. 동일 원천에 다른 만기를 지정하면 충돌합니다. 정산 명령은 회사·사용자·명령·키 advisory transaction lock, 헤더 row lock, 정렬된 대상 row lock, expected_version을 함께 사용합니다. 다른 사용자가 같은 대상에 동시 배분해도 lost update나 초과 확정을 허용하지 않습니다.

다른 회사 resource는 query 단계부터 company_id로 제한하여 RESOURCE_NOT_FOUND로 처리합니다. 회사 membership·권한을 매 요청 검증하고, 회원 자격 폐기 후 접근도 차단합니다. 화면 숨김은 보안의 대체 수단이 아닙니다.

## 원장 대사와 출처

기준일까지의 보조부 잔액과 POSTED 분개의 통제계정 잔액을 비교합니다. AR은 차변−대변, AP는 대변−차변입니다. 결과는 MATCHED/MISMATCH와 차이, 계정, 원천 전표·증빙 참조를 제공합니다. Closing은 향후 MISMATCH를 차단 사유로 소비할 수 있습니다.

채권·채무 → 원천 Journal/Line → canonical Transaction → Import/Evidence의 관계형 출처를 조회합니다. 수금·지급은 별도 확정 Journal을 참조하고 기존 Governance Audit에 안전한 resource 참조를 기록합니다. 원천 전표를 역분개한 경우 자동으로 채권·채무를 취소하지 않으며 대사 차이가 드러납니다. 역분개 연계 정산 취소 정책은 후속 작업입니다.

## API

아래 경로는 기존 prefix 없는 API 규칙을 따릅니다. 회사는 X-Company-ID, 인증은 기존 Principal을 사용합니다. 중요 command는 extra 필드를 거부합니다. 금액은 정확한 십진수 문자열로 보내세요.

| 기능 | 경로 |
| --- | --- |
| 목록/상세 | GET /receivables, /receivables/{id}; /payables 대칭 |
| 확정 원천 연결 | POST /receivables/from-journals; /payables/from-journals |
| 기준일 Aging/대사 | GET /receivables/aging, /receivables/reconciliation; /payables 대칭 |
| 수금·지급 등록/조회 | POST/GET /collections, /payments; GET /{id} |
| 초안 배분 교체 | POST /collections/{id}/allocations; /payments 대칭 |
| 명시적 확정 | POST /collections/{id}/confirm; /payments 대칭 |

조회에는 as_of를 명시합니다. 생성·배분·확정은 Idempotency-Key가 필요합니다. 배분 요청은 헤더 expected_version과 대상별 expected_version을 포함합니다. SETTLEMENT_TARGET_STALE은 409, SETTLEMENT_ALLOCATION_EXCEEDED는 422입니다. SQL/parameter 원문은 응답하거나 로그에 출력하지 않습니다.

## 참고 코드 판단

실제로 읽은 저장소는 `nobadai/mainproject`, commit `516449c08feb3d065d36d6c556eb59d14625d5d8`입니다. COPY/직접 ADAPT는 없으며 아래 의미만 PATTERN으로 참고했습니다.

| 원본 파일·함수 | 신규 파일·판단 |
| --- | --- |
| backend/app/finance/receivables.py — build_receivable_write_plan, confirm_receivable | receivables/application/service.py — 확정 원천 검증·중복 방지·caller transaction |
| backend/app/finance/collection.py — build_collection_transition, apply_explicit_collection | settlements/domain/rules.py, application/service.py — 부분수금과 Decimal 잔액 |
| backend/app/finance/settlement.py — settle_recognized_payables | settlements/application/service.py — lock 후 검증·초과 지급 차단 |
| backend/app/finance/expenses.py — settle_expense, cancel_expense | 정책 PATTERN만 참고, Expense 코드 도입 없음 |
| backend/app/finance/rules.py — evaluate_sales_amount_integrity | settlements/domain/rules.py — 계산과 판정 분리·stable error |

원본의 simulation 식별자, finance state, 직접 psycopg SQL, 현금 state 차감, fixture 전용 identity와 전용 정책은 DROP했습니다. 신규 구현은 SQLAlchemy/UoW/company/Journal 계약으로 작성했습니다. WITH ESG·ServIQ·CommitLens를 이번 범위에 새로 이식하지 않았습니다.

## 공식 데이터와 알려진 제한

단건 GOLDEN_CORP_001은 AR 5,500,000, AP 1,650,000과 각 GL 일치, 기존 TB 차변/대변 62,650,000, 현금 50,550,000을 검증합니다. Card/Treasury 기능을 구현했다는 의미는 아닙니다.

연간 SYN_MFG_001의 공식 정본은 native Google Sheet **AI_Accounting_Office_SAMPLE_COMPANY_2025** (`1C_URD6dlROitLTmN6ZTAhBdebF0Dc3_bl3dzaIiXvA8`)입니다. 같은 폴더의 `_v1.xlsm`은 legacy/raw artifact이며 공식 Onboarding fixture가 아닙니다. 기존 macro 없는 XLSX regression fixture는 수정하지 않았습니다. 이번 Finance 테스트는 native Sheet의 관련 9개 탭을 읽어 만든 versioned CSV snapshot을 테스트 전용 adapter로 소비합니다. 매출 상세 486행·매입 상세 148행의 합계를 청구서 공급가액과 별도로 대조합니다. 운영용 연간 workbook importer를 추가하지 않았습니다.

실제 정본에는 COLL_MULTI_001의 SINV0179/SINV0180과 PAY_MULTI_001의 PINV0060이 발생일보다 앞선 정산일을 가집니다. 두 batch 전체를 명시적으로 거부하고 회귀 테스트에서 그 오류를 단언합니다. 원본 날짜를 고치거나 일부 행만 조용히 반영하지 않습니다. 나머지 유효 배분과 모든 매출 240건·매입 74건의 기준일 잔액을 대사합니다. 정본 수정은 별도 fixture version과 변경 근거가 필요합니다. 세무 sheet는 기대 신고 정답으로 사용하지 않습니다.

현재 목록은 pagination 없이 반환합니다. 실제 은행 이체·은행/카드 workflow·Expense·Treasury·writeoff·정산 취소·후속 미배분 적용·자산·재고·세무·Agent/LLM은 제외합니다.

검증 명령과 실측 결과는 [재무 보조부 검증 기록](finance-verification.md), 용어는 [약어 풀이](abbreviations.md)를 참고하세요.
