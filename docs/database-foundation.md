> 이전 구현 범위의 기록입니다. 현재 상태는 [Identity/Company](identity-company.md)와 [현재 검증](identity-verification.md)을 참고하세요.

# DB Foundation 구조와 마이그레이션 정책

단일 기준선은 [AI_Accounting_Office_v0.2.3_통합설계_구현보강](https://drive.google.com/drive/folders/17FO3EYPA64MItPL-_RQbgg1NhKr4I5mn)입니다. Repository Skeleton 다음 단계까지만 구현하며 업무 Entity/API/테이블은 없습니다.

## 책임과 의존 방향

| 위치 | 책임 |
| --- | --- |
| app/contracts/unit_of_work.py | ORM 없는 UoW Protocol, Application transaction 계약 |
| app/contracts/repository.py | 회사 범위를 요구하는 조회 Protocol |
| app/contracts/errors.py | 단일 ApplicationError hierarchy, 안전한 고정 메시지 |
| app/core/values.py | DB 없는 UUID/Decimal/UTC 값 규칙 |
| app/core/database/base.py, naming.py | DeclarativeBase, metadata, deterministic constraint 이름 |
| app/core/database/types.py | typed UUID/NUMERIC/TIMESTAMPTZ persistence boundary |
| app/core/database/engine.py, session.py | 호출자가 소유하는 엔진·세션 factory |
| app/core/database/unit_of_work.py | SQLAlchemy UoW 구현 및 session 조립 경계 |
| app/core/database/errors.py | SQLSTATE 기반 infrastructure 오류 변환 |
| app/core/database/schema.py | PostgreSQL catalog 정책 검사 |
| migrations/ | runtime 앱을 부팅하지 않는 Alembic 환경과 baseline |

Application → UoW/Repository Protocol ← infrastructure 구현 방향입니다. Domain/Application 계약은 SQLAlchemy/FastAPI를 import하지 않습니다. 구체 UoW의 session은 infrastructure에서 Repository를 조립하기 위한 것으로 Application/Domain 계약에 노출하지 않습니다. 실제 업무 Repository와 wiring은 후속 Domain에서 구현합니다.

기존 accounting/tax/evidence/finance/approvals/audit/jobs 경계를 유지합니다. Foundation은 이들의 정본을 소유하지 않습니다. generic entity/payload 모델, Agent state 저장소, 기존 프로젝트 Domain 코드는 없습니다. Agent → Tool Registry → Tool Adapter → Application Service → Repository/UoW 경계와 deterministic calculation, Human Approval 원칙을 유지합니다.

## 타입과 이름 규칙

- PK/FK 식별자는 Python `uuid.UUID` 및 PostgreSQL UUID입니다. `new_uuid()`는 Application의 자원 생성 시 uuid4를 발급합니다. DB default나 업무 ID 계층은 만들지 않습니다. 문자열은 persistence boundary에서 거부합니다.
- 금액은 유한한 `Decimal`과 `NUMERIC(19,4)`입니다. float, 범위 초과, 저장 시 반올림이 필요한 값을 거부합니다. `MoneyNumeric`은 반올림·세법 계산을 하지 않습니다. Domain은 명시적인 계산/반올림 정책을 별도로 소유합니다. float에서 이미 만든 Decimal의 출처까지 판별하지는 못하므로 Domain에서도 float를 사용하지 않아야 합니다.
- 시간은 aware datetime과 PostgreSQL TIMESTAMPTZ입니다. naive 값을 거부하고 UTC로 정규화합니다. 연결 timezone도 UTC이며 원래 offset 표현 대신 같은 시점의 의미를 보존합니다.
- Base type annotation map은 UUID/Decimal/datetime에 위 타입을 적용합니다. 실제 column은 아직 없습니다.
- PK `pk_<table>`, FK `fk_<table>_<columns>_<target>`, UNIQUE `uq_<table>_<columns>`, INDEX `ix_<table>_<columns>`입니다. CHECK는 의미 있는 명시적 이름을 붙여 `ck_<table>_<name>`을 생성합니다. 긴 이름의 PostgreSQL 제한은 SQLAlchemy의 deterministic truncation에 맡깁니다.

## Session과 transaction ownership

Session은 autoflush=false, expire_on_commit=false, autobegin=false입니다. implicit transaction 재시작을 막고 UoW가 명시적으로 begin합니다. 정상 scope 종료는 commit, body 예외는 rollback, commit 실패도 rollback하며 항상 close합니다. persistence 예외는 안전한 ApplicationError로 변환합니다. commit 실패 시 성공으로 간주하지 않습니다.

명시적 commit/rollback은 현재 scope를 종료합니다. 이후 session 접근은 실패하며 scope 종료 시 다시 commit하지 않습니다. commit 후 발생한 예외로 이미 확정된 데이터를 되돌릴 수는 없습니다. 따라서 승인·업무 검증은 commit 전에 수행하며 정상 context 종료 방식을 권장합니다. 중첩 UoW/savepoint는 이번 계약에 없습니다. 하나의 UoW를 동시에 공유하지 않습니다.

Repository는 commit/rollback/begin을 소유하지 않습니다. Application Command가 승인 검증과 변경을 하나의 UoW 안에서 조합합니다. 공통 Repository는 `get(*, company_id: UUID, resource_id: UUID)`만 정의하며 거대 CRUD를 제공하지 않습니다. 회사 범위 없는 `get_by_id(id)`는 기본값이 아닙니다. 향후 별도 Control Plane의 전역 조회는 명시적인 예외 계약과 검토가 필요합니다.

## 안전한 오류

SQLAlchemy 예외 문자열을 읽거나 사용자에게 전달하지 않고 PostgreSQL SQLSTATE와 예외 종류로 분류합니다.

| 원인 | Application 오류 / HTTP |
| --- | --- |
| 연결 실패, class 08, 서버 종료 | DatabaseUnavailable / UPSTREAM_UNAVAILABLE 503 |
| UNIQUE 23505 | UniqueConflict / BUSINESS_RULE_VIOLATION 422 |
| FK 23503 | ForeignKeyConflict / BUSINESS_RULE_VIOLATION 422 |
| 기타 class 23 | IntegrityViolation / BUSINESS_RULE_VIOLATION 422 |
| serialization 40001, deadlock 40P01 | ConcurrencyConflict / VERSION_CONFLICT 409 |
| lock unavailable 55P03 | ResourceLocked / RESOURCE_LOCKED 409 |
| strict persistence 값 거부 | InvalidPersistenceValue / INVALID_INPUT 422 |
| 기타 DB 오류 | PersistenceError / INTERNAL_ERROR 500 |

기존 공통 오류 envelope/request_id를 유지합니다. 원문 SQL, credential, 매개변수, traceback은 API나 앱 로그에 넣지 않습니다. 엔진 echo/echo_pool=false와 hide_parameters=true를 고정합니다. 앱 시작과 `/health`는 DB 연결을 시도하지 않습니다. readiness API와 자동 재시도는 추가하지 않습니다.

## Migration lifecycle

`alembic.ini`에는 secret/URL이 없고 `env.py`가 typed settings와 Base.metadata만 참조합니다. application runtime과 업무 API를 boot하지 않습니다. `create_all()`은 사용하지 않습니다. 현재 `db_foundation` baseline은 upgrade/downgrade 모두 업무 DDL이 없고 Alembic 자체의 version 상태만 기록합니다.

`upgrade head` 전후 같은 migration transaction에서 schema guard를 실행합니다. 실패하면 migration이 확정되지 않습니다. offline SQL 생성은 접속 없이 가능하지만 실제 catalog 검사를 대신하지 못합니다. CI는 실제 PostgreSQL online migration과 integration을 요구합니다.

후속 번호는 **59_Complete_DDL_Migration_Map_v0.2.3**을 우선합니다. 41/51에 남아 있는 이전 번호 예시와 충돌할 때 59의 완전한 migration map을 적용합니다. 현재 baseline은 아래 업무 번호를 소비하지 않습니다.

| 예정 순서 | 소유 범위 |
| --- | --- |
| 001_identity | users, sessions, security events |
| 002_tenant_company_rbac | tenant/company, 역할·권한·membership/invitation |
| 003_master_accounting_settings | master/accounting policy |
| 004_storage_evidence_intake | storage/evidence/intake |
| 005_transactions | transactions |
| 006_journal_core | journal core |
| 007_governance | approval/audit 등 governance |
| 008_finance_subledger | finance subledger |
| 009_jobs_agents | 실행 이력 |
| 010_tax_profile_rules | tax profile/rules |
| 011_tax_treatment_adjustment | tax treatment/adjustment |
| 012_tax_forms_filing | tax forms/filing |
| 013_reporting_optional_snapshots | 선택적 reporting snapshots |

위 migration 파일과 업무 테이블은 만들지 않았습니다. migration message와 revision 파일명에는 기능 목적을 기록합니다.

## Relational-First guard

현재 관리 대상은 `public`입니다. pg_catalog/information_schema와 PostgreSQL 임시 스키마는 대상에서 제외합니다. 추후 별도 프로젝트 schema를 도입하면 호출부의 allowlist를 함께 확장해야 합니다.

catalog 검사는 JSON/JSONB뿐 아니라 domain wrapping 및 ARRAY element도 순회하여 schema/table/column/type 위반 목록을 반환합니다. 초기 foundation은 ARRAY도 모두 거부합니다. 식별자 관계는 FK/child/join table로 표현하며, 별도 scalar ARRAY 필요성도 향후 정책 검토 없이 도입하지 않습니다. API JSON serialization은 DB 저장 정책과 다릅니다.

테스트는 별도 임시 schema에서 JSON/JSONB/domain/array 위반을 실제로 만들어 탐지를 확인한 후 transaction rollback으로 제거합니다. 운영 migration에는 테스트 테이블을 넣지 않습니다. UUID/Decimal/time round trip과 commit/rollback은 TEMP TABLE로 검증하고 연결 종료로 제거합니다.

## 검증 운용

DB 없는 unit/contract는 독립 실행됩니다. PostgreSQL integration은 `_test` 이름의 별도 DB와 TEST_POSTGRES_URL을 요구합니다. `--require-postgres`를 CI와 전체 완료 검증에서 사용하여 skip으로 통과하지 못하게 합니다. migration test는 empty schema → upgrade → 재실행 → current head → metadata 비교 → downgrade → upgrade를 검증합니다. public에 예상치 못한 테이블이 있으면 삭제하지 않습니다.

Windows Alembic Config는 locale encoding으로 ini를 읽으므로 ini는 ASCII 설정만 유지합니다. 한글 설명은 이 문서와 Python 주석에 둡니다. 직접 작성한 주석/docstring 및 사용자 안내는 한글 원칙을 유지합니다.

다음 구현 범위는 Identity/Company입니다. 인증/RBAC와 실제 company scope enforcement는 그 범위에서 추가하며 foundation만으로 접근 권한이 구현된 것은 아닙니다.
