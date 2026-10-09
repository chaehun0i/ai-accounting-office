# 실행 검증 기록

이 문서는 PR #1 Repository Skeleton의 당시 검증 기록입니다. 최신 DB Foundation 결과는 [별도 검증 기록](database-verification.md)을 참고하세요.

검증 환경: Windows, Python 3.14.2, Node.js 24.12.0, npm 11.6.2, Docker Desktop Linux Engine 29.5.3.
원격 main을 fetch/pull하여 `e7282bc481dd17782b577613e13acbb41392f605`와 README만 있는 상태를 확인했습니다. 기존 PR은 없었습니다. 작업은 `feat/repository-skeleton`에서 수행했습니다.

## Backend

backend 디렉터리, 설치된 가상환경에서 실행했습니다.

| 명령 | 결과 |
| --- | --- |
| python -m pip install -r requirements-dev.lock / python -m pip install --no-deps -e . | 설치 성공; 최초 설치는 pyproject의 dev extra로 수행 후 설치 버전을 잠금 |
| python -m pip check | No broken requirements found |
| python -m pytest -q | 23 passed; Starlette TestClient의 httpx 사용 deprecation warning 1개 |
| python -m ruff check . | 통과 |
| python -m ruff format --check . | 26 files already formatted |
| python -m mypy app | Success: no issues found in 22 source files |
| 루트에서 python -m ruff check scripts/dev.py | 통과 |
| 루트에서 python -m ruff format --check scripts/dev.py | 통과 |
| python scripts/dev.py backend-run | 8100 포트에서 시작 성공 |
| curl.exe --fail --silent --show-error -i http://127.0.0.1:8100/health | HTTP 200, {"status":"ok"} |

테스트는 health 계약/OpenAPI/app 생성/설정 parsing·누락·오류/명시적 CORS/안전한 오류 응답/request ID/Agent import 경계를 포함합니다. 실제 DB/Redis 없이 수행합니다.

## Infrastructure

루트 `.env`의 로컬 override: PostgreSQL 5433, backend 8100. 실제 credential은 사용하지 않았습니다.

| 명령 | 결과 |
| --- | --- |
| docker compose --env-file .env -f infra/docker-compose.yml config --quiet | 통과 |
| docker compose --env-file .env -f infra/docker-compose.yml up -d --wait | 통과 |
| docker compose --env-file .env -f infra/docker-compose.yml ps | PostgreSQL/Redis 모두 healthy |
| PostgreSQL information_schema.tables, public schema count | 0 |
| PostgreSQL information_schema.columns, public JSON/JSONB count | 0 |
| docker compose --env-file .env -f infra/docker-compose.yml exec -T redis redis-cli ping | PONG |

## Frontend

frontend 디렉터리에서 실행했습니다. NEXT_TELEMETRY_DISABLED=1로 빌드했습니다.

| 명령 | 결과 |
| --- | --- |
| npm ci --no-fund | 123 packages 설치, 124 packages audit, 성공 |
| npm run lint | ESLint 권장/TypeScript 권장 규칙, warning 0, 성공 |
| npm run typecheck | next typegen + tsc --noEmit, 성공 |
| npm run build | Next.js 16.4.0 Turbopack production build 성공; /, /_not-found 정적 생성 |
| npm audit --audit-level=low | found 0 vulnerabilities |

프론트엔드 빌드 과정에서 backend/DB/Redis를 호출하지 않습니다.

## 정적 검토

`rg`로 backend/app, infra, docs에서 JSON/JSONB를 검색했습니다. API JSONResponse와 정책 문서 외 DB 저장형식 구현은 없습니다. backend/infra/docs의 과거 프로젝트 식별자 검색은 0건입니다. ORM/model/repository/SQL/migration/create_all 및 기존 Domain 이식이 없습니다. Kafka/vector DB/pgvector도 없습니다.

`.env`, `.venv`, node_modules, `.local`은 gitignore됩니다. 버전 관리 대상에는 로컬 placeholder인 `.env.example`만 포함합니다. debug=false, 단일 origin CORS, 고정 오류 메시지와 생성된 request ID를 사용합니다. git diff --check를 수행합니다.

## 초기 실패와 해결

- Git 소유권 검증 및 `.git` 쓰기 제한: 해당 저장소에 한정한 safe.directory 옵션과 승인된 Git 실행으로 해결. 전역 Git 설정은 변경하지 않았습니다.
- Python 가상환경 pip 초기화: sandbox 임시 경로 쓰기 실패를 저장소 내부 `.local/tmp`로 우회했습니다. 의존성 다운로드는 승인된 네트워크 실행으로 완료했습니다.
- 초기 Ruff 포맷/길이 오류: 포맷 후 검사 통과했습니다.
- 기존 서비스가 backend 8000 및 PostgreSQL 5432를 사용 중: 기존 서비스를 유지하고 새 로컬 `.env`만 8100/5433으로 조정했습니다.
- 초기 eslint-config-next 간접 의존성에서 high 취약점 5개: 현재 셸에는 불필요한 설정 패키지를 제거하고 ESLint 10/TypeScript 권장 규칙으로 교체했습니다. 설치 트리 충돌은 빈 임시 경로에서 잠금 파일을 재계산해 해결했습니다.

## 남은 제한

Starlette TestClient의 httpx deprecation warning은 upstream 테스트 도구의 전환 대상으로 남아 있습니다. 테스트는 통과하며 warning을 숨기지 않았습니다.

현재 architecture guard는 정적 import 계약이며 runtime sandbox가 아닙니다. DB Foundation에서 실제 migration/schema guard를 추가하고, Agent runtime 범위에서 capability/side-effect 제한을 검증해야 합니다. 인증/승인/업무 기능은 아직 없으며 이번 완료 범위가 아닙니다.

## 주석과 안내 문구 후속 검증

직접 작성한 주석/docstring과 설정·로그 안내를 한글로 정리했습니다. 초기 화면의 개발 단계명·설계 버전을 제거하고 준비 상태를 쉬운 표현으로 안내합니다. API 오류는 사용자가 이해할 수 있는 한글 메시지를 사용하며 필드명·오류 코드·health status 계약은 유지합니다.

변경 후 pytest 23개, Ruff lint/format, mypy, frontend lint/typecheck/production build가 모두 통과했습니다. 개발 명령의 기존 .env 보존 안내도 확인했습니다. 자동 생성되는 next-env.d.ts와 라이브러리 자체 문구는 생성 도구가 관리합니다.
