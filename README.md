# AI Accounting Office

회계 장부와 세무 계산·신고 정본을 분리하고, AI의 제안을 결정적 검증과 사람의 승인으로 연결하는 서비스입니다.

현재 구현 범위는 **Repository Skeleton**입니다. FastAPI, Next.js + TypeScript, PostgreSQL/Redis 로컬 의존성, 품질 검사와 CI만 제공합니다. 업무 데이터와 인증은 아직 없습니다.

## 설계 기준과 원칙

단일 기준선: [AI_Accounting_Office_v0.2.2_통합설계_구현명세](https://drive.google.com/drive/folders/1bJVY8fPsIw3iEaMeQZQJEsOjWpV5fMQ8).
이전 설계 버전으로 fallback하지 않습니다. [설계 추적과 모듈 경계](docs/architecture.md)를 함께 참고하세요.

- **Relational-First**: 업무 데이터는 명시적 table/column/FK/constraint로 표현합니다. 초기 업무 PostgreSQL **JSON/JSONB column은 0개**이며 이번 범위는 테이블 자체를 만들지 않습니다. 예외는 별도 ADR이 필요합니다.
- **정본 분리**: accounting은 회계 장부, tax는 세무 계산·신고, evidence는 증빙/provenance, jobs/agents/tool executions는 실행 이력을 소유합니다.
- **Agent 경계**: Agent → Tool Registry → Tool Adapter → Application Service → Domain/Repository. Agent는 ORM/Session/SQL/Repository에 직접 접근하지 않습니다.
- **Deterministic calculation**: 금액·세금·잔액·집계는 Decimal, Domain Rule, Application Service와 결정적 query/calculation이 소유합니다. LLM이 계산하지 않습니다.
- **Human approval**: Posting, Period Close/Reopen, Tax Filing, Payment 확정은 사람의 승인과 Application Command 경계를 통과해야 합니다.

## 저장소 구조

```text
backend/app/     FastAPI 및 독립적인 업무 모듈 경계
backend/tests/   unit, integration, contract, golden
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

`/health`는 **liveness**입니다. DB/Redis 연결이나 업무 데이터 존재를 검사하지 않습니다. 시작 시 필수 설정은 검증하지만 실제 DB 연결은 시도하지 않으므로 의존 서비스가 내려가도 앱은 시작합니다. DB readiness 정책은 DB Foundation에서 정합니다. import 시 DB side effect나 자동 schema 생성은 없습니다.

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

GitHub Actions가 동일한 명령으로 backend/frontend를 독립 검증합니다. 업무 integration이 없으므로 DB service container를 띄우지 않습니다. Compose 설정도 별도 검사합니다. 실제 실행 기록은 [검증 문서](docs/verification.md)를 참고하세요.

## 제외 범위와 다음 구현

users/tenants/companies/memberships, 인증/RBAC, 회계·세무·증빙 업무, Approval/Audit, Agent workflow, LLM, 실제 업무 Tool, Idempotency persistence, Excel Import, Alembic migration은 미구현입니다. Kafka/vector DB/pgvector와 기존 프로젝트 Domain 코드도 포함하지 않습니다.

다음 설계 범위는 **DB Foundation**입니다. SQLAlchemy/Alembic, UUID/Decimal convention, Unit of Work, base repository, error base 및 JSON/JSONB column 금지 migration/schema test를 후속으로 구현합니다. 이번 저장소는 이를 선행 구현하지 않습니다.
