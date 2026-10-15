# 거래 기반 회계 제안 실행

## 기준선과 역할

시작 main은 `1f3cd8fb5d1511b0f8f3f169a854e1059f7cef2d`이며 PR #8 Finance까지 병합된 상태에서 분기했습니다. 활성 SSOT는 v0.2.6이며 fallback은 없습니다. 문서 지도 이후 로드맵, ADR, Orchestrator, Tool/MCP, LLM Gateway, Job, Controller, Approval, Architecture, Physical DDL, Migration Map, Relational Policy, Permission, Error, DoD, Coverage, API를 직접 확인했습니다.

- [ADR-034/035와 버전 정책](https://docs.google.com/document/d/1xsS5QYqUqQP5s6SxMtCxCXrZvCso8AkGkrCAB3lfwKY/edit): Agent P0와 framework-owned checkpoint 예외.
- [Tool/MCP 계약](https://docs.google.com/document/d/1nx0Q25SMUi878wfEjzp3DJY3K25zJbnRTDs0veRksQ8/edit): 같은 Registry와 사용자 위임 권한.
- [LLM 안전 계약](https://docs.google.com/document/d/1nfhe1mh3b6BTKFUQ2fu-w9bgLx43lsthD7FN-TX3AfM/edit): Provider 격리·구조화 출력·Controller 재검증.
- [Job 계약](https://docs.google.com/document/d/1ECUir5VCs7BDg9lAemn7_-v7PpXXfZ29Afca6P1iefw/edit): 제품 실행 이력·상태·재연결.
- [API 계약](https://docs.google.com/document/d/1seqmSKIwjyWP5mKQYJt-RTG-e2XKbqAoIXxuGzUOWBw/edit): `/agent/runs` 경로를 사용합니다.

LangGraph는 실행 순서·분기·checkpoint·interrupt를, langchain-core는 동일 Tool 변환을, Gemini는 분류·계정 식별자 선택을 담당합니다. 업무 실행은 기존 Application Service가 소유합니다. Accounting/Finance Domain은 이 SDK를 import하지 않습니다. Google SDK 2.29.0, LangGraph 1.2.14, PostgreSQL checkpointer 3.1.2, langchain-core 1.6.9, MCP 2.3.0을 공식 package 정보로 확인하고 lock에 고정했습니다.

## 실제 실행 흐름

`load_transaction → load_evidence → classify_transaction → search_accounts → propose_journal → validate_proposal → controller`

Controller BLOCK은 종료합니다. REVIEW와 PASS는 모두 Human Interrupt에서 멈춥니다. 증빙이 없거나 분류가 OTHER이면 REVIEW이며, Fake는 정확한 회계 분류를 가장하지 않습니다. 존재하지 않는 계정·증빙, 같은 차대 계정, 닫힌 기간, 오래된 원천 version, schema 밖의 모델 금액은 차단합니다.

모델 출력 `AccountSelection`에는 계정 UUID와 증빙 UUID만 있습니다. 금액 필드가 없습니다. 두 분개 금액은 원천 Transaction의 Decimal로 만들고 기존 `validate_journal`로 회사·계정·활성·postable·기간·차대 균형을 검사합니다. 수식·세금·잔액을 LLM에게 계산시키지 않습니다.

CONTINUE에서도 원천 version·권한·기간을 다시 확인한 뒤 기존 JournalCommands로 DRAFT만 생성합니다. REJECT는 초안 없이 종료합니다. Graph 응답은 회계 승인이나 Posting이 아닙니다. 작성자 자기승인 금지·Period Lock·POSTED 불변성은 기존 명령 경계가 그대로 담당합니다.

검증 UoW와 저장 UoW 사이의 원천 변경도 막기 위해 기존 JournalCommands.create에 선택적 source_version을 전달합니다. 실제 source row lock 안에서 version을 다시 비교하며 기존 일반 전표 호출의 동작·fingerprint는 변경하지 않습니다.

## Canonical Tool

정의는 `app/tools/accounting.py`, 검증은 `ToolRegistry`가 소유합니다. 이름·설명·입출력 schema를 Adapter에서 다시 작성하지 않습니다.

| Tool | class | 권한 |
| --- | --- | --- |
| accounting.search_accounts | READ | account.read |
| accounting.get_transaction | READ | transaction.read |
| evidence.get_transaction_evidence | READ | evidence.read |
| accounting.get_ledger | READ | ledger.read |
| accounting.get_trial_balance | READ | trial_balance.read |
| finance.list_receivables | READ | receivable.read |
| finance.list_payables | READ | payable.read |
| finance.get_ar_reconciliation | READ | receivable.read |
| finance.get_ap_reconciliation | READ | payable.read |
| accounting.validate_journal | READ | journal.propose |
| accounting.propose_journal | PROPOSE | journal.propose |

응답은 Pydantic typed Result이며 as_of·warnings·evidence_refs를 포함합니다. Decimal은 문자열 직렬화로 정밀도를 보존합니다. 회사·Principal·permission·SQL·path·URL은 모델 argument로 받지 않습니다. 입력 extra는 거부합니다. 검색은 활성 postable 계정 최대 20개로 제한합니다. 합계·원장·시산표·대사는 기존 Application 계산 결과입니다.

금지 Tool은 `journal.post`, `period.close`, `period.reopen`, `payment.execute`, `tax.filing.submit`, `tax.rule.activate`, `arbitrary_db_query`입니다. COMMAND/EXTERNAL class도 이 Registry에서 등록하지 않습니다.

## API

인증 Bearer와 `X-Company-ID`가 필요합니다. 변경 요청은 기존 Origin/CSRF 정책을 적용합니다. 시작·재개는 `journal.propose`, 조회는 `journal.read`를 요구하며 Tool마다 세부 권한도 재검증합니다. OWNER라는 이유로 작성 권한을 넓히지 않습니다.

| 요청 | 내용 |
| --- | --- |
| POST /agent/runs/bookkeeper | `{transaction_id}`, Idempotency-Key 필수 |
| POST /agent/queries/bookkeeper | `{period_id, question}`, Idempotency-Key 필수. 마감 상태 또는 CLOSED 기간 BS/IS 조회 |
| GET /agent/runs/{id} | status/version/pending_action/controller_verdict/result_journal_id |
| GET /agent/runs/{id}/steps | 노드 실행과 안전한 오류 코드 |
| GET /agent/runs/{id}/events?after_seq=0 | 저장된 이벤트 순서 조회, 최대 1,000개 |
| GET /agent/runs/{id}/stream?after_seq=0 | 같은 DB 이벤트를 SSE 형식으로 replay |
| POST /agent/runs/{id}/resume | `{expected_version, decision: CONTINUE 또는 REJECT}` |

다른 회사 run/transaction은 404이며 실행 작성자만 resume할 수 있습니다. stale version은 409입니다. 클라이언트는 이전 event_seq 이후를 조회하여 복구합니다. SSE 전송 실패는 이미 저장된 Run에 영향을 주지 않습니다.

기간 질의는 `closing.readiness`와 `financial_statement.read` 두 읽기 Tool만 사용합니다. 전자는 Closing Application의 검사·차단 사유를 그대로 반환하며 `period.read` 권한을 요구합니다. 후자는 CLOSED 기간의 최신 BS/IS 스냅샷과 요청 항목의 계정·전표 출처를 Reporting Application에서 읽으며 `financial_statement.read` 권한을 요구합니다. Tool Registry가 회사 범위와 사용자 권한을 재검증하고 Controller가 답변의 금액·문구·resource·출처가 Tool 결과와 정확히 일치하는지 확인합니다. 마감·기표·승인 명령은 Agent에 노출하지 않습니다.

`/ai-team`은 회사와 회계기간을 선택해 위 기간 질의를 실행하는 최소 Workspace입니다. 차단 검사는 건수와 검사 코드·영향 금액을 Tool 결과 그대로 답변하며, Controller는 건수와 검사 목록의 불일치도 차단합니다. UI는 답변·Decimal 문자열 금액·검증 상태·resource/digest를 구분합니다. 회사 전환 시 이전 입력·응답을 폐기하며 대화 이력과 토큰 스트리밍은 저장·제공하지 않습니다.

거래 전표 제안 그래프는 `agents/graphs/bookkeeping.py`, 기간 질의 그래프는 `agents/graphs/accounting_question.py`에 둡니다. 두 그래프는 같은 Tool Registry와 Runtime 감사 경계를 사용합니다. 화면의 기간 조회·질의 재시도·run 조회 상태는 `ai-team/use-accounting-query.ts`가 소유하고 Workspace 컴포넌트는 결과 표시만 담당합니다.

## 영속성·복구

`010_agent_runtime_foundation`은 jobs/agent_runs/agent_steps/tool_executions/job_events와 빈 framework schema를 추가합니다. 기존 009 및 그 이전 migration은 수정하지 않았습니다. 공식 PostgresSaver.setup()이 별도 schema에 자체 table을 설치하며 동시 설치를 advisory lock으로 보호합니다. 같은 thread 실행도 PostgreSQL advisory lock으로 직렬화합니다.

`017_accounting_agent_queries`는 기존 `agent_runs`가 거래 UUID를 필수로 요구하던 제약을 확장해 기간 질의와 답변의 정형 열을 기록합니다. 기존 실행·단계·Tool 감사 테이블을 재사용하고 새 업무 테이블이나 JSON 컬럼은 추가하지 않습니다.

운영은 forward migration만 사용합니다. downgrade는 이번 격리 테스트 DB의 왕복 검증용이며 framework 실행 이력도 제거하므로 활성 실행이 있는 운영 DB에서 사용하지 않습니다.

시작 키는 회사·작성자 범위에서 unique이며 transaction/graph version fingerprint가 다르면 conflict입니다. 대기·완료 결과는 replay합니다. 실행 lease는 5분이고 Tool 시작마다 heartbeat를 갱신합니다. 중단된 실행은 lease 만료 후 같은 시작 키로 재시도하면 checkpoint부터 복구합니다. 최대 시도는 3회입니다. 사람 대기 상태는 명시적 resume으로 재개합니다. Gateway/Graph/checkpointer 객체를 모두 다시 만들어도 같은 thread를 사용합니다.

실행 UoW와 Tool 업무 UoW는 분리되어 짧게 끝납니다. LLM을 호출하는 동안 업무 row lock을 잡지 않습니다. 초안 생성은 run ID에 결합된 기존 회계 멱등 명령이며 재개 중 장애에도 중복 초안을 만들지 않습니다.

감사에는 input/output digest·permission 결정·latency·오류 코드와 run/source/result FK만 저장합니다. 전체 Tool payload·prompt·Provider response·파일 원문은 제품 DB/로그에 넣지 않습니다. Job Event와 Tool Execution은 append-only입니다. framework checkpoint에는 최소화된 원천 fact·계정 후보·제안 상태가 들어가며 Accounting/Finance/Tax 정본을 대체하지 않습니다.

## 로컬 MCP

backend 디렉터리에서 OS 환경의 `MCP_ACCESS_TOKEN`과 `MCP_COMPANY_ID`를 설정한 뒤 `python -m app.tools.adapters.mcp_stdio`를 실행합니다. 비밀번호/토큰을 명령 인수에 쓰거나 로그로 출력하지 마세요. 공개 HTTP 서버는 제공하지 않습니다.

요청마다 현재 access token을 인증하고 서버 회사 membership 및 Tool permission을 검증합니다. 목록은 허용 권한으로 필터링하며 실행도 다시 검증합니다. 같은 사용자·회사·Tool·입력의 PROPOSE는 같은 명령 ID를 사용하므로 연결 재생성에도 같은 초안을 재사용합니다. 읽기 resource는 현재 회사 활성 분개 계정 검색(최대 20개)입니다. 전체 COA snapshot으로 오해하지 마세요.

Internal Graph는 MCP 서버를 HTTP로 호출하지 않고 Registry를 직접 실행합니다. 외부 MCP는 동일 Registry를 공식 SDK protocol로 호출합니다. 외부 READ에는 AgentRun이 없으므로 AgentRun별 trace를 만들지 않으며 PROPOSE는 기존 회계 명령의 Governance audit를 남깁니다.

## 현재 한계와 제외 범위

실행은 동기 API 요청 기반이며 상시 queue worker, 취소, 주기적 복구 scheduler, live fanout은 없습니다. 네트워크가 끊기면 REST 상태와 저장 이벤트를 조회하세요. Tool timeout metadata는 완료 후 예산 초과를 검사하며 실행 중인 Python 함수를 강제 중단하지 않습니다. Gemini SDK에는 실제 HTTP timeout과 전체 재시도 예산을 적용합니다.

실 Gemini 네트워크 테스트는 키·모델을 제공한 별도 opt-in으로만 수행합니다. 일반 CI는 Fake이며 키가 없어도 Core/health가 동작합니다. Remote MCP OAuth/host별 서비스 인증, checkpoint retention/운영 role 분리, Chat UI, Closing/Tax/multi-agent/RAG/자율 Posting은 이번 범위가 아닙니다. 정적 import guard는 Python sandbox가 아닙니다.

실 Gemini 검증 명령은 `RUN_GEMINI_INTEGRATION=1`과 `GEMINI_API_KEY`, `GEMINI_MODEL`을 OS 환경에 지정한 후 `python -m pytest -m gemini tests/integration/test_gemini_live.py`입니다. 일반 실행은 skip하며 이번 검증에서 실 호출은 하지 않았습니다.
