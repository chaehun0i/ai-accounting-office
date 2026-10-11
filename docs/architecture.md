# 현재 구조와 기술 경계

단일 설계 기준은 [AI_Accounting_Office_v0.2.6_통합설계_정본](https://drive.google.com/drive/folders/14f9qJtr7eKzC12n8GpdHcNc3Ff2nyYpf)입니다. 활성 문서만 사용하며 이전 버전 fallback은 없습니다. 이전 구현별 검증 문서는 당시 이력이며 현재 구현 상태의 정본은 이 문서와 README입니다.

## 실제 구현

Identity/Company/RBAC, 회계 Master, Storage/Evidence/Intake, Onboarding/Data Exchange, Transaction/Journal/Approval/Posting/Reversal/GL/TB, Governance 및 Finance Subledger가 구현되어 있습니다. Finance는 채권·채무·수금·지급·배분·Aging·GL 대사를 소유합니다. 실제 은행 이체·Tax·Asset/Inventory·Closing 전체는 구현하지 않았습니다.

이번 P0 Runtime은 기존 거래에서 Tool 조회 → 구조화 계정 제안 → 결정론적 검증 → 사람 응답 대기 → 전표 **초안** 전달을 수행합니다. 실제 Gemini 호출은 선택 사항이며 기본 공급자는 Fake입니다. 전체 Chat UI나 자율 회계 승인은 제공하지 않습니다.

기본 의존 방향은 `API → Application → Domain`입니다. Infrastructure가 계약을 구현하고 UoW가 transaction을 소유합니다. Repository는 commit하지 않습니다. Domain/Application은 ORM·FastAPI·Provider SDK에 의존하지 않습니다.

## Agent 기술 경계

`Agent Graph → Canonical Tool Registry → Tool Adapter → Application Service → Domain/Repository`

| 기술 | 소유 책임 | 허용 import 위치 |
| --- | --- | --- |
| Gemini 공식 SDK | 구조화된 분류·계정 선택 | `llm/providers` |
| LangGraph | 노드·분기·interrupt·checkpoint·resume | `agents/graphs`, `agents/runtime`, `agents/checkpoints` |
| langchain-core | 동일 Registry의 Tool 변환 및 실행 설정 타입 | `tools/adapters/langchain.py`, `agents/runtime` |
| MCP 공식 SDK | 동일 Registry의 로컬 외부 호스트 연결 | `tools/adapters/mcp*` |
| FastAPI Application | 권한·회사·업무 검증 및 명령 | 기존 Application Service |

Graph는 Session·Repository·SQL에 접근하지 않습니다. `agents/checkpoints`의 psycopg 연결은 공식 framework 체크포인트 전용 예외이며 업무 쿼리에 사용하지 않습니다. Tool Adapter에는 SQL이나 Repository import가 없습니다. Principal·company는 서버가 주입하며 모델 입력으로 받지 않습니다.

Registry 한 곳이 이름·버전·설명·permission·class·side effect·timeout·Pydantic 입출력 schema를 소유합니다. Internal/LangChain/MCP Adapter가 별도 Tool 정의를 만들지 않습니다. `journal.post`, `period.close/reopen`, `payment.execute`, `tax.filing.submit`, arbitrary SQL은 등록할 수 없습니다.

Human Interrupt의 CONTINUE는 Graph 진행 허용입니다. Accounting APPROVED와 다릅니다. 기존 JournalCommands가 DRAFT를 만들고, 이후 제출·별도 사용자 승인·Posting은 기존 회계 흐름을 따라야 합니다. 숫자는 Transaction의 Decimal 금액에서만 구성합니다.

## 데이터베이스

기존 `db_foundation → 001_identity → … → 009_finance_subledger` 이력을 수정하지 않고 `010_agent_runtime_foundation`을 추가했습니다. 설계 migration map의 target 순서와 이미 배포된 번호는 구분하며, 이번 다음 사용 가능한 forward revision을 사용했습니다.

제품 실행 정본은 `jobs`, `agent_runs`, `agent_steps`, `tool_executions`, `job_events`입니다. 업무 스키마는 JSON/JSONB 0을 유지합니다. 실행 이력에는 digest·오류 코드·상태·resource FK를 기록하며 prompt·provider response·전체 Tool payload는 저장하지 않습니다. Tool Execution과 Job Event는 DB trigger로 append-only입니다.

ADR-035에 따라 공식 PostgresSaver가 `agent_checkpoints`에 자체 migration/table을 설치합니다. `checkpoints.checkpoint`, `checkpoints.metadata`의 JSONB만 허용합니다. 나머지 blob table은 공식 실행 직렬화이며 Accounting/Finance 정본으로 조회하지 않습니다. 체크포인트와 감사의 보존·백업은 운영에서 함께 관리해야 합니다.

`assert_relational_schema`는 업무 정책을, `assert_framework_schema`는 공식 table/column/JSONB 허용 목록을 검사합니다. `scripts/verify_accounting_schema.py`는 실제 테이블/FK/orphan/JSON 수치를 출력합니다. 실측 결과는 [Agent 검증 기록](agent-runtime-verification.md)에 기록합니다.

010과 공식 checkpoint 설치 후 전용 PostgreSQL 실측은 업무 테이블 **67**, 업무 FK **163**, orphan **0**, 업무 JSON **0**·JSONB **0**입니다. 별도 framework는 공식 테이블 4개와 허용된 JSONB 2개이며 업무 테이블 수에 더하지 않습니다. 기존 009 상태는 업무 테이블 62개였습니다.

## 검증과 현재 한계

AST guard가 Domain/Application의 프레임워크 의존, SDK 위치, Agent DB 우회, Repository transaction 소유 및 Graph의 고위험 명령을 검사합니다. 이는 Python sandbox가 아니며 실행 시 Registry allowlist·회사·RBAC와 기존 Domain 불변식을 함께 적용합니다.

현재 실행은 API 요청 안에서 제한된 Graph를 수행합니다. PostgreSQL lease·heartbeat·thread lock과 동일 시작 키 재시도·명시적 resume으로 복구하며, 상시 queue 소비 worker·취소·운영 스케줄러는 다음 범위입니다. SSE는 DB 이력 replay이며 지속 연결 fanout은 아닙니다. 자세한 API와 제한은 [Agent Runtime](agent-runtime.md)을 참고하세요.
