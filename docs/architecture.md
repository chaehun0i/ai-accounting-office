# 설계 추적과 모듈 경계

현재 기준선은 [AI_Accounting_Office_v0.2.5_통합설계_정본](https://drive.google.com/drive/folders/14f9qJtr7eKzC12n8GpdHcNc3Ff2nyYpf)입니다. fallback 없이 확인한 최신 설계와 적용은 [파일·증빙·인테이크](storage-evidence-intake.md)에 기록했습니다.

## 초기 DB Foundation 설계 추적

아래 v0.2.3 문서는 이전 구현 당시의 이력입니다. 현재 범위에 이전 버전 fallback으로 적용하지 않습니다.

| 문서 | 적용 |
| --- | --- |
| [51 Bootstrap](https://docs.google.com/document/d/1z73FQSN4SZ3mNRm42-8k3umUfJFXfVjedH75bpTad1s/edit) | Skeleton 다음 DB Foundation만 구현 |
| [59 Complete DDL Migration Map](https://docs.google.com/document/d/1A_JnJ_-arKHFakEsQAo-El0RpwxVKW1R_jjnqx2O518/edit) | 후속 001_identity/002_tenant_company_rbac 번호 보존 |
| [53 PostgreSQL DDL Skeleton](https://docs.google.com/document/d/1arwJGAxHJY2oWQfK9EOFKjl_n6iE4hTS-P0txr4Q67g/edit) | UUID, NUMERIC(19,4), TIMESTAMPTZ convention |
| [42 Relational First 정책](https://docs.google.com/document/d/12Aplp-KL-P9H_Har_wAWm6ZYN7ljJVERgnG8SxiupSk/edit) | JSON/JSONB 금지, 관계 ARRAY 금지 |
| [48 Repository Architecture](https://docs.google.com/document/d/1LcVMzK_CUeXzhyiWjOmXKpvNZ65HiZ_qisbMAs8EQ1Q/edit) | ORM 없는 Application 계약, 정본·모듈 경계 |
| [52 DoD](https://docs.google.com/document/d/1EekWD2gPPJ0nzNpopBD31hKy9BsfOvyLxxYIGFjO1CE/edit) | 실제 PostgreSQL·회귀·보안 검사 |
| [41 Physical ERD](https://docs.google.com/document/d/1mfHCGFCCJqhQ4VEWd04PSgQSBNHZaXOUDSbgUp9EEYk/edit) | 물리 타입 확인, 업무 테이블 선행 구현 금지 |
| [46 Error/Idempotency/Concurrency](https://docs.google.com/document/d/1oNaQ-Hep-VsRwksEIP-8owfVsafUYY8kup-TdzBmnFc/edit) | 안전한 오류 코드와 concurrency 분류 |

## Backend 책임

`core`는 config/errors/logging 등 cross-cutting primitive만 소유합니다. 업무 로직은 두지 않습니다. `health.py`는 업무 모듈이 아닌 process liveness router/schema입니다. application factory는 설정·미들웨어·라우터 조합만 수행합니다.

`identity`, `companies`, `intake`, `accounting`, `finance`, `tax`, `closing`, `reporting`, `evidence`, `approvals`, `audit`, `jobs`, `agents`, `llm`, `tools`중 Identity/Company/Accounting/Master Data/Storage/Evidence/Intake는 실제 구현이 있으며 나머지는 Python package 경계입니다. 기능이 생길 때 `domain/application/infrastructure/api`를 추가합니다. 지금 비어 있는 service/repository/model 파일을 미리 만들지 않습니다.

기본 의존성은 `api → application → domain`이며 infrastructure가 domain interface를 구현합니다. Router는 Repository를 호출하지 않습니다. domain은 FastAPI/ORM/LLM SDK에 의존하지 않습니다. Application Command가 transaction/UoW를 소유하고 Repository는 임의 commit하지 않습니다.

accounting은 장부 정본, tax는 세무 계산·신고 정본, evidence는 provenance를 소유합니다. jobs/agents/tools 실행 이력이나 LLM 출력이 정본을 대체하지 않습니다. generic entity/payload/settings model을 만들지 않습니다. 숫자는 Decimal/Domain Rule/Application Service/deterministic query가 계산합니다.

Agent → Tool Registry → Tool Adapter → Application Service → Domain/Repository 방향만 허용합니다. Runtime이 principal/company/permission을 주입하고 LLM은 이를 생성하지 않습니다. Posting, Close/Reopen, Filing, Payment 확정은 Human Approval과 Application Command를 통과합니다. 실제 Agent/Tool/Approval은 아직 없습니다.

## 현재 architecture guard

`backend/tests/contract/test_architecture.py`가 agents/llm의 Python AST를 검사합니다. 다른 app 모듈 import는 app.tools만 허용하며 상대 import, app에서의 import, ORM/DB driver, importlib와 직접 __import__/eval/exec 우회를 검사합니다. 금지 예제도 테스트합니다.

이는 정적 import 계약이며 Python sandbox가 아닙니다. 별칭·간접 호출·외부 라이브러리를 통한 동적 실행의 모든 경우를 증명하지 않습니다. Agent runtime을 구현할 때 capability/runtime 제한과 실제 side-effect 테스트를 추가해야 합니다. Domain/Application/contracts의 SQLAlchemy/FastAPI/DB infrastructure 의존을 추가 검사합니다. Repository 파일의 commit/rollback/begin/begin_nested 호출도 금지합니다. 실제 모듈에 더해 금지 예제를 검증하며 향후 계층이 추가되면 자동 검사 대상이 됩니다.

## 데이터베이스와 후속 범위

SQLAlchemy/Alembic, strict UUID/Decimal/UTC 타입, UoW와 회사 범위를 필수로 받는 Repository Protocol이 존재합니다. baseline 위에 Identity/Company 업무 테이블 10개를 001/002, 회계 마스터 12개를 003 revision으로 등록합니다. 자동 create_all은 없습니다.

[DB Foundation 구조와 migration 정책](database-foundation.md)에 타입·transaction·error·schema guard 및 후속 migration map을 설명합니다. 실제 PostgreSQL의 JSON/JSONB column 0개를 integration과 online migration 전후에 검사합니다. API JSON serialization은 DB 저장 형식과 별개입니다. 현재 Identity/Company 구조와 구현 결정을 [인증·회사 계약](identity-company.md)에 기록했습니다. 회계 마스터는 [현재 구조와 결정](accounting-master.md)을 따릅니다. Storage/Evidence/Intake 11개 테이블을 004에 추가했으며 005 Onboarding/Data Exchange의 10개 관계형 테이블을 추가하여 전체 업무 테이블은 43개입니다. 이후 006 Transaction의 FK를 연결합니다. [온보딩 계약](onboarding-data-exchange.md)을 따릅니다. [현재 계약](storage-evidence-intake.md)을 따릅니다.

## 품질 도구 결정

프론트엔드 lint는 ESLint 10과 typescript-eslint 권장 규칙을 사용합니다. 초기 eslint-config-next가 가져오는 간접 의존성의 high 취약점 5개를 피하고 최소 셸에 필요한 검사만 유지하기 위한 선택입니다. React hooks나 복잡한 Next.js UI가 추가되는 범위에서 필요한 규칙을 안전한 버전으로 확장합니다. TypeScript strict와 next typegen, production build 검증은 별도로 유지합니다.
