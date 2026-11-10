# 회계 Agent 비교 재무제표 검토

AI 회계팀에서 당기와 비교 전기를 선택해 비교 검토를 실행한다. 기존 Tool Registry가 회사 권한과 typed input을 검증하고 ComparativeStatementsService의 readiness를 호출한다. LLM과 Repository 직접 접근은 사용하지 않는다.

검토 결과는 READY/BLOCKED 판정, 원천 digest, 차단 사유를 보존한다. RuntimeAudit의 기존 Run/Step/ToolExecution 및 Idempotency 경계를 재사용한다. 동일 key와 요청은 기존 Run을 반환하며 다른 요청은 충돌한다. 원천이 바뀔 수 있으므로 검토 결과는 조회 시점 기준이다.

이 Workflow는 READ 전용이다. 생성·재분류·검토 요청·독립 승인은 재무제표 화면에서 수행하며 기존 서비스가 권한, 작성자 분리, expected_version, 현재 원천과 승인 digest를 검증한다. Agent에게 승인 권한을 부여하지 않는다. 승인 대기 상태를 Agent 검토 성공으로 가장하지 않는다.

API: POST /agent/queries/comparison-review. period_id, comparison_period_id와 Idempotency-Key, 회사 scope, CSRF가 필요하다. 기존 run/steps/events API에서 이력을 조회한다. 모든 결과는 INTERNAL_VALIDATION_ONLY이다.

지원 범위는 기존 비교 서비스와 같은 BS/IS이다. CF/SCE/Notes 비교, 변경성 Tool, 자동 생성·승인·Posting은 지원하지 않는다. Tool 실패는 FAILED로 기록하며 회계 상태를 변경하지 않는다. 사용자는 기존 재무제표 화면에서 직접 검토를 계속할 수 있다.

## 구현 및 검증 기록

기준 main은 `e9033d8c0dea659911eb8f09a3c418456233eeaa`이며, 구현은 [Issue #120](https://github.com/chaehun0i/ai-accounting-office/issues/120)과 [PR #121](https://github.com/chaehun0i/ai-accounting-office/pull/121)에서 관리한다. 아래 수치는 기능 커밋 `d75d91ed3f73a840849f3a5ca5a6871645d997d1`의 검증 기록이다.

- 신규 비교 Tool 및 Registry 단위 검증: 7건 통과. READY/BLOCKED 보존, 회사 문맥 전달, 권한 거부 시 서비스 미호출, 임의 company 입력 거부를 확인했다.
- 기존 PostgreSQL 비교 업무 통합 테스트에 Agent 검토를 추가했다. 정상 완료, Application readiness와 원천 digest 일치, 동일 요청 replay, 같은 키의 다른 요청 충돌, Step 감사 기록과 후속 독립 승인·Export를 확인했다.
- [Quality CI 실행](https://github.com/chaehun0i/ai-accounting-office/actions/runs/42761010714)의 backend/frontend/PostgreSQL/infrastructure/scope가 모두 통과했다. backend Ruff·format·mypy 및 frontend lint·test·typecheck·build가 포함된다.
- 개발 PC에서는 TEST_POSTGRES_URL 부재로 PostgreSQL 테스트 1건이 skip됐다. PostgreSQL 통과 근거는 CI 실행이다.
- 전체 Golden, 연간 synthetic, 전체 PostgreSQL 회귀, 전체 브라우저 E2E는 실행하지 않았다.

이 검증은 변경성 Agent Action의 승인·동시 실행 검증을 뜻하지 않는다. 이번 Workflow에는 변경성 Tool이 없으며, 향후 추가 시 독립 승인·expected_version·원천 stale·중복 실행 계약을 별도로 검증해야 한다. #112와 #117의 전체 DoD 재감사 및 Issue 정리는 이번 변경에서 완료하지 않았다.

## 로컬 PostgreSQL 추가 검증

2026-11-10 기존 `ai-accounting-office-postgres-1` 컨테이너를 실행하고 개발 DB와 분리된 `agent_workflow_test` DB에서 검증했다. `127.0.0.1:5433`을 사용했으며 자격 증명은 기존 컨테이너 설정에서 실행 환경으로만 전달했다.

실행 범위: `test_comparative_statements.py`, `test_agent_reporting_tools.py`, `test_report_center.py`에 `--require-postgres -q` 적용. 결과는 **9 passed, 1 warning, 130.79초**, skip 0건이다. 경고는 Google GenAI 의존성의 Python 향후 버전 deprecation이며 테스트 실패는 없다. 앞의 로컬 DB 미실행 기록은 이 추가 검증 이전 상태다.
