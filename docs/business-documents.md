# 매출·매입 업무문서

## 책임과 사용 흐름

업무문서는 거래·전표·채권채무와 별개의 원천입니다. `finance/invoices`가 매출 청구서, 매입 청구서, 감액 정정문서(Credit Note), 증액 정정문서(Debit Note)를 소유합니다.

회계 담당자가 초안을 작성하고 승인 요청하면, 작성자와 다른 승인 담당자가 문서를 확정합니다. 문서 확정은 같은 작업단위에서 정규 거래와 채권 또는 채무를 만듭니다. 전표 작성·사람 승인·Posting은 기존 회계 애플리케이션이 별도로 수행합니다. 자동 Posting은 없습니다.

- Invoice: `DRAFT → REVIEW_REQUIRED → APPROVED`
- 정정문서: `DRAFT → REVIEW_REQUIRED → APPLIED`
- 정산 상태는 기존 AR/AP의 확정 배분과 정정 사실에서 계산합니다. 원 Invoice의 확정 상태를 정산 때마다 UPDATE하지 않습니다.
- 확정 문서의 경제적 내용과 항목은 DB trigger로 변경·삭제를 차단합니다.

## API와 권한

`/sales-invoices`, `/purchase-invoices`는 목록·상세·생성·초안 PATCH·`submit`·`approve`를 제공합니다. `/credit-notes`, `/debit-notes`는 원 Invoice를 참조하는 생성·목록·상세·제출·승인을 제공합니다. 모든 쓰기는 CSRF와 `Idempotency-Key`가 필요합니다. PATCH/상태 명령은 `expected_version`, 정정문서 생성은 원문서의 `expected_version`을 요구합니다.

`invoice.read/create/review/approve`, `credit_note.create` 권한을 서버에서 검사합니다. 회사 관리자는 다른 사용자가 작성한 문서를 승인할 수 있으나 회계 담당자의 작성 권한을 자동으로 갖지 않습니다. 회사 범위는 인증 사용자와 ACTIVE membership 및 `X-Company-ID`로 결정합니다. 사용자가 보낸 임의 company_id는 허용하지 않습니다.

Pydantic은 extra를 거부하고 금액의 float/bool 입력을 거부합니다. 금액은 Decimal/NUMERIC(19,4), 현재 통화는 KRW입니다. 세액은 원천 문서의 사실이며 검증된 세무 신고 결과가 아닙니다.

## 원자성·출처·중복 방지

`DocumentService → TransactionService.from_approved_document_in → ObligationService.recognize_invoice_in/adjust_invoice_in`이 하나의 UoW를 공유합니다. Repository는 commit하지 않습니다. 승인 중 실패하면 문서·거래·채권채무·감사 이벤트가 전부 rollback됩니다.

문서는 회사·종류별 문서번호와 회사·원천 시스템·원천 식별자가 UNIQUE입니다. 정규 거래는 `BUSINESS_DOCUMENT / 종류:문서UUID`를 source identity로 사용하고 원천 파일/Import/Evidence 참조를 보존합니다. 외부 원천 식별자는 문서에 그대로 남습니다. FK는 회사와 자원 ID의 복합키로 다른 회사 연결을 차단합니다.

`business_document_events`는 actor/command/key/fingerprint와 문서 FK·전후 상태·결과 version을 관계형으로 저장합니다. 동일 요청은 기존 결과를 조회하며 다른 fingerprint는 충돌입니다. 전체 요청·응답 JSON을 저장하지 않습니다. PostgreSQL advisory lock, 원문서·거래처·채권채무 row lock, UNIQUE가 경쟁을 방어합니다. 감사와 정정 fact는 append-only입니다.

## 정정과 정산

`obligation_adjustments`는 원 채권/채무와 정정문서를 FK로 연결합니다.

`잔액 = 원금 + 확정 증액 - 확정 감액 - 확정 수금/지급 배분`

11,000,000원 매출에서 5,500,000원 수금 후 2,200,000원 감액하면 잔액은 3,300,000원입니다. 원 Invoice 금액이나 기존 수금 배분은 변경하지 않습니다. 이후 2,200,000원 증액하면 잔액은 5,500,000원입니다. 감액은 현재 미정산 잔액을 초과할 수 없고, 완전 정산 문서의 환불은 별도 Domain이 필요하므로 차단합니다.

Invoice는 전표 Posting 전에도 업무 채권채무를 인식합니다. 이때 GL 대사는 불일치할 수 있으며 자동 보정하지 않습니다. 해당 Transaction을 참조한 POSTED Journal을 기존 인식 명령에 연결하면 같은 채권채무에 전표 참조를 붙이고 중복 생성하지 않습니다. 기본 통제계정은 활성 전기가능 `외상매출금`/`외상매입금`이 유일해야 합니다. 사용자 지정 통제계정 역할 매핑은 후속 범위입니다.

## 관계형 스키마

순방향 revision `013_business_documents`는 배포된 012 이하를 변경하지 않습니다.

