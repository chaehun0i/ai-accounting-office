# Agent Runtime 검증 기록

2026-10-11, 시작 main `1f3cd8fb5d1511b0f8f3f169a854e1059f7cef2d`, 작업 branch `feat/p0-agent-runtime-foundation`에서 실행했습니다. 설계는 v0.2.6, fallback은 없습니다. 서로 다른 실행의 passed 수를 더하지 않습니다.

## PostgreSQL E2E

`python -m pytest --require-postgres tests/integration/test_agent_runtime.py tests/integration/test_agent_tools.py -q -x --tb=short` 실행은 **12 passed, 1 warning**입니다. 별도 생성한 `_test` DB를 사용했고 종료 시 해당 DB만 제거했습니다. 개발 DB의 사용자·회사·기존 업무 데이터는 제거하지 않았습니다.

- 실제 회사·회계 담당자·Transaction을 생성하고 Bookkeeper API를 시작했습니다.
- Registry가 실제 Transaction/Evidence/계정 검색/Application 검증을 호출했습니다.
- Fake Provider의 구조화된 제안은 Controller REVIEW가 되어 Human Interrupt에 도달했습니다.
- pending_action과 PostgreSQL checkpoint를 조회했습니다. 별도 Python 프로세스에서도 같은 checkpoint를 읽었습니다.
- Gateway/Graph/checkpointer 객체를 재구성하고 API resume으로 같은 실행을 계속했습니다.
- 원천 `100.0000`과 차변·대변 금액이 같고 결과는 DRAFT였습니다. 승인·Posting은 발생하지 않았습니다. 대기 시에는 Journal 자체가 생성되지 않았습니다.
- 실제 Tool 실행 6회와 노드·이벤트 이력을 확인했습니다. 조회 Tool 9개는 별도로 Internal/LangChain Adapter에서 실제 Application으로 호출했습니다.
- 공식 MCP SDK client/server 메모리 전송으로 initialize/list_tools/call_tool을 실행했습니다. Registry schema와 같고 금지된 journal.post는 거부했습니다.
- 다른 회사·없는 원천·OWNER 작성 권한, extra 회사 argument, stale version, 원천 변경, 닫힌 기간, 잘못된 계정·증빙·추가 금액을 차단했습니다.
- REJECT는 전표 없이 종료했습니다. 감사 삭제 trigger와 framework allowlist 오염 거부도 검증했습니다.

새 프로세스 테스트는 checkpoint 조회를, 재구성 Runtime 테스트는 실제 resume을 각각 수행합니다. 별도 상시 worker 프로세스를 배포했다는 의미는 아닙니다.

## Migration과 스키마

전용 `accounting_agent_verify_test`에서 다음을 실행하고 DB를 제거했습니다.

1. 빈 DB → `alembic upgrade 009_finance_subledger` → `upgrade head`.
2. `alembic current --check-heads` → `010_agent_runtime_foundation`.
3. `alembic check` → No new upgrade operations detected.
4. `downgrade 009_finance_subledger` → `upgrade head` → `alembic check` 통과.
5. 공식 PostgresSaver.setup() → `python scripts/verify_accounting_schema.py`.

| 실제 조회 항목 | 결과 |
| --- | ---: |
| public 업무 table (alembic_version 제외) | 67 |
| public FK | 163 |
| orphan rows | 0 |
| public JSON | 0 |
| public JSONB | 0 |
| framework JSON | 0 |
| framework JSONB | 2 |

새 업무 table은 jobs/agent_runs/agent_steps/tool_executions/job_events입니다. framework table 4개는 공식 checkpoint_migrations/checkpoints/checkpoint_blobs/checkpoint_writes입니다. JSONB 예외는 checkpoints.checkpoint/metadata뿐입니다. 기존 009와 그 이전 migration은 변경하지 않았습니다. 운영 downgrade는 지원 절차로 사용하지 않습니다.

## Frontend와 실행 환경

