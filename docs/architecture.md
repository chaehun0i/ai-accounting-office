# 설계 추적과 모듈 경계

기준선은 [AI_Accounting_Office_v0.2.2_통합설계_구현명세](https://drive.google.com/drive/folders/1bJVY8fPsIw3iEaMeQZQJEsOjWpV5fMQ8)입니다. 아래 문서를 직접 읽고 skeleton 범위에 적용했습니다.

| 문서 | 적용 |
| --- | --- |
| [Bootstrap 초기개발 순서](https://docs.google.com/document/d/1ncDLHkVhaGNJsjEJfRGF6JXdnM-6IDufukfjVgxJgEU/edit) | 실행 기반만 구현, 업무 테이블/DB Foundation 보류 |
| [Repository Module Architecture](https://docs.google.com/document/d/1T6cyaFtBqbHVgwwjirk1cU4mT5wYPX7l82sq1OnbgpU/edit) | root, backend module, frontend feature, test 경계 |
| [File Level Migration Map](https://docs.google.com/document/d/1mt7Muxcfd98OXMA6RWolKrDL8YSVZEMatbzZ9J1yLvA/edit) | 기존 프로젝트 코드를 복사하지 않음 |
| [PostgreSQL DDL SQL Skeleton](https://docs.google.com/document/d/1Jwkd3Wjp8TiJYD2J3ESqlmH9nVmYmkABq2JQDMTQWaY/edit) | 후속 migration의 기준, 현재 SQL 없음 |
| [ADR Relational First No JSONB](https://docs.google.com/document/d/1vZrpygREDJltPy7ZZTse0FIbwMl50kOt_buZPzRsQ7U/edit) | 업무 PostgreSQL JSON/JSONB column 0개, 예외는 ADR |
| [Implementation DoD Review Checklist](https://docs.google.com/document/d/1jxhbyYgNEioeTns7uO0hhh88_AoydPvP6Ulm3JL1TXs/edit) | 적용 가능한 API/observability/security/test 기준만 검증 |
| [API Pydantic Contract](https://docs.google.com/document/d/1S90s8NzYyQX5clZSFmQ8b8U4eyodkqytBqVUff9TIVM/edit) | typed health response, 공통 typed 오류 |
| [Error Idempotency Concurrency Contract](https://docs.google.com/document/d/1y1sXqZro-tYwxqpDaE785fmEg3RKYiaFYP6hx-k0py8/edit) | stable code/request ID, traceback 비노출; persistence 보류 |
| [Agent Tool Contract](https://docs.google.com/document/d/1D5BHcn7iC0KlSDJRqU9_l6oYDEXB7AkGqSHGNX3HsPI/edit) | tools 경유, 직접 DB/Repository import 차단 |

## Backend 책임

`core`는 config/errors/logging 등 cross-cutting primitive만 소유합니다. 업무 로직은 두지 않습니다. `health.py`는 업무 모듈이 아닌 process liveness router/schema입니다. application factory는 설정·미들웨어·라우터 조합만 수행합니다.

`identity`, `companies`, `intake`, `accounting`, `finance`, `tax`, `closing`, `reporting`, `evidence`, `approvals`, `audit`, `jobs`, `agents`, `llm`, `tools`는 docstring만 있는 Python package 경계입니다. 기능이 생길 때 `domain/application/infrastructure/api`를 추가합니다. 지금 비어 있는 service/repository/model 파일을 미리 만들지 않습니다.

기본 의존성은 `api → application → domain`이며 infrastructure가 domain interface를 구현합니다. Router는 Repository를 호출하지 않습니다. domain은 FastAPI/ORM/LLM SDK에 의존하지 않습니다. 후속 Application Command가 transaction/UoW를 소유하고 Repository는 임의 commit하지 않습니다.

accounting은 장부 정본, tax는 세무 계산·신고 정본, evidence는 provenance를 소유합니다. jobs/agents/tools 실행 이력이나 LLM 출력이 정본을 대체하지 않습니다. generic entity/payload/settings model을 만들지 않습니다. 숫자는 Decimal/Domain Rule/Application Service/deterministic query가 계산합니다.

Agent → Tool Registry → Tool Adapter → Application Service → Domain/Repository 방향만 허용합니다. Runtime이 principal/company/permission을 주입하고 LLM은 이를 생성하지 않습니다. Posting, Close/Reopen, Filing, Payment 확정은 Human Approval과 Application Command를 통과합니다. 실제 Agent/Tool/Approval은 아직 없습니다.

## 현재 architecture guard

`backend/tests/contract/test_architecture.py`가 agents/llm의 Python AST를 검사합니다. 다른 app 모듈 import는 app.tools만 허용하며 상대 import, app에서의 import, ORM/DB driver, importlib와 직접 __import__/eval/exec 우회를 검사합니다. 금지 예제도 테스트합니다.

이는 정적 import 계약이며 Python sandbox가 아닙니다. 별칭·간접 호출·외부 라이브러리를 통한 동적 실행의 모든 경우를 증명하지 않습니다. Agent runtime을 구현할 때 capability/runtime 제한과 실제 side-effect 테스트를 추가해야 합니다. API/domain 내부의 전체 의존 방향 검사는 해당 계층 구현 시 확장합니다.

## 데이터베이스와 후속 범위

현재 ORM, SQL, migration, DB 연결 primitive, create_all이 없습니다. 업무 테이블과 PostgreSQL JSON/JSONB column은 모두 0개입니다. API JSON serialization은 저장 형식과 별개입니다.

다음 DB Foundation에서 SQLAlchemy/Alembic, UUID/Decimal convention, UoW/base repository/error base와 실제 migration/schema guard를 구현합니다. PostgreSQL catalog 검사로 JSON/JSONB column 금지를 증명하고 migration 검토에 ADR을 연결합니다. 이번 범위에서는 이를 선행 구현하지 않습니다.

## 품질 도구 결정

프론트엔드 lint는 ESLint 10과 typescript-eslint 권장 규칙을 사용합니다. 초기 eslint-config-next가 가져오는 간접 의존성의 high 취약점 5개를 피하고 최소 셸에 필요한 검사만 유지하기 위한 선택입니다. React hooks나 복잡한 Next.js UI가 추가되는 범위에서 필요한 규칙을 안전한 버전으로 확장합니다. TypeScript strict와 next typegen, production build 검증은 별도로 유지합니다.
