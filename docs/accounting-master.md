# 회계 마스터와 회사별 회계정책

시작 main: `3200d58212af939cfc880de7bcb0288dd5cfe042`. 작업 브랜치: `feat/accounting-master`.
단일 기준선은 [AI_Accounting_Office_v0.2.3_통합설계_구현보강](https://drive.google.com/drive/folders/17FO3EYPA64MItPL-_RQbgg1NhKr4I5mn)이며 이전 버전 fallback을 사용하지 않았습니다.

## 직접 확인한 설계

51 Bootstrap, 55 Master Data Counterparty, 58 Accounting Policy, 59 Complete DDL Migration Map, 41 Physical ERD, 42 Relational First, 44 Permission Matrix, 45 API/Pydantic, 46 Error/Concurrency, 48 Module Architecture, 49 File Migration Map, 52 DoD를 직접 읽었습니다. Golden는 50, 다음 범위 판단은 57 Import Physical Schema도 확인했습니다.

- [55 거래처 설계](https://docs.google.com/document/d/1RvOa_GFKFKgfFpMxROx1IDrIKk4IE2KX77ggkWhyYH4/edit)
- [58 회계정책](https://docs.google.com/document/d/1Tqdt4JxI-DKeVrFLYLqXQgyvVXMK2MQWYGadk1i6IsM/edit)
- [59 마이그레이션 지도](https://docs.google.com/document/d/1A_JnJ_-arKHFakEsQAo-El0RpwxVKW1R_jjnqx2O518/edit)
- [51 Bootstrap 보강](https://docs.google.com/document/d/1z73FQSN4SZ3mNRm42-8k3umUfJFXfVjedH75bpTad1s/edit)
- [57 Import 물리 스키마](https://docs.google.com/document/d/1-duTZmxV8_-LfZB1NYLhbQWbgkaiofmVXhQZlgODrUg/edit)

## 구조와 트랜잭션

`master_data/payment_terms`, `master_data/counterparties`와 `accounting/settings`, `templates`, `accounts`, `periods`, `sequences`가 각자의 Domain 값과 infrastructure를 소유합니다. `accounting/application/contracts.py`의 ORM 없는 Protocol과 `MasterSQLAlchemyUnitOfWork`가 한 작업의 저장소를 조립합니다. API는 Application Service만 호출합니다.

회사별 Repository의 단건 조회는 `get(*, company_id: UUID, resource_id: UUID)`입니다. 조회·수정 SQL에서 회사 범위를 사용합니다. child는 먼저 해당 회사의 부모를 검증합니다. 템플릿은 명시적인 공통 Control Plane 예외입니다. Repository는 flush만 수행하고 commit/rollback하지 않습니다. 초기화·거래처와 child 생성·역할 변경은 성공 시 UoW commit, 오류 시 전체 rollback입니다.

## 관계형 스키마

리비전 연결은 `db_foundation → 001_identity → 002_tenant_company_rbac → 003_master_accounting_settings`입니다. 신규 업무 테이블 12개, 전체 업무 테이블 22개입니다.

| 테이블 | 핵심 제약 |
| --- | --- |
| payment_terms | 회사+term_code unique, 회사+id unique, due rule/days/version CHECK |
| counterparties | 회사+id unique, 사업자번호가 있을 때 회사+정규화 번호 partial unique, 회사 범위 Payment Term 복합 FK |
| counterparty_roles | 역할·기간 CHECK, 부모+역할+유효기간 배타 제약 |
| counterparty_contacts | 종류 CHECK, 거래처+종류별 primary partial unique |
| counterparty_addresses | 종류 CHECK, 거래처+종류별 primary partial unique |
| counterparty_bank_refs | opaque vault 참조 형식 CHECK, 상태 CHECK |
| accounting_settings | 회사 1:1 unique index, 통화/시작 월/접두어/리셋 정책/version CHECK |
| coa_templates | 코드+버전 unique, 유효시작일·상태·version |
| coa_template_accounts | 템플릿+코드 unique, 템플릿 범위 부모 FK, 정상 잔액 방향 CHECK |
| chart_of_accounts | 회사+코드 unique, 회사 범위 부모 복합 FK, 템플릿 provenance FK, 타입/잔액/상태/version CHECK |
| accounting_periods | 회사+회계연도+기간번호 unique, 날짜·version CHECK, 회사별 기간 배타 제약 |
| journal_sequences | 회사+회계연도+sequence_key unique, 비음수 번호 CHECK |

모든 신규 FK는 `ON DELETE RESTRICT`이고 FK 선두 컬럼 인덱스를 둡니다. 관계를 ARRAY로 저장하지 않습니다. 금액 컬럼은 이 Master에 필요하지 않아 추가하지 않았고 기존 strict Decimal/NUMERIC(19,4) 회귀를 유지합니다. 시간과 식별자는 기존 UTC/TIMESTAMPTZ·UUID convention을 사용합니다.

`btree_gist` 확장으로 UUID/문자열 equality와 날짜 범위 중첩을 하나의 PostgreSQL exclusion constraint에서 검사합니다. 종료일은 포함하고 열린 종료일은 무기한입니다. migration 실행 계정에는 이 trusted extension을 설치할 권한이 필요합니다. downgrade는 신규 테이블만 역순 제거하며 공유 확장을 삭제하지 않습니다.

## 거래처와 지급조건

사업자번호는 구분자·공백 제거 후 ASCII 숫자 10자리, 법인번호는 13자리입니다. 빈 값은 NULL이며 회사별 NULL 여러 건은 허용합니다. 이름은 NFKC/casefold/공백 축약 값으로 deterministic matching합니다. 정확한 사업자번호를 우선하고 다음으로 정규화 법인명을 조회합니다. 후보만 반환하며 자동 병합하지 않습니다.

ACTIVE/INACTIVE/BLOCKED를 명시하며 물리 삭제 API는 없습니다. 역할 CUSTOMER/SUPPLIER/PAYEE/TAX_COUNTERPARTY는 별도 유효기간 row입니다. 주 연락처·주소는 종류별 각각 최대 하나입니다. Create에서 child를 함께 생성하고 상세 조회로 확인할 수 있습니다. 역할 추가에는 expected_version이 필요하며 부모 version도 증가합니다.

지급조건은 IMMEDIATE(0일), NET_DAYS, MONTH_END_PLUS_DAYS와 due_days(0~3650)로 표현합니다. 계약상 due date가 있으면 우선하며 JSON DSL은 없습니다.

계좌 참조는 `vault:<UUID>` 형태만 허용합니다. 실제 vault/금융기관 연동과 원계좌 저장은 구현하지 않았습니다. 읽기 응답은 참조 토큰도 제외하고 별칭·은행코드·상태만 제공합니다. 사업자·법인번호는 마지막 세 자리 외 마스킹합니다. 로그에는 입력 값이나 SQL 오류 원문을 남기지 않습니다. 세무 판단·세율·VAT 공제 결론은 거래처에 없습니다.

## 초기화와 회계정책 결정

58의 회사별 materialization 의도를 보존하되, 이번 요청이 허용한 별도 `InitializeAccountingMaster` 명령으로 실행 시점을 분리했습니다. 기존 Company creation transaction은 확장하지 않습니다. OWNER/ADMIN이 템플릿과 회계연도·통화를 선택하면 설정, 25개 회사 계정, 12개 월별 기간, 번호 baseline을 원자적으로 생성합니다. 같은 회사·템플릿·연도·정책 재요청은 기존 결과를 반환하며 계정이나 번호를 다시 만들지 않습니다. 다른 초기화 조건은 409입니다.

초기화 후 통화·회계연도 시작 월·번호 리셋 정책은 일반 PATCH로 바꾸지 않습니다. 이미 생성된 기간·장부의 의미가 바뀌는 정책 변경은 후속 명시적 command에서 다룹니다. 현재 PATCH는 접두어와 수기 전표 허용만 expected_version으로 변경합니다. DB UPDATE에도 version 조건을 포함하며 오래된 요청은 409입니다.

41의 period_year/month/start/end 명칭 대신 이번 요청의 fiscal_year/period_no/start_date/end_date를 채택했습니다. 회계연도는 시작 달력 연도이며 1월이 아닌 시작 월도 12개월을 생성합니다. OPEN/CLOSED 조회 계약만 있고 Close/Reopen command는 없습니다. 41의 close_version/closed_at/closed_by는 후속 Closing 범위에서 추가합니다.

계정 타입 ASSET/LIABILITY/EQUITY/REVENUE/EXPENSE와 잔액 DEBIT/CREDIT를 Domain과 CHECK에서 검증합니다. 감가상각누계액을 표현하도록 명시적 is_contra를 템플릿과 회사 계정에 추가했습니다. ASSET/EXPENSE는 기본 DEBIT, 나머지는 CREDIT이며 차감계정만 반대입니다. 부모 계층은 시드/초기화에서 순환·미정의 부모를 검증하고 DB에서는 같은 템플릿·회사 부모 FK를 강제합니다.

기본 템플릿은 KR_STANDARD 버전 1, 유효시작일 2026-01-01입니다. 필수 20개 전기 계정과 분류용 부모 5개를 포함합니다. 법정 계정체계나 세무 판단을 대신하지 않습니다. 회사 계정은 별도 UUID row로 생성되어 템플릿 수정에 종속되지 않습니다. 시드는 동일 버전 내용을 덮어쓰지 않고 불일치하면 실패합니다.

번호 Repository는 `SELECT FOR UPDATE` 후 증가하며 호출 UoW가 커밋합니다. FISCAL_YEAR는 실제 연도, NEVER는 내부 fiscal_year=0을 사용합니다. 표시 형식은 Domain의 `J-2026-000001`입니다. 성공한 증가분은 유지되고 실패한 동일 트랜잭션 증가분은 rollback됩니다. 번호 할당 공개 API, Posting, 전표 테이블은 없습니다.

## API와 권한

모든 아래 API는 Bearer 인증과 필수 UUID `X-Company-ID`를 받습니다. 회사 선택은 권한이 아니며 매 요청 Principal·활성 멤버십·role_permissions를 DB에서 검증합니다. 접근 불가능한 회사/거래처는 404, 같은 회사 권한 부족은 403입니다. 변경 요청에는 기존 CSRF 헤더·Origin 검사도 적용합니다.

| API | permission |
| --- | --- |
| GET /accounting/settings, /accounts, /account-templates | account.read |
| PATCH /accounting/settings, POST /accounting/initialize | company.accounting_settings.update |
| GET /accounting/periods | period.read |
| GET /counterparties, /counterparties/{id}, /payment-terms | counterparty.read |
| POST /counterparties, /payment-terms | counterparty.create |
| PATCH /counterparties/{id}, POST /counterparties/{id}/status, /counterparties/{id}/roles | counterparty.update |

44의 기존 회계 권한은 변경하지 않았습니다. 55/이번 요청의 counterparty 권한은 read=OWNER/ADMIN/ACCOUNTANT/REVIEWER/VIEWER/AUDITOR, create/update=OWNER/ADMIN/ACCOUNTANT로 보수적으로 추가했습니다. counterparty.merge는 seed만 등록하고 grant/API는 없습니다. 병합은 감사·승인 경계가 준비될 때 별도 설계합니다.

Create/Update/Read/Command를 분리하고 Command는 extra=forbid입니다. 목록 필터는 name/status/role만 허용하고 추가 query를 거부합니다. 거래처 목록은 이름+UUID 순서의 최대 100개이며 범용 필터나 fuzzy merge는 없습니다. 기존 /health는 DB 연결이 필요 없는 200/{status:ok} liveness입니다.

## 실행

backend 가상환경에서:

```sh
python -m alembic upgrade head
python -m app.companies.infrastructure.seed
python -m app.accounting.templates.infrastructure.seed
```

두 seed는 스키마 migration과 분리되어 있으며 재실행 가능합니다. 프론트엔드에서 회사를 선택하면 권한에 따라 회계 초기 설정, 계정과목·기간 조회와 설정 수정이 나타납니다. 회사 전환 시 컴포넌트를 새로 만들고 늦게 도착한 이전 조회 결과를 버립니다. 인증 정본과 회사 선택을 합치지 않습니다.

## 검증과 Golden

전용 PostgreSQL 17 테스트 DB에서 빈 DB lifecycle, 002→003→002→003, 현재 head, Alembic diff, JSON/JSONB/ARRAY guard, FK 대상·실제 orphan, 회사 FK 인덱스, unique/check와 기간 overlap을 검사합니다. 초기화/시드 반복, stale version, 권한·IDOR·취소 membership, 동일 사업자번호 타 회사 허용과 외부 회사 지급조건 거부를 검증합니다.

8개 실제 연결의 동시 번호 할당은 1~8, rollback 후 다음 성공은 9입니다. 회사·연도·키별 독립 증가도 검사합니다. Golden CSV는 GOLDEN_CORP_001의 CUSTOMER_A(CUSTOMER), SUPPLIER_B(SUPPLIER)만 제공합니다. T001/T004 거래와 기초잔액 전기는 생성하지 않습니다.

최종 명령·결과는 [회계 마스터 검증 기록](verification-accounting-master.md)을 참고하세요.

## 제외와 다음 범위

Transaction/Evidence/Storage/실제 Import/Opening Balance/Journal/Posting/Ledger/Approval/Audit/Idempotency/AR/AP/Treasury/Jobs/Agent/LLM/Tax는 구현하지 않습니다. 기초잔액을 계정 balance UPDATE로 반영하지 않습니다.

51 보강과 57/59에 따라 다음은 **004_storage_evidence_intake**의 Storage/Evidence/Import 기본 물리 모델을 먼저 확정하고 **005_transactions**가 imports.id를 실제 FK로 참조하도록 이어가는 범위입니다. import_receipts의 후속 idempotency FK 등 생성 순서를 다시 검토해야 하며, 이 PR에서 이를 선행 생성하지 않았습니다.
