# AI Accounting Office

회계 장부와 세무 계산·신고 정본을 분리하고, AI의 제안을 결정적 검증과 사람의 승인으로 연결하는 서비스입니다.

현재 구현 범위는 **Repository Skeleton + DB Foundation**입니다. 기존 실행 기반 위에 SQLAlchemy/Alembic, 관계형 타입 규칙, Unit of Work, Repository 계약과 실제 PostgreSQL 검증을 제공합니다. 업무 테이블과 인증은 아직 없습니다.

## 설계 기준과 원칙

단일 기준선: [AI_Accounting_Office_v0.2.3_통합설계_구현보강](https://drive.google.com/drive/folders/17FO3EYPA64MItPL-_RQbgg1NhKr4I5mn).
이전 설계 버전으로 fallback하지 않습니다. [설계 추적과 모듈 경계](docs/architecture.md)를 함께 참고하세요.

- **Relational-First**: 업무 데이터는 명시적 table/column/FK/constraint로 표현합니다. 초기 업무 PostgreSQL **JSON/JSONB column은 0개**이며 이번 범위는 테이블 자체를 만들지 않습니다. 예외는 별도 ADR이 필요합니다.
- **정본 분리**: accounting은 회계 장부, tax는 세무 계산·신고, evidence는 증빙/provenance, jobs/agents/tool executions는 실행 이력을 소유합니다.
- **Agent 경계**: Agent → Tool Registry → Tool Adapter → Application Service → Domain/Repository. Agent는 ORM/Session/SQL/Repository에 직접 접근하지 않습니다.
- **Deterministic calculation**: 금액·세금·잔액·집계는 Decimal, Domain Rule, Application Service와 결정적 query/calculation이 소유합니다. LLM이 계산하지 않습니다.
- **Human approval**: Posting, Period Close/Reopen, Tax Filing, Payment 확정은 사람의 승인과 Application Command 경계를 통과해야 합니다.

## 저장소 구조

```text
backend/app/     FastAPI 및 독립적인 업무 모듈 경계
backend/app/contracts/       ORM에 의존하지 않는 오류·UoW·Repository 계약
backend/app/core/database/  SQLAlchemy persistence primitive
backend/migrations/         Alembic 환경과 비업무 baseline
backend/tests/              unit, PostgreSQL integration, contract, golden
frontend/src/   app, features, shared
infra/          PostgreSQL/Redis Docker Compose
scripts/        플랫폼 공통 개발 진입점
docs/           설계 추적, 환경변수, 검증 기록
.github/        backend/frontend 품질 CI
```

## 준비 사항

- Python 3.14 권장 (패키지 최소 버전 3.12; 현재 CI/검증은 3.14)
- Node.js 24 LTS, npm 11
- Docker Engine/Desktop 및 Compose v2 (`--wait` 지원), Git
- Windows는 Docker Desktop의 Linux 컨테이너 모드를 사용합니다.

명령은 별도 표시가 없으면 저장소 루트에서 실행합니다. Windows PowerShell에서 `npm` 실행 정책 문제가 있으면 `npm.cmd`를 사용하세요.

## 환경 설정

```sh
python scripts/dev.py env
```

루트 `.env.example`을 `.env`로 복사하며 기존 `.env`는 덮어쓰지 않습니다. 파일의 값은 로컬 placeholder입니다. 실제 운영 비밀번호를 사용하거나 커밋하지 마세요. `.env`는 Git에서 제외됩니다.

[환경변수 계약](docs/environment.md)에 필수값, validation, URL/포트 동기화와 로그 정책을 설명합니다.

## PostgreSQL / Redis

```sh
python scripts/dev.py infra-start
# 또는
docker compose --env-file .env -f infra/docker-compose.yml config --quiet
docker compose --env-file .env -f infra/docker-compose.yml up -d --wait
docker compose --env-file .env -f infra/docker-compose.yml ps
```

두 컨테이너가 `healthy`여야 합니다. 공개 포트는 localhost에만 바인딩됩니다. PostgreSQL 기본 5432, Redis 기본 6379입니다. 충돌하면 `.env`의 `POSTGRES_PORT`/`REDIS_PORT`와 `POSTGRES_URL`/`REDIS_URL`을 함께 수정하세요. 예: PostgreSQL 5433.

```sh
python scripts/dev.py infra-stop
# 또는
docker compose --env-file .env -f infra/docker-compose.yml down
```

named volume은 유지합니다. `down -v`는 데이터를 삭제하므로 일상적인 종료에 사용하지 마세요. 이미 초기화된 PostgreSQL volume의 사용자/비밀번호는 환경변수 수정만으로 변경되지 않습니다.

## Backend

```sh
cd backend
python -m venv .venv
```

가상환경 활성화:

```powershell
# Windows PowerShell
.venv/Scripts/Activate.ps1
```

```sh
# Unix
. .venv/bin/activate
```

활성화 후 두 플랫폼에서 동일한 명령:

```sh
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
cd ..
python scripts/dev.py backend-run
```

기본 `http://127.0.0.1:8000`에서 실행합니다. 포트 충돌 시 `.env`의 `BACKEND_PORT=8100`처럼 변경하세요. 실제 기동 검증에서는 8100을 사용했습니다. `/docs`와 `/openapi.json`에서 메타데이터와 계약을 확인할 수 있습니다.

```sh
curl http://localhost:8000/health
```

기대 응답: HTTP 200, `{"status":"ok"}`. 변경한 포트를 사용하세요. PowerShell에서는 `curl.exe` 또는 `Invoke-RestMethod`를 사용할 수 있습니다.

`/health`는 **liveness**입니다. DB/Redis 연결이나 업무 데이터 존재를 검사하지 않습니다. 시작 시 필수 설정은 검증하지만 실제 DB 연결은 시도하지 않으므로 의존 서비스가 내려가도 앱은 시작합니다. DB Foundation도 이 계약을 유지합니다. DB 연결은 migration 또는 명시적인 persistence 사용 시 수행하며 실패는 안전한 공통 오류로 변환합니다. import 시 DB side effect나 자동 schema 생성은 없습니다.

## Frontend

```sh
cd frontend
npm ci
npm run dev
```

`http://localhost:3000`에서 최소 셸을 확인합니다. 포트 충돌 시 `npm run dev -- --port 3100`을 사용하고 backend의 `FRONTEND_ORIGIN`도 수정하세요. 첫 화면은 backend에 요청하지 않으므로 backend 없이 개발·빌드할 수 있습니다.

`NEXT_PUBLIC_API_ORIGIN`은 향후 브라우저 API transport를 위한 예약값입니다. 현재 소비하는 코드가 없으며 Next.js는 frontend의 `.env.local`을 읽습니다. 필요해지는 시점에 루트 예제의 공개값만 복사하고 비밀값을 `NEXT_PUBLIC_*`에 넣지 마세요.

## 품질 검사

활성화된 Python 가상환경에서:

```sh
cd backend
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy app
```

```sh
cd frontend
npm ci
npm run lint
npm run typecheck
npm run build
```

GitHub Actions가 backend/frontend를 독립 검증하고, 별도 PostgreSQL 17 service job에서 migration 및 schema/transaction/type integration을 필수 실행합니다. DB 없이 실행하는 pytest에서는 integration만 명시적으로 skip됩니다. Compose 설정도 별도 검사합니다. 이번 검증 기록은 [DB Foundation 검증](docs/database-verification.md), 기존 실행 기반 기록은 [Skeleton 검증](docs/verification.md)을 참고하세요.

## Migration과 PostgreSQL 통합 검사

가상환경을 활성화하고 backend에서 실행합니다. Alembic은 기존 typed settings의 `POSTGRES_URL`을 읽습니다.

```sh
cd backend
python -m alembic current
python -m alembic upgrade head
python -m alembic current --check-heads
python -m alembic check
```

현재 head는 `db_foundation`이며 업무 DDL은 없습니다. `alembic_version`은 migration 상태를 위한 내부 테이블입니다. 이후 업무 migration 번호는 v0.2.3의 `59_Complete_DDL_Migration_Map`을 따릅니다.

통합 검사는 개발 DB와 분리된, 이름이 `_test`로 끝나는 PostgreSQL DB가 필요합니다. 예제 로컬 계정을 그대로 사용하는 경우 루트에서 한 번 생성합니다.

```sh
docker compose --env-file .env -f infra/docker-compose.yml exec -T postgres psql -U accounting_local -d postgres -c "CREATE DATABASE accounting_foundation_test;"
```

이미 있으면 다시 만들지 마세요. 계정과 포트는 자신의 `.env`에 맞추세요. backend에서 테스트 주소를 설정합니다.

```powershell
$env:TEST_POSTGRES_URL='postgresql://accounting_local:local_placeholder_change_me@localhost:5432/accounting_foundation_test'
```

```sh
# Unix
export TEST_POSTGRES_URL='postgresql://accounting_local:local_placeholder_change_me@localhost:5432/accounting_foundation_test'
```

```sh
python -m pytest --require-postgres
```

`--require-postgres`는 설정 누락을 실패로 처리합니다. 테스트는 전용 DB의 migration 상태를 초기화하고 복구하므로 공유·개발·운영 DB를 지정하지 마세요. 업무 테이블을 발견하면 삭제하지 않고 중단합니다. [DB 구조와 정책](docs/database-foundation.md)에 lifecycle, 타입, 오류 및 schema guard를 설명합니다.

## 제외 범위와 다음 구현

users/tenants/companies/memberships, 인증/RBAC, 회계·세무·증빙 업무, Approval/Audit, Agent workflow, LLM, 실제 업무 Tool, Idempotency persistence, Excel Import는 미구현입니다. Kafka/vector DB/pgvector와 기존 프로젝트 Domain 코드도 포함하지 않습니다.

다음 범위는 v0.2.3 기준 **Identity/Company**입니다. users/refresh_sessions/security events, tenants/companies, roles/permissions, memberships/invitations, auth/session/RBAC와 active company context를 후속으로 구현합니다.

## 주석과 사용자 안내 문구

직접 작성하는 코드 주석과 docstring은 한글로 작성합니다. 도구가 자동 생성하는 파일과 타입 지시문은 생성 도구의 형식을 유지합니다.

사용자가 읽는 화면·API 메시지는 쉬운 한글로 작성하고, 필요한 경우 다음 행동을 안내합니다. 초기 화면에는 내부 개발 단계명이나 설계 버전을 표시하지 않습니다. 오류 원문이나 내부 구현 정보를 사용자 안내에 넣지 않습니다. API 필드명·오류 코드·환경변수명처럼 프로그램 간 계약에 해당하는 식별자는 유지합니다.
