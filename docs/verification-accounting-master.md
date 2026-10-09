# 회계 마스터 검증 기록

검증일: 2026-10-10 (Asia/Seoul). 시작 main: `3200d58212af939cfc880de7bcb0288dd5cfe042`.
브랜치: `feat/accounting-master`. 설계: **AI_Accounting_Office_v0.2.3_통합설계_구현보강**, 이전 버전 fallback 없음.

환경: Windows PowerShell, Python 3.14.2, Node.js 24/npm 11, PostgreSQL 17-alpine, Redis 7-alpine. 개발 volume과 분리한 `accounting_master_test`를 사용했습니다. 실제 credential은 저장하거나 출력하지 않았고 아래 접속 정보는 로컬 테스트 placeholder입니다.

## 최종 로컬 결과

| 명령·검사 | 결과 |
| --- | --- |
| python -m pytest | 81 passed, 70 skipped, 경고 1건. TEST_POSTGRES_URL 미설정 기본 실행 |
| python -m pytest --require-postgres | **151 passed, 실패·skip 0**, 경고 1건 |
| python -m ruff check . | 통과 |
| python -m ruff format --check . | 177개 파일 형식 통과 |
| python -m mypy app | 142개 소스 통과 |
| python -m pip check | No broken requirements found |
| python -m alembic current | 003_master_accounting_settings (head) |
| python -m alembic upgrade head | 성공, 재실행 성공 |
| python -m alembic current --check-heads | 현재 head 일치 |
| python -m alembic check | No new upgrade operations detected |
| 빈 DB→head / 002→003→002→003 / base 왕복 | 전용 DB integration lifecycle 통과 |
| PostgreSQL public JSON column | **0개** |
| PostgreSQL public JSONB column | **0개** |
| 29개 FK의 실제 데이터 대조 | **orphan row 0개** |
| 검증되지 않은 PostgreSQL FK | 0개 |
| npm ci | 성공, 124개 패키지 감사, 취약점 0개 |
| npm run lint | 통과, warning 0 |
| npm run typecheck | next typegen/TypeScript 통과 |
| npm test | 회사 전환/검색 테스트 2 passed |
| npm run build | Next.js 프로덕션 빌드 통과 |
| docker compose --env-file .env -f infra/docker-compose.yml config --quiet | 통과 |
| docker compose --env-file .env -f infra/docker-compose.yml up -d --wait | 성공 |
| docker compose --env-file .env -f infra/docker-compose.yml ps | PostgreSQL/Redis healthy |
| 실제 FastAPI GET /health | HTTP 200, {"status":"ok"} |
| git diff --check | 통과 |

실제 서버는 `python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8002 --no-access-log`로 실행해 상태 계약을 확인했습니다. 프론트엔드 화면의 브라우저 수동 상호작용 테스트는 수행하지 않았습니다. UI는 lint/type/build와 기존 회사 전환 테스트, backend 연결 계약은 실제 API integration으로 검증했습니다.

## 테스트 내용

- 기존 Identity/Company 인증·세션 회전·재사용 탐지·RBAC·초대 및 DB Foundation UUID/Decimal/UTC 회귀 유지.
- 초기화·시드 반복, 회사 COA 25개/월별 기간 12개, 1·4·7·12월 회계연도 시작, 정책 값 거부와 NEVER 리셋 정책.
- 거래처 사업자번호 정규화, 동일 회사 중복 거부·타 회사 허용, 외부 회사 지급조건/거래처/계정/기간 접근 거부.
- 설정/거래처/역할 expected_version, stale update 409, 역할 유효기간 겹침/잘못된 기간 거부.
- 종류별 주 연락처·주소 중복, 원계좌번호 입력, 잘못된 계정 방향, 기간 overlap, 중복 account code/version CHECK 거부.
- OWNER/ADMIN/ACCOUNTANT/REVIEWER/VIEWER permission 행렬, 임의 query 거부, revoked membership 404, 민감 식별자 마스킹과 은행 토큰 응답·로그 제외.
- 8개 실제 PostgreSQL 동시 연결이 중복 없이 1~8 할당, 롤백된 증가 후 9 성공, 회사·연도·키 독립 증가.
- Golden GOLDEN_CORP_001/CUSTOMER_A/SUPPLIER_B. T001/T004와 Opening Journal은 미생성.
- Domain/Application ORM/FastAPI 금지, Agent/LLM DB 접근 금지, Repository commit 금지와 company-scoped get 정적 계약.

신규 Master에서 legacy 식별자 store_id/sim_run_id/analysis_run_id/VOC/농산물, get_by_id, session.commit, Float, JSONB 저장 타입 검색 결과는 0건입니다. generic metadata/extra/options/payload/context DB column은 스키마 검사에서 0건입니다. 기존 .env는 ignored이며 변경 커밋에 포함되지 않았습니다.

## 경고와 후속 사항

기존 Starlette TestClient의 httpx 사용 중단 경고 1건이 유지됩니다. 테스트 실패는 없으며 httpx2 전환은 프로젝트의 테스트 클라이언트 호환성을 별도로 확인한 뒤 진행해야 합니다. PostgreSQL 통합 테스트의 skip은 기본 실행에서만 허용하고 CI는 --require-postgres를 사용합니다.

실제 vault 연결, 거래처 병합, 정책 재설정 command, Close/Reopen, Posting, Opening Balance 및 다음 Intake/Transaction은 이 범위에 포함하지 않았습니다. GitHub Actions 결과는 PR Checks에서 확인할 수 있습니다.
