# Identity / Company 검증 기록

검증일: 2026-10-10 (Asia/Seoul). 기준 main은 `db0df108f17c3e5a562e8c3d17bc65b30d620f95`이며 작업 종료 전 다시 fetch하여 동일함을 확인했습니다. 브랜치는 `feat/identity-company`입니다.

## 실행 결과

| 실행 명령 | 결과 |
| --- | --- |
| `python -m pytest` (TEST_POSTGRES_URL 미설정) | 72 passed, 44 skipped, warning 1; DB 검사를 성공으로 간주하지 않고 명시적 skip |
| `python -m pytest --require-postgres` | **116 passed, skip 0, warning 1** |
| `python -m ruff check .` | 통과 |
| `python -m ruff format --check .` | 114 files formatted |
| `python -m mypy app` | 85 source files, 오류 0 |
| `python -m alembic current` | 002_tenant_company_rbac (head) |
| `python -m alembic upgrade head` | 통과, 재실행도 통과 |
| `python -m alembic current --check-heads` | 통과 |
| `python -m alembic check` | No new upgrade operations detected |
| `python -m app.companies.infrastructure.seed` 연속 2회 | 통과, 역할 8개/permission 48개 중복 없음 |
| `python -m pip check` | No broken requirements found |
| migration lifecycle integration | empty → head, 재적용, foundation까지 downgrade → 001 → head, base downgrade → head 통과; metadata diff 0 |
| `npm ci` | 통과, 124 packages audited, 취약점 0 |
| `npm run lint` / `npm run typecheck` | 통과 |
| `npm test` | 2 passed, 실패/skip 0 |
| `npm run build` | production build 통과 |
| `docker compose --env-file .env -f infra/docker-compose.yml config --quiet` | 통과 |
| `docker compose --env-file .env -f infra/docker-compose.yml up -d --wait` | 통과 |
| `docker compose --env-file .env -f infra/docker-compose.yml ps` | PostgreSQL/Redis 모두 healthy |
| HTTP GET /health | 실제 서버에서 200, `{"status":"ok"}` |
| HTTP GET /openapi.json | 200, health 포함 12개 path 계약 생성 |
| `git diff --check` | 통과 |

Windows PowerShell, Python 3.14.2, Node 24, PostgreSQL 17-alpine, Redis 7-alpine 환경입니다. PostgreSQL 포트 5433, 런타임 API 검증은 기존 포트 충돌을 피해 18765, 브라우저는 localhost:3000을 사용했습니다. 별도 `accounting_identity_test` DB만 migration lifecycle/데이터 검사에 사용했고 브라우저 테스트 계정·회사와 테스트 seed는 검사 후 정리했습니다. 개발 DB와 volume은 삭제하지 않았습니다.

## 실제 PostgreSQL 결과

관리 schema `public`에서 조회했습니다.

- 업무 테이블: 10개; 내부 alembic_version: 1개.
- JSON column: **0개**, JSONB column: **0개**, ARRAY column: **0개**.
- FK별 child/parent outer join으로 계산한 orphan FK row: **0개**.
- catalog constraint: CHECK 20, FK 14, PK 11, UNIQUE 6. 활성 초대 중복은 별도 partial UNIQUE index로 차단합니다.
- migration head: `002_tenant_company_rbac`, metadata diff 0.

## 인증·회사·보안 증거

실제 PostgreSQL 기반 서비스/API 테스트가 가입/중복 이메일/로그인 실패/비활성·폐기 사용자, 잘못된 입력과 token, rotation, hash/JTI 불일치, 만료/폐기/재사용, 가족 추적·폐기, logout/logout-all을 검증합니다. 서로 다른 실제 DB 연결의 동시 refresh는 한 번의 회전과 reuse 가족 폐기를 확인하며 이력이 남습니다.

회사 생성+OWNER membership, accessible list, 8종 role의 수정 권한, optimistic version 충돌, 다른 회사/미존재 404, 같은 회사 권한 부족 403, membership 폐기, DB permission 변경 즉시 반영, 생성 중 FK 오류의 전체 rollback을 검사했습니다.

초대 생성/활성 중복/유효 수락/다른 이메일/만료/재사용/회사 scope 폐기, ADMIN의 OWNER 초대 금지, 폐기 membership 복원 금지를 검사했습니다. Argon2 password hash와 refresh hash 저장, 원문 password/access/refresh/invitation token 로그 미포함, CSRF·Origin 및 로그인 제한도 자동 검사합니다. 인증 이벤트는 명시적 관계형 필드이며 범용 JSON payload가 없습니다.

실제 브라우저에서 가입 → 빈 회사 안내 → 회사 생성 → 1개 회사 자동 선택 → 새로고침으로 세션 복구 → 두 번째 회사 생성 → 선택 완료 후 활성 회사 표시를 확인했습니다. frontend 단위 테스트는 회사 전환 및 사용자 변경 뒤 늦게 도착한 응답 폐기와 UUID를 유지한 이름 검색을 검증합니다.

기존 architecture guard가 Domain/Application/contracts의 framework/ORM 의존, Agent/LLM의 DB 직접 접근과 Repository transaction ownership을 검사합니다. 정적 검색에서 과거 프로젝트 식별자와 신규 Repository 독립 commit은 0건입니다. 기존 UoW 내부 commit은 허용된 transaction 소유자입니다. `.env`는 tracked file이 아니며 실제 secret을 커밋하지 않았습니다.

## 발견 및 해결

추가 rollback 테스트의 예상 응답을 409로 작성했으나 기존 FK 오류 계약은 422 BUSINESS_RULE_VIOLATION이었습니다. 기존 공통 계약에 맞춰 테스트를 수정한 뒤 전체 116개 검사를 다시 통과했습니다.

남은 warning 1건은 기존 FastAPI/Starlette TestClient의 httpx 전환 deprecation입니다. 테스트 실패나 운영 API warning은 아니며 의존성 정비 범위에서 httpx2 호환을 검토해야 합니다. 이번 작업에서 잠금 파일을 임의로 광범위 업그레이드하지 않았습니다.

운영 인증 이메일 검증/비밀번호 복구/초대 이메일 전달/서명 키 rotation과 edge rate limit은 별도 운영 또는 후속 범위입니다. Web Locks 미지원 환경의 여러 탭 동시 refresh는 보수적으로 가족이 폐기되어 재로그인이 필요할 수 있습니다. 다음 업무 범위는 Accounting Master이며 선행 구현하지 않았습니다.
