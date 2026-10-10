# 회계 온보딩과 데이터 병합

시작 main: `85e23b1bd2e94c7d4d22bd5447222964bf5f863c`. 브랜치: `feat/onboarding-data-exchange`.
원격 main을 fetch/fast-forward pull하고 기존 Alembic head `004_storage_evidence_intake`를 확인했습니다.
단일 기준선은 [AI_Accounting_Office_v0.2.5_통합설계_정본](https://drive.google.com/drive/folders/14f9qJtr7eKzC12n8GpdHcNc3Ff2nyYpf)입니다. 활성 문서만 확인했으며 과거 버전 fallback은 사용하지 않았습니다.

## 설계 추적

문서지도와 제품 개발 로드맵을 먼저 읽고 Onboarding → Transaction/Journal/Ledger 순서를 확인했습니다.
Onboarding Workspace, Data Exchange Round Trip, Excel/CSV Mapping, Intake Physical Schema, Evidence/Provenance,
Physical ERD/DDL, Relational-First, API/Pydantic, Error/Idempotency/Concurrency, Repository Architecture,
Complete DDL Map, Permission Matrix, State Transition Matrix를 코드와 대조했습니다.
Golden Cases, Golden Dataset, DoD, 전산회계운용사 Coverage와 샘플회사 가이드도 확인했습니다.
Storage/Evidence/Intake를 재구현하지 않고 기존 서비스·파서·UoW를 조합했습니다.

## 사용 흐름과 화면

로그인하고 회사를 선택하면 직접입력 Form이 기본입니다. 별도 입력 방식 선택 카드는 없습니다.
상단 Excel 업로드 버튼 하나로 Modal을 열고, Modal 안에서만 공식 양식을 다운로드하거나 업로드합니다.
Section별 기본 입력 Group 또는 Row Item을 편집하고 초안을 저장합니다. 진행률과 검증 결과는 서버가 계산합니다.
저장하지 않은 변경사항이 있으면 Excel 병합과 완료를 막습니다. 회사가 바뀌면 화면 상태를 새로 생성합니다.

Excel 미리보기는 현재 값과 들어올 값을 비교합니다. 빈 필드는 신규, 같은 값은 동일,
다른 값은 충돌입니다. 충돌마다 **현재 값 유지** 또는 **Excel 값 적용**을 선택해야 합니다.
적용 이후에도 직접 수정할 수 있습니다. 검증·재계산 후 지원하는 데이터만 최종 정본에 반영합니다.
로딩, 조회 권한 없음, 빈 항목, 저장 중/저장 완료, 검증 오류, 충돌, 파생값 재계산 필요 상태를 표시합니다.

## 관계형 저장 구조

신규 revision: `005_onboarding_data_exchange` → 이전 revision `004_storage_evidence_intake`.

| 테이블 | 책임 |
| --- | --- |
| onboarding_sessions | 회사별 단일 초안, 상태·version·시작/완료 정보 |
| onboarding_sections | Section 상태·필수 여부·표시 순서 |
| onboarding_field_definitions | 단일 코드 Catalog의 불변 UUID 정의 |
| onboarding_row_items | Section별 안정적인 업무 키 |
| onboarding_values | text/numeric/date/boolean 중 하나만 사용하는 현재 값 |
| onboarding_value_history | 이전 값·source·version·수정자·source Import 이력 |
| onboarding_validation_results | 안전한 코드·메시지와 field/row 위치 |
| onboarding_imports | 기존 Import와 초안·Template 버전 연결 |
| onboarding_apply_receipts | Apply 요청 fingerprint·source digest·집계·참조 |
| onboarding_promotion_receipts | 완료 요청 fingerprint·계정/거래처 생성 수·참조 |

기존 companies에는 timezone, accounting_settings에는 accounting_framework_code와 reporting_taxonomy_code,
counterparties에는 nullable counterparty_code와 회사별 unique를 추가했습니다.
기존 Import는 공식 양식 source와 최대 16 Sheet/빈 Sheet의 metadata를 수용합니다.
일반 CSV/XLSX 입력의 엄격한 기본 파서 제한은 유지합니다.
모든 FK는 RESTRICT, 회사 scope와 주요 참조에 index/unique/check를 둡니다.
NUMERIC(19,4), UUID, timezone-aware timestamp 규칙을 유지하며 JSON/JSONB/ARRAY·원본 파일 bytes를 저장하지 않습니다.

## 단일 Field Catalog와 직접입력

정의 위치: `backend/app/onboarding/domain/catalog.py`.
Field code, Section, 표시명, 자료형, 입력 모드, required rule, enum source, derived handler, 표시 순서, 활성 여부를 정의합니다.
API가 이 Catalog를 제공하며 화면, 공식 XLSX 헤더/README, 검증, DB 등록이 같은 정의를 사용합니다.
전체 필드 목록은 [필드 목록](onboarding-fields.md)에 기록합니다.

값은 field_definition + row_key로 식별합니다. 단일값 Group은 `singleton`입니다.
숫자는 문자열로 전송해 Decimal로 검증하며 float와 과도한 소수 자릿수, NaN/Infinity를 거부합니다.
DB CHECK는 `num_nonnulls(value_text,value_numeric,value_date,value_boolean)=1`입니다.
Excel 값을 직접 바꾸면 현재 source는 MANUAL로 전환하고 이전 EXCEL_IMPORT/source_import를 관계형 이력에 보존합니다.
동일 값은 불필요하게 다시 쓰지 않습니다. 시스템 기본값은 기존 회사·회계 설정에서 복구합니다.

필수 규칙은 ALWAYS, NEVER, CORPORATION의 결정론적 코드입니다.
법인일 때만 법인번호를 요구합니다. KRW만 허용하며 외화를 조용히 변환하지 않습니다.
신규 회사는 `Company.no_opening_balance=true`로 기초잔액 없음에 명시적으로 동의할 수 있습니다.

진행률 분모는 활성·편집 가능한 실제 입력 Field/Row입니다.
DERIVED_READONLY, SYSTEM_DEFAULT, 숨겨진 조건부 필드는 제외합니다.
분자는 VALID 값이며 검증 오류가 있으면 WARNING입니다. 진행률만으로 완료 가능 여부를 판단하지 않고 필수 검증을 별도로 통과해야 합니다.

## 파생 계산

Opening_Balances/COA 원천값이 바뀌면 파생값을 STALE로 표시합니다.
검증 명령이 Decimal로 차변 합계, 대변 합계, 차액을 재계산합니다. LLM/Agent는 사용하지 않습니다.
계정 유형과 정상 잔액의 불일치는 ACCOUNT_BALANCE_REVIEW로 차단합니다.
샘플의 감가상각누계액 같은 차감 계정은 후속 명시적 회계정책 지원 전 자동 승격하지 않습니다.

## 공식 Excel 양식과 Intake 연결

Template code `ACCOUNTING_ONBOARDING`, Template version `1`, schema version `1`, locale `ko-KR`.
generated_at을 Metadata Sheet에 넣습니다. 앱 버전과 Template 버전은 독립적입니다.
breaking change는 새 Template version으로 발행해야 하며 기존 definition drift는 조용히 덮어쓰지 않습니다.

지원 Sheet: README, Company, Accounting_Settings, COA, Counterparties, Bank_Accounts, Card_Accounts,
Opening_Balances, Fixed_Assets, Inventory_Items, Opening_Inventory, AR_Opening, AP_Opening, Metadata.
부분 Sheet 입력도 가능하며 공식 헤더와 metadata를 검증합니다.
공식 양식은 macro 없는 XLSX입니다. 기존 안전 parser의 공식 양식 profile만 사용하며 별도 파서를 만들지 않습니다.
파일 제한은 2,000,000 byte, 최대 16 Sheet, Sheet당 1,000 data row/40 column, cell 4,000자입니다.
ZIP entry 100개, 확장 크기 20,000,000 byte, XML markup 500,000 byte 제한도 적용합니다.
ZIP entry/확장 크기, 경로, XML entity/DOCTYPE, 매크로/VBA, 외부 링크, embedded object, ActiveX, 수식 등 기존 방어를 유지합니다.
CSV는 기존 Intake에서 UTF-8/BOM으로 처리합니다. 공식 온보딩 양식 API는 XLSX만 받습니다.

자유 매핑 거래처 CSV/XLSX도 기존 `/imports`에서 COUNTERPARTY + ONBOARDING_DRAFT로 업로드/매핑한 후
`POST /onboarding/imports`에 `{existing_import_id}`를 보내 연결할 수 있습니다.
현재 자유 매핑 연결은 COUNTERPARTY만 지원합니다. 나머지 source를 임의 추론하지 않습니다.
일반 Import confirm으로 ONBOARDING_DRAFT를 우회할 수 없습니다.
Apply 후 원본 Import를 COMPLETED로 고정하므로 mapping 변경도 거부합니다.

## API

기존과 같이 백엔드에는 별도 `/api` prefix가 없습니다. 브라우저의 `/api/*`는 Next.js가 proxy합니다.
인증, 정확한 Origin/CSRF header, X-Company-ID, backend permission을 검사합니다.

| 요청 | 책임 |
| --- | --- |
| GET /onboarding | 초안 생성/복구와 Catalog·진행률 |
| PATCH /onboarding/values | expected_version과 typed 값 저장 |
| POST /onboarding/validate | 재계산·필수/미지원 검증 |
| GET /onboarding/templates/current | 공식 macro-free XLSX 다운로드 |
| POST /onboarding/imports | 공식 파일 업로드 또는 기존 매핑 Import 연결 |
| GET /onboarding/imports/{id} | 요청자·회사 범위 연결 상태 |
| POST /onboarding/imports/{id}/preview | 재파싱한 병합 미리보기 |
| POST /onboarding/imports/{id}/apply | 명시적 충돌 선택 후 초안 적용 |
| POST /onboarding/complete | 현재 Domain Command의 원자적 승격 |

Update/Command는 extra=forbid입니다. ORM을 응답으로 직접 노출하지 않습니다.
API에는 안전한 stable 오류와 request_id만 반환합니다. 원본 cell/SQL/credential은 오류 메시지·로그에 넣지 않습니다.

## 병합·무결성·동시성

| Section | 안정적인 row key |
| --- | --- |
| COA | account_code |
| Counterparties | counterparty_code |
| Bank_Accounts / Card_Accounts | bank_account_code / card_account_code |
| Fixed_Assets / Inventory_Items | asset_code / item_code |
| Opening_Balances | as_of_date + account_code + optional counterparty_code |
| Opening_Inventory | as_of_date + item_code |
| AR_Opening / AP_Opening | counterparty_code + reference_code |

이름 fuzzy match, 자동 merge/overwrite는 없습니다. SAME는 UNCHANGED, 다른 기존 값은 CONFLICT입니다.
KEEP_CURRENT/APPLY_IMPORT 선택은 충돌 항목과 정확히 일치해야 하며 누락/여분 선택을 거부합니다.
집계는 Field/Row cell 기준입니다. 신규·변경·동일·충돌·오류를 접수증에 저장합니다.

Preview 전체 행은 요청 중 메모리에만 존재합니다. Redis/PostgreSQL에 row blob을 저장하지 않습니다.
유효기간은 900초이며 DB에는 digest/expiry만 저장합니다.
digest는 파일 SHA-256, session ID/version, mapping version, source/target,
preview 정의 버전, typed normalized field/row/value로 계산합니다.
Apply 때 파일 해시를 확인하고 다시 파싱하여 digest·버전·만료·요청자를 재검증합니다.
session row lock과 expected_version으로 마지막 write wins를 금지합니다.

Apply/Complete는 회사별 Idempotency-Key + fingerprint를 relational receipt로 저장합니다.
동일 요청은 기존 receipt, 다른 fingerprint는 IDEMPOTENCY_CONFLICT입니다.
Complete fingerprint는 회사/초안 버전/command version, Apply는 Import/초안 버전/digest/선택으로 구성합니다.
Receipt에 전체 API response를 저장하지 않습니다. Repository는 독립 commit하지 않습니다.

## 정본 승격과 미지원 데이터

Complete는 하나의 Onboarding UoW 안에서 Company, Accounting, Master Data의 Application Command를 호출합니다.
회사 profile/timezone, 회계 설정, 회사 COA, 기간/시퀀스 기반, 코드가 있는 거래처와 역할을 지원합니다.
지급조건은 기존 company-scoped term_code를 참조하며 없는 코드는 완료를 차단합니다.
기존 동일 Master는 재생성하지 않습니다. 동일 code의 다른 정본은 안전한 conflict로 중단합니다.
승격 대상 Domain의 기존 permission도 통과해야 합니다. onboarding.complete만으로 다른 권한을 우회하지 않습니다.
중간 실패 시 회사 변경을 포함해 전체 rollback하며 receipt를 만들지 않습니다.

은행/카드, 기초잔액, 고정자산, 재고, AR/AP 데이터는 Draft+Validation까지만 보존합니다.
하나라도 입력되면 PENDING_DOMAIN_SUPPORT로 완료를 BLOCK합니다. 지원된 부분만 조용히 승격하지 않습니다.
기초잔액 없음 확인은 0원 가짜 row를 생성하지 않습니다.
Opening Balance는 향후 validated import → DRAFT/SUBMITTED → 별도 승인/Post Command로 연결해야 합니다.
이번 코드는 account balance UPDATE나 POSTED Journal을 생성하지 않습니다.

## 2025 synthetic fixture

공식 정본은 [native Google Sheet](https://docs.google.com/spreadsheets/d/1C_URD6dlROitLTmN6ZTAhBdebF0Dc3_bl3dzaIiXvA8/edit)입니다.
회사 SYN_MFG_001, 가온푸드웍스 주식회사, 2025-01-01~12-31, 식품 제조/B2B 도매, 법인/KRW입니다.
macro-free export를 `backend/tests/fixtures/onboarding/sample-company-2025-v1.xlsx`에 변경 없이 보관합니다.
SHA-256: `c4df64f12fc517b73f1ef0c164bdeb541c1039a6c43d8ee3971310b414761d02`.

`derive_fixture.py`는 원본을 읽기만 하고 지원 Sheet/헤더를 공식 Template에 맞춘 별도
`onboarding-syn-mfg-2025-derived-v1.xlsx`를 생성합니다. 원본 schema를 덮어쓰지 않습니다.
변환: source 회계기준 → K_GAAP, 거래처 CUSTOMER/SUPPLIER → BUSINESS + role_code 보존,
posting 1/0 → boolean, 이동가중평균 source → WEIGHTED_AVERAGE,
기초 재고 quantity/unit_cost → opening_quantity/opening_unit_cost. 세무 Sheet는 승격/정답으로 사용하지 않습니다.
Company, 19 COA, 20 Counterparty, 8 Opening Balance, 12 Asset, 12 Inventory Item, 12 Opening Inventory의
425 typed cell을 정확히 비교합니다. 차변/대변 원천 합계는 각각 280,000,000 KRW입니다.
없는 사업자/법인번호를 fixture에 발명하지 않고 수동 회사 정보와 병합합니다.
`.xlsm`은 공식 fixture가 아니며 업로드 거부 회귀에만 사용합니다. 확인 당시 활성 샘플 폴더에는 가이드와 native Sheet가 있었습니다.
향후 baseline 변경은 v2와 변경 이유/expected 차이를 별도로 기록해야 합니다.

## 실제 Reference와 충돌 해결

WITH ESG `shell-files/dev_skm` commit `720e33c7923a679c2cff694ca12c9f92646ed06b`의 실제 파일을 읽었습니다.

| 실제 소스 | 분류 | 신규 대상·처리 |
| --- | --- | --- |
| frontend/src/homes/onboards/OnBoard.jsx | ADAPT | frontend/src/features/onboarding/onboarding-workspace.tsx: 회사 context, 편집/상태/복구 패턴만 재작성 |
| frontend/src/homes/onboards/onboardingUtils.js | ADAPT | model.ts, backend domain/validation.py: 입력 모드·진행률을 서버 Catalog/규칙으로 통일 |
| backend/src/apis/onboarding.py | PATTERN | onboarding/api/router.py: scoped list/PATCH 구조만 참고, query company trust·raw detail 제거 |
| backend/src/repositories/onboardinginputrepository.py | ADAPT/PATTERN | infrastructure/repository.py, domain/validation.py: typed 값/이력·의존값 invalidation 재작성 |
| ESG assignment/approval 개념 | PATTERN | 현재 전체 workflow 이식 없음, 향후 고위험 승인 contract만 유지 |
| ESG metric/DMA/rollup/MariaDB/int PK/직접 commit/float | DROP | 신규 회계 Domain으로 가져오지 않음 |

COPY는 없습니다. React Router/Redux, ESG workflow, 직접 SQL, repository-owned transaction은 제거했습니다.
신규 코드는 UUID/PostgreSQL/SQLAlchemy/UoW, active company/RBAC, Decimal, 단일 Catalog를 따릅니다.
ServIQ를 재이식하지 않고 이미 병합된 신규 Intake의 parser/storage/evidence/digest를 composition합니다.

## 검증과 실행

일반 설치·Compose·quality 명령은 루트 README와 같습니다. 테스트 DB 이름은 반드시 `_test`로 끝나야 합니다.
PostgreSQL integration에는 `TEST_POSTGRES_URL`을 별도로 지정하세요. 운영/개발 DB를 migration lifecycle 테스트에 사용하지 마세요.

```sh
cd backend
python -m pytest --require-postgres
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy app
python -m pip check
python -m alembic current
python -m alembic upgrade head
python -m alembic current --check-heads
python -m alembic check
cd ../frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

브라우저 smoke는 별도 synthetic DB에 migration/permission seed 후 백엔드와 Next.js를 실행해 사용합니다.
허용 FRONTEND_ORIGIN과 브라우저 origin을 정확히 일치시키세요. 기존 서비스를 종료하지 말고 필요하면 별도 포트를 사용하세요.
Playwright와 Edge가 있는 환경에서 루트의 다음 명령을 실행합니다. 별도 설치 경로는 PLAYWRIGHT_MODULE_PATH에 지정할 수 있습니다.

```sh
node scripts/onboarding-browser-smoke.cjs --allow-synthetic
```

실행은 테스트 계정/회사를 생성합니다. 원본 fixture를 수정하지 않습니다. 실패 screenshot은 ignored `.local/`에만 저장합니다.
검증 실측과 commit 목록은 [검증 기록](onboarding-verification.md)에 정리합니다.

## 알려진 제한과 후속 계약

- 공식 양식 v1과 자유 매핑 COUNTERPARTY만 Draft 연결을 지원합니다. 전체 spreadsheet 자동 이해 기능이 아닙니다.
- 현재 직접입력은 기존 값을 새 값으로 바꾸는 계약입니다. 저장된 값을 빈 값으로 지우는 삭제 Command는 제공하지 않으며 화면에서 명확히 거부합니다.
- 파일 저장/기존 Import 업로드와 초안 연결은 각각 UoW입니다. 연결 실패로 남은 원본 Import는 canonical 승격되지 않으며 운영 정리 정책이 필요합니다.
- 전체 2025 샘플은 미지원 Domain/차감 계정 검토로 완료가 차단됩니다. 데이터 보존이 우선입니다.
- 전체 샘플 처리의 성능 목표나 실제 금융 vault/provider는 이번 변경에서 인증하지 않았습니다.
- Browser smoke는 별도 테스트 환경에서 실행하며 CI는 PostgreSQL/API/Golden/Schema 및 frontend unit/build gate를 수행합니다.
- 다음 Transaction·Journal·Ledger는 Evidence/Import provenance, validated opening Draft, promotion capability,
  회사별 Master, Decimal, UoW, permission, expected_version/receipt 계약을 이어받아야 합니다.
  승인/기간 lock/Post를 일반 PATCH나 온보딩 Complete로 우회해서는 안 됩니다.
