# 현재 구조와 기술 경계

단일 설계 기준은 [AI_Accounting_Office_v0.2.6_통합설계_정본](https://drive.google.com/drive/folders/14f9qJtr7eKzC12n8GpdHcNc3Ff2nyYpf)입니다. 활성 문서만 사용하며 이전 버전 fallback은 없습니다. 이전 구현별 검증 문서는 당시 이력이며 현재 구현 상태의 정본은 이 문서와 README입니다.

## 실제 구현

Identity/Company/RBAC, 회계 Master, Storage/Evidence/Intake, Onboarding/Data Exchange, Transaction/Journal/Approval/Posting/Reversal/GL/TB, Governance, Finance Subledger, Business Document, Bank/Card Reconciliation 및 Closing V1이 구현되어 있습니다. Finance는 채권·채무·수금·지급·배분·Aging·GL 대사를 소유합니다. 실제 은행 이체·Tax·Asset/Inventory·BS/IS는 구현하지 않았습니다.

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

011 적용 후 전용 PostgreSQL 업무 schema 실측은 업무 테이블 **70**, 업무 FK **170**, orphan **0**, 업무 JSON **0**·JSONB **0**입니다. 별도 framework checkpointer를 설치하면 공식 테이블 4개와 허용된 JSONB 2개를 사용하며 업무 테이블 수에 더하지 않습니다. 통합 테스트 정리 후 스키마 검증 시 framework JSON/JSONB는 0개였습니다. 기존 009 상태는 업무 테이블 62개였습니다.

## 검증과 현재 한계

AST guard가 Domain/Application의 프레임워크 의존, SDK 위치, Agent DB 우회, Repository transaction 소유 및 Graph의 고위험 명령을 검사합니다. 이는 Python sandbox가 아니며 실행 시 Registry allowlist·회사·RBAC와 기존 Domain 불변식을 함께 적용합니다.

현재 실행은 API 요청 안에서 제한된 Graph를 수행합니다. PostgreSQL lease·heartbeat·thread lock과 동일 시작 키 재시도·명시적 resume으로 복구하며, 상시 queue 소비 worker·취소·운영 스케줄러는 다음 범위입니다. SSE는 DB 이력 replay이며 지속 연결 fanout은 아닙니다. 자세한 API와 제한은 [Agent Runtime](agent-runtime.md)을 참고하세요.

## 회사 관리차원

`011_accounting_dimensions`는 기존 003/007 이력을 보존하는 forward revision입니다. `accounting_dimensions`, `accounting_dimension_values`, `journal_line_dimensions`를 추가하고 회사·분석축 composite FK와 분개별 유형 UNIQUE를 적용합니다. `accounting/dimensions`의 Domain/Application/Infrastructure/API 경계를 따르며 기존 Journal 검증·Posting transaction 안에서 활성/기간/필수정책을 재검증합니다. POSTED 연결 변경은 DB trigger로도 차단합니다.

원장에는 선택적 관리항목 EXISTS 필터만 추가합니다. 기본 GL/TB와 AR/AP 대사는 동일 Accounting 정본을 유지합니다. Agent Tool은 추가하지 않았고 framework checkpoint schema도 변경하지 않았습니다. [관리차원 계약](accounting-dimensions.md)에 적용 결정과 샘플 정합성, 재사용 판정을 기록합니다.

## 확정 가져오기 거래 승격

`012_import_transaction_promotion`은 `intake/promotion`의 명시적 Application 경계를 추가합니다. 기존 Confirm은 파일 해석·사용자 확인인 CONFIRMED, 별도 Promote는 Transaction 생성 후 COMPLETED입니다. Promotion이 기존 Transaction Application의 `save_in`을 같은 UoW에서 호출하므로 전체 행·영수증·typed 재시도 기록이 함께 rollback됩니다. Transaction ORM을 직접 쓰거나 Journal을 자동 생성하지 않습니다.

`import_promotion_rows`는 원본 행을 복제하지 않고 locator·digest·거래 FK·review를 보존합니다. `import_promotion_commands`는 company/actor/command/key/fingerprint와 Receipt 참조만 저장합니다. 요청·Import·원천 identity 잠금과 기존 Transaction UNIQUE가 동시 재시도를 보호합니다. 회사·Receipt/Transaction composite FK가 다른 회사 참조를 차단합니다. Agent mutation Tool과 framework checkpoint 예외는 변경하지 않았습니다. API·상태·재사용·실측 검증은 [승격 계약](import-transaction-promotion.md)을 따릅니다.

012 적용 후 전용 PostgreSQL 실측은 업무 테이블 **72**, 업무 FK **176**, orphan **0**, 업무 JSON **0**·JSONB **0**입니다. 위 011 수치는 이전 revision의 기록이며 당시 head는 012이며 아래 014가 현재 head입니다.


## 매출·매입 업무문서

`finance/invoices`는 Invoice와 Credit/Debit Note를 거래·전표·보조부와 분리합니다. `013_business_documents`는 8개 관계형 테이블과 기존 AR/AP의 Invoice 원천 FK를 추가합니다. 문서 승인 명령은 같은 UoW의 명시적 Transaction/Obligation Application 계약을 호출합니다. Router/Repository가 다른 Domain ORM을 직접 써서 업무를 우회하지 않습니다. Infrastructure의 조회와 FK 연결만 기존 model을 참조합니다.

문서는 DRAFT→REVIEW_REQUIRED→APPROVED, 정정문서는 승인과 함께 APPLIED입니다. 작성자 자기승인을 차단하고 승인된 문서/항목은 DB trigger로 불변입니다. 정산과 정정은 append-only fact로 잔액을 계산하며 원금/기존 Collection·Payment를 덮어쓰지 않습니다. 전표가 없는 Invoice 원천은 업무 보조부에 보이고, 원장 대사 불일치는 별도로 반환합니다. 기존 POSTED Journal을 연결하면 동일 채권채무에 참조를 붙입니다. 자동 Posting은 없습니다.

013의 격리 PostgreSQL 실측은 업무 테이블 **80**, FK **215**, orphan **0**, 업무 JSON **0**, JSONB **0**입니다. 012 이하 이력과 LangGraph framework schema는 변경하지 않았습니다. [업무문서 계약](business-documents.md), [검증 결과](business-documents-verification.md)를 참고하세요. 이 수치는 013 시점의 기록이며 은행·카드는 아래 014에서 확장합니다.


## 은행·카드 원천 대사

`014_bank_card_reconciliation`은 기존 009의 match/line 구조를 재사용하고 은행·카드 계좌/원천/명세와 policy/item/event 8개 테이블을 추가합니다. 기존 013 이하 migration을 변경하지 않았습니다. 014 시점 전용 PostgreSQL 실측은 업무 테이블 **88**, FK **250**, 인덱스 **495**, CHECK **232**, orphan **0**, 업무 JSON **0**, JSONB **0**입니다. Framework checkpoint schema는 변경하지 않았습니다.

`finance/banking`은 확정 Intake의 원본 digest/Receipt/version을 다시 검증해 source를 정규화합니다. `finance/reconciliation`의 기존 AR/AP 원장 조회는 유지하고 별도 명시적 BankReconciliationService를 확장합니다. 회사 transaction lock 안에서 source/target 잔여액과 후보 version을 재검증합니다. 동시 초과 대사와 stale 후보를 차단하고 typed event/line 이력을 보존합니다. Router는 Application만 호출하고 Repository는 commit하지 않습니다.

은행 명세와 GL, 확정 source 잔액을 구분합니다. 카드매출 정산채권과 법인카드 미지급금은 명시적 통제계정 role/usage로 분리합니다. 대사는 Journal 생성·승인·Posting 권한을 갖지 않으며 차이를 자동 조정하지 않습니다. Agent Tool/Framework는 확장하지 않았습니다. `blocker` summary는 Closing V1 검사 입력으로 사용합니다.

PR #14 병합 기준 main은 `f1915db34688e6dc41b46f0db08ef8a843e41520`입니다. [은행·카드 계약](bank-card-reconciliation.md)을 참고하세요.

## 월마감 V1

`015_period_closing`은 이미 배포된 014 이하 이력을 수정하지 않는 순방향 revision입니다. 회계기간에 `CLOSING`과 `close_version`을 추가하고 결산 실행·검사·조정·승인·감사 이벤트·멱등 명령을 관계형 테이블에 기록합니다. 활성 실행은 회사·기간별로 유일하며 검사 재실행은 기존 행을 지우지 않고 버전별 이력을 추가합니다.

`closing` Application은 기존 총계정원장/시산표, AR/AP 원장 대사, 은행/카드 대사의 계산 결과를 조합합니다. 미처리 거래, 미승인 전표, 금융 미대사, AR/AP 차이, 시산표 불균형, 필수 조정을 BLOCKER로 판정하고 컷오프 날짜 차이는 WARNING으로 보입니다. 계산 입력의 digest가 달라진 실행은 재검사 전에는 마감할 수 없습니다. Asset/Inventory/Cost/Tax 미구현 상태는 서비스업 기본 월마감의 차단 사유로 만들지 않습니다.

결산조정은 기존 Journal 초안·독립 승인·Posting을 통과합니다. 일반 전표는 CLOSING 기간에 신규 작성하거나 기표할 수 없습니다. 최종 마감과 재개는 요청자와 다른 활성 권한자의 승인을 요구하고, 기간 상태·마감 버전·실행 상태·감사 이벤트를 하나의 작업단위로 변경합니다. 자동 역분개 대상은 다음 열린 기간의 기존 Reversal 명령으로 초안을 생성한 후 동일한 사람 승인 절차를 따릅니다. CLOSED 장부의 수정이나 GL 직접 쓰기는 없습니다.

명시적인 `UNADJUSTED`/`ADJUSTED` 시산표 조회와 장부·대사 digest는 후속 BS/IS의 입력 경계입니다. 월별 손익 계정을 물리적으로 0으로 만드는 연말 마감은 포함하지 않았습니다. [월마감 계약](period-closing.md)과 [검증 기록](period-closing-verification.md)을 참고하세요.