최종 코드의 PostgreSQL 환경변수 없는 `python -m pytest -q`는 **199 passed, 138 skipped, 1 warning**입니다. skip은 PostgreSQL 연결을 요구하는 137개와 opt-in Gemini 1개이며 아래 실제 PostgreSQL 실행과 구분합니다. `ruff check .`, `ruff format --check .`(403 files), `mypy app`(317 source files), `pip check`가 통과했습니다.

`npm ci`는 통과했고 audit 0 vulnerabilities였습니다. `npm run lint`, `npm run typecheck`, `npm test`(**25 passed**), `npm run build`가 통과했습니다. 이번 PR에는 Chat 화면 변경이 없습니다.

`docker compose --env-file .env -f infra/docker-compose.yml config --quiet`와 `up -d --build --wait`를 실행했습니다. Python 3.14 Linux 이미지에 lock을 설치했고 frontend/backend/PostgreSQL/Redis가 healthy였습니다. `/health`는 `{"status":"ok"}`였습니다. 컨테이너의 `pip check`도 통과했습니다.

## 경고와 제한

초기 Windows 전체 회귀는 329 passed / 1 failed였고, 실패는 새 `httpx2` logger의 초대 URL capability 노출이었습니다. 기존 마스킹을 httpx2/httpcore2까지 확장하고 transport 단위 회귀를 추가했습니다. 이 초기 실행을 전체 성공으로 기록하지 않습니다. 최종 재검증 결과는 별도 실행 단위로 기록합니다.

수정 전에 시작된 Linux 실행도 331 passed / 1 failed / 1 skipped로 같은 로그 문제를 확인했습니다. 수정 후 로그 보안과 Agent 전체 PostgreSQL 집중 재실행은 **13 passed, 1 warning**이며, 검증과 저장 사이 source version 변경을 강제로 만들어 rollback까지 확인했습니다. 원본 Golden fixture나 회계 expected 값은 변경하지 않았습니다.

Google SDK import에서 Python 3.14의 `_UnionGenericAlias` 사용에 관한 DeprecationWarning 1개가 나타납니다. 테스트 실패는 아니며 upstream 교체를 추적해야 합니다. Docker build에는 일반적인 root pip 설치 경고가 있었고 실행 사용자는 기존 비특권 office 계정입니다.

Gemini 실 네트워크 호출은 하지 않았습니다. 별도 `gemini` marker와 `RUN_GEMINI_INTEGRATION=1` opt-in을 제공하며 일반 CI는 skip합니다. Fake 검증을 실 Gemini 성공으로 주장하지 않습니다.

상시 queue worker·운영 scheduler·취소·지속 SSE fanout·외부 MCP OAuth·전체 Chat UI는 제외했습니다. Tool timeout은 강제 중단이 아닌 완료 후 예산 검사이며 Gemini SDK에는 HTTP timeout을 적용합니다. 자세한 경계는 [Runtime 계약](../platform/agent-runtime.md)을 따릅니다.

## 최종 PostgreSQL 전체 회귀

최종 기능 코드 `fd517c2`와 동일한 파일을 Linux Python 3.14 컨테이너에 읽기 전용으로 연결하고, 별도 `accounting_agent_final_test`에서 `python -m pytest tests --require-postgres -q -p no:cacheprovider --tb=short`를 실행했습니다. 결과는 **336 passed, 1 skipped, 1 warning, 743.95초**입니다. 종료 후 이 테스트 DB만 제거했습니다.

Accounting/Finance/연간 샘플회사 Golden, Posting/Reversal·자기승인 금지·회사 격리·멱등성 및 Agent/MCP 회귀가 이 실행에 포함됩니다. 기존 Golden의 AR 5,500,000 / AP 1,650,000과 Trial Balance 차변·대변 각각 62,650,000을 변경하지 않고 통과했습니다. skip 1개는 opt-in Gemini 실 호출이고 warning 1개는 위에 기록한 Google SDK의 Python 3.14 deprecation입니다. 서로 다른 실행 결과를 합산한 수치가 아닙니다.
