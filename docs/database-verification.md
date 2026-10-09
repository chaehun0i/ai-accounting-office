# DB Foundation 검증 기록

검증일: 2026-10-09 (Asia/Seoul). 기준 main `f8125cd3e3fc724616eabf8142466c868fe12a82`, 작업 branch `feat/database-foundation`. 원격 fetch/pull 후 PR #1 병합과 열린 PR/Issue 없음을 확인했습니다.

설계 기준: **AI_Accounting_Office_v0.2.3_통합설계_구현보강**. 업무 모델·테이블·API는 추가하지 않았습니다.

## 실제 실행 결과

Windows PowerShell, Python 3.14.2, PostgreSQL 17 Alpine, Redis 7 Alpine, Node.js 24 환경에서 실행했습니다. backend 가상환경을 사용했으며 integration에는 개발 DB와 분리된 `accounting_foundation_test`를 사용했습니다. 로컬 PostgreSQL 포트는 5433입니다.

| 실행 위치 | 명령 | 결과 |
| --- | --- | --- |
| backend | python -m pip install -r requirements-dev.lock 및 editable install | 성공 |
| root | backend/.venv/Scripts/python -m pip check | 의존성 충돌 없음 |
| backend | python -m pytest --require-postgres --tb=short | **86 passed**, skip 0, 기존 upstream warning 1 |
| backend | python -m ruff check . | 성공 |
| backend | python -m ruff format --check . | 55 files already formatted |
| backend | python -m mypy app | 36 source files 성공 |
| backend | python -m alembic current | db_foundation (head) |
| backend | python -m alembic upgrade head | 성공, 재실행 성공 |
| backend | python -m alembic current --check-heads | db_foundation (head) |
| backend | python -m alembic downgrade base | 성공 |
| backend | python -m alembic upgrade head | 성공 |
| backend | python -m alembic check | No new upgrade operations detected |
| root | docker compose --env-file .env -f infra/docker-compose.yml config --quiet | 성공 |
| root | docker compose --env-file .env -f infra/docker-compose.yml up -d --wait | 성공 |
| root | docker compose --env-file .env -f infra/docker-compose.yml ps | PostgreSQL/Redis 모두 healthy |
| frontend | npm ci | 성공, audit 취약점 0 |
| frontend | npm run lint | 성공 |
| frontend | npm run typecheck | 성공 |
| frontend | npm run build | 성공, 정적 페이지 생성 |
| backend | python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8101 --no-access-log | 기동 성공 |
| root | Invoke-WebRequest http://127.0.0.1:8101/health | 200, {"status":"ok"} |
| root | Invoke-RestMethod http://127.0.0.1:8101/openapi.json | OpenAPI 생성 성공 |
| root | git diff --check | 성공 |
| root | git ls-files '*.env' '.env' | 추적된 실제 env 파일 없음 |
| root | rg -n 'sim_run_id|store_id|incident_id' backend infra docs | 과거 프로젝트 식별자 없음 |

최초 의존성 설치는 pyproject의 editable dev install 후 freeze로 기존 lock 방식을 유지했습니다. CI에서는 lock 설치 후 no-deps editable install을 사용합니다.

## PostgreSQL 및 migration 증거

migration integration은 empty public schema에서 시작하여 upgrade/re-upgrade/current/check/metadata 비교/downgrade/re-upgrade를 수행했습니다. 업무 테이블이 있으면 테스트가 중단하도록 보호합니다. 임시 테스트 테이블과 정책 위반 schema는 연결 종료 또는 rollback으로 제거합니다.

실제 전용 PostgreSQL에서 실행한 쿼리:

```sql
SELECT count(*) FILTER (WHERE data_type='json') AS json_columns,
       count(*) FILTER (WHERE data_type='jsonb') AS jsonb_columns
FROM information_schema.columns
WHERE table_schema='public';
```

결과: **json_columns=0, jsonb_columns=0**. public 테이블 목록은 `alembic_version` 1개이며 업무 테이블은 0개입니다. Base.metadata도 빈 상태이며 Alembic 비교 결과 차이가 없습니다.

schema guard는 별도 schema의 JSON/JSONB/domain wrapper/UUID ARRAY/JSONB ARRAY 위반을 탐지했습니다. 실패 메시지에 table/column/type이 포함되는 것을 확인했습니다. 관리 대상 public 외 schema와 system schema 처리를 검증했습니다.

## transaction·타입·보안

실제 PostgreSQL에서 연결, commit, rollback, UoW 정상 commit, body 예외 rollback, 명시적 commit/rollback 후 종료, deferred UNIQUE commit 실패 rollback을 검증했습니다. UUID/Decimal/aware datetime 왕복과 잘못된 Decimal의 안전한 오류 변환이 통과했습니다. unit 검사는 float/문자열 UUID/naive datetime 거부 및 precision/scale을 확인합니다.

기존 공통 API envelope로 DB 오류를 반환해 SQL·매개변수·credential 원문이 노출되지 않는 contract test가 통과했습니다. echo=false/hide_parameters=true와 import/factory 시 연결 없음도 검증했습니다. 실제 secret을 추가하지 않았으며 예제와 CI에는 로컬 전용 placeholder만 사용합니다.

Domain/Application/contracts → SQLAlchemy/FastAPI/DB infrastructure 금지, Agent/LLM → DB/Repository 금지, Repository → commit/rollback/begin 금지 정적 검사와 금지 예제들이 통과했습니다. 정적 검사는 runtime sandbox나 실제 RBAC의 대체물이 아닙니다.

## 발견한 문제와 한계

- Windows Alembic이 locale encoding으로 ini를 읽어 한글 주석을 해석하지 못하는 문제를 확인했습니다. ini를 ASCII 설정으로 유지하고 한글 설명을 문서/Python 주석에 두어 해결했습니다.
- PostgreSQL 테스트 DDL의 예약어 컬럼 이름을 수정한 뒤 전체 검증을 다시 통과했습니다.
- 제한된 실행 환경의 localhost 접근은 허용된 네트워크 실행으로 검증했습니다. 제품 코드 우회 설정은 추가하지 않았습니다.
- 기존 Starlette TestClient의 httpx deprecation warning 1개가 남습니다. 테스트 실패는 없으며 테스트 transport 의존성 전환은 후속 호환성 검토가 필요합니다.

CI는 backend unit/contract와 frontend 검증을 유지하고 별도 PostgreSQL service에서 online Alembic 및 `pytest tests/integration --require-postgres`를 수행합니다. 원격 실행 결과는 PR Checks에서 확인할 수 있습니다.
