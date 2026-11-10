# 회계 Agent 비교 재무제표 검토

AI 회계팀에서 당기와 비교 전기를 선택해 비교 검토를 실행한다. 기존 Tool Registry가 회사 권한과 typed input을 검증하고 ComparativeStatementsService의 readiness를 호출한다. LLM과 Repository 직접 접근은 사용하지 않는다.

검토 결과는 READY/BLOCKED 판정, 원천 digest, 차단 사유를 보존한다. RuntimeAudit의 기존 Run/Step/ToolExecution 및 Idempotency 경계를 재사용한다. 동일 key와 요청은 기존 Run을 반환하며 다른 요청은 충돌한다. 원천이 바뀔 수 있으므로 검토 결과는 조회 시점 기준이다.

이 Workflow는 READ 전용이다. 생성·재분류·검토 요청·독립 승인은 재무제표 화면에서 수행하며 기존 서비스가 권한, 작성자 분리, expected_version, 현재 원천과 승인 digest를 검증한다. Agent에게 승인 권한을 부여하지 않는다. 승인 대기 상태를 Agent 검토 성공으로 가장하지 않는다.

API: POST /agent/queries/comparison-review. period_id, comparison_period_id와 Idempotency-Key, 회사 scope, CSRF가 필요하다. 기존 run/steps/events API에서 이력을 조회한다. 모든 결과는 INTERNAL_VALIDATION_ONLY이다.

지원 범위는 기존 비교 서비스와 같은 BS/IS이다. CF/SCE/Notes 비교, 변경성 Tool, 자동 생성·승인·Posting은 지원하지 않는다. Tool 실패는 FAILED로 기록하며 회계 상태를 변경하지 않는다. 사용자는 기존 재무제표 화면에서 직접 검토를 계속할 수 있다.