신규: `sales_invoices`, `sales_invoice_lines`, `purchase_invoices`, `purchase_invoice_lines`, `document_notes`, `document_note_lines`, `business_document_events`, `obligation_adjustments`.

기존 receivables/payables에는 원 Invoice·Transaction FK와 인식일을 추가하고 전표가 없는 Invoice 원천을 명시적으로 허용합니다. Journal 원천 경로는 유지합니다. 문서 항목 합계, 승인자 분리, 원천 UNIQUE, 회사 복합 FK, 수량/단가 쌍, 날짜·상태·version을 검증합니다. 업무 JSON/JSONB 컬럼은 추가하지 않습니다. 기존 LangGraph framework schema는 변경하지 않습니다.

빈 DB downgrade/re-upgrade는 허용하지만 업무문서 이력이 존재하면 손실 방지를 위해 downgrade를 거부합니다. 데이터가 있는 환경은 백업 복구 또는 후속 순방향 migration을 사용합니다.

## 설계와 재사용 판정

SSOT는 `AI_Accounting_Office_v0.2.6_통합설계_정본`이며 fallback은 없습니다. 문서지도·로드맵·전체업무흐름·재무운영·Physical ERD·Migration Map·API·State Transition·Error/Concurrency·RBAC·Repository·Relational-First·Coverage·DoD·Golden·샘플 가이드를 직접 대조했습니다.

설계의 invoice_no 의미는 공통 API/모델의 `document_no`로 통일했습니다. 설계 migration 의미상 과거 006 영역이나 기존 history를 변경하지 않고 새 013에 추가했습니다. 정정문서 승인은 별도 중간 승인 저장 없이 같은 트랜잭션에서 APPLIED까지 진행합니다. 정산 상태는 업무문서의 경제적 상태와 분리한 AR/AP 조회입니다.

| 실제 참고 파일/패턴 | 판정 | 적용 | 제외 |
| --- | --- | --- | --- |
| 현재 Transaction Application | ADAPT | 같은 UoW의 명시적 문서 승인 명령 | ORM 직접 side effect |
| 현재 AR/AP·Settlement | ADAPT | Invoice 원천, 정정 fact와 기존 배분 합산 | 중복 보조부/잔액 overwrite |
| 현재 Evidence/Company/RBAC | ADAPT | 회사 범위 reference와 권한 | 임의 회사 입력 |
| 현재 UoW/Idempotency | PATTERN/ADAPT | 요청 잠금, 관계형 이벤트 replay | response blob |
| `nobadai/mainproject/backend/app/finance/schemas.py` | PATTERN | Decimal·명시적 상태·기한 contract | simulation identity |
| `nobadai/mainproject/backend/app/finance/db.py` | DROP/PATTERN | as-of와 원천/projection 구분 | raw psycopg·snapshot |
| `nobadai/mainproject/database/10_domain_schema.sql` | DROP/PATTERN | 원천과 채권채무 관계 개념 | pg_dump·JSON·기존 Domain |

외부 참고 commit은 `516449c08feb3d065d36d6c556eb59d14625d5d8`입니다. COPY는 없습니다. 다른 legacy 저장소를 이식하지 않았습니다.

## Fixture 정책

공식 source는 native Google Sheet 세 개입니다: SYN_SERVICE_001, SYN_RETAIL_001, SAMPLE_COMPANY_2025(SYN_MFG_001). 같은 폴더의 `_v1.xlsm`은 macro-enabled legacy artifact이며 공식 fixture가 아닙니다. Drive 원본을 수정·삭제하지 않았습니다. 문서상 세 native Sheet 외 legacy 파일이 남아 있는 정리 항목을 기록합니다.

서비스 v1 adapter는 native Sheet의 매출 2건(8,800,000원), 매입 1건(1,100,000원)을 CSV로 정규화합니다. 제조 v1 adapter는 기존 불변 native-2025-v1 snapshot의 매출 240건(781,044,000원), 매입 74건(195,277,500원)을 사용합니다. 천 단위 구분자만 제거합니다. 원본 상세의 반올림 단가는 수량×단가와 정확히 일치하지 않으므로 헤더 공급가·세액을 한 개의 명시적 집계 항목으로 운반하고 수량/단가를 꾸미지 않습니다. 원본과 기존 Golden expected는 변경하지 않습니다.

## 약어와 제외 범위

COA: 계정과목 체계. AR: 매출채권 보조부. AP: 매입채무 보조부. GL: 총계정원장. TB: 합계잔액시산표. UoW: 하나의 원자적 작업단위. CSRF: 인증 쿠키를 악용한 외부 요청 방어. FK: 외래키. SSOT: 단일 정본 기준. E2E: 실제 사용자 흐름 검증.

외화, 환불/반대채권, 전자세금계산서 발행, Tax Rule Engine, Bank/Card 대사, Closing, 재무제표, Asset/Inventory, 새 Agent Tool과 자동 Posting은 제외합니다. 다음 후보는 Bank/Card Reconciliation입니다.
