# 거래·전표·원장·시산표

설계 기준은 `AI_Accounting_Office_v0.2.5_통합설계_정본`이다. 문서 지도, 릴리즈 게이트, 회계코어, 물리 DDL, migration map, API, 상태전이, 승인/RBAC, 오류·동시성, Golden 및 Coverage 문서를 직접 확인했다. 이전 버전 fallback은 사용하지 않았다. 시작 main은 `42368174ae85db110e9e2043d784e736d62544f1`이다.

## 사용자 흐름

거래는 경제적 사건이며 전표와 별도 정본이다. 회사별 거래를 입력하고 그 거래를 출처로 전표를 작성한다. 전표 작성자는 분개를 입력한 뒤 제출하고 승인을 요청한다. 별도 검토자가 승인하면 장부 반영 권한자가 확정한다. 작성자 본인의 승인은 서버에서 거부한다.

`DRAFT → PROPOSED → REVIEW_REQUIRED → APPROVED → POSTED` 순서를 명시적인 Command로 처리한다. 일반 PATCH로 상태를 변경할 수 없다. 반려는 `REJECTED`로 보존하며 자동 승인은 제공하지 않는다. 확정된 원 전표의 상태는 역분개 후에도 `POSTED`이다. 역분개는 차대변을 교환한 새 초안이며 독립된 승인·확정이 필요하다.

## 관계형 구조

- `006_transactions`: transactions 및 회사·거래처·Import·Evidence 출처 FK.
- `007_journal_core`: journal_entries, journal_lines, journal_evidences, journal_proposals, opening_balance_imports, opening_balance_lines.
- `008_governance`: approvals, audit_events, idempotency_records 및 승인 FK, 확정 불변성과 감사 append-only trigger.

현재 사람 작성 Proposal은 전표 초안을 참조하고 동일한 관계형 분개·증빙을 사용한다. Agent용 제안 분개, confidence, agent_run FK는 아직 만들지 않는다. 향후 Agent Proposal은 별도 승인 전 데이터 구조로 확장하며 확정 Journal을 덮어쓰지 않는다.

Application/UoW가 트랜잭션을 소유한다. Repository는 flush만 수행한다. 금액은 Decimal/NUMERIC(19,4), 시간은 TIMESTAMPTZ, 식별자는 UUID다. JSON/JSONB, 가변 payload 또는 balance 정본 테이블을 추가하지 않는다.

## 승인과 확정

승인은 대상 전표의 회사, 버전, 회계 의미 digest, 만료 시각, 요청자와 검토자를 보존한다. 확정 시 검토자의 현재 활성 사용자·멤버십·승인 권한을 다시 검사한다. 승인 후 변경되거나 만료된 대상은 확정할 수 없다.

확정은 회사·전표·기간·계정을 잠그고 차대변, 최소 2개 분개, 활성 posting 계정, OPEN 기간, 승인, expected_version을 검사한다. 기존 Journal Sequence를 같은 UoW에서 증가시키고 전표번호·확정·승인 소비·감사·멱등성 receipt를 함께 저장한다. 중간 실패는 번호와 승인 소비까지 rollback한다.

각 분개는 차변 양수/대변 0 또는 대변 양수/차변 0이며 음수와 양쪽 금액 입력은 거부한다. 초안은 불균형 상태로 저장할 수 있지만 제출 이후는 정확히 Debit=Credit이어야 한다. POSTED 헤더·분개·증빙 연결은 API와 DB trigger 모두 수정·삭제를 차단한다.

## 원장과 시산표

POSTED Journal Lines만 조회한다. 원장은 시작일 이전 잔액을 포함하여 일자·전표번호·분개 순번 순으로 누적하며 계정의 normal balance 방향으로 표시한다. 시산표는 기초 차변/대변, 기간 차변/대변, 기말 차변/대변을 계산하고 각각의 전체 차대변 일치를 검사한다. 현재는 미결산 시산표이며 결산·재무제표를 구현하지 않는다.

화면의 합계는 BigInt 기반 소수점 네 자리 단위로 계산한다. 최종 회계 판단은 서버 Decimal 검증이다. 조회 결과를 사용자가 수정하거나 장부 계산에서 Draft를 포함시키지 않는다.

## 기초잔액

온보딩의 저장된 Opening_Balances를 회사의 기존 계정·거래처 코드와 정확히 연결한다. 단일 기준일과 차대변 균형을 검사하고 입력 버전·행 키·금액·계정의 관계형 스냅샷과 OPENING 전표 초안을 같은 UoW에서 만든다. 원천 typed cell digest와 Import Evidence 출처를 보존한다.

잔액 컬럼을 직접 UPDATE하거나 즉시 POSTED 전표를 생성하지 않는다. 생성된 기초 전표도 사람의 제출·승인·확정 흐름을 거쳐야 한다. 회계 Master가 아직 준비되지 않았다면 먼저 기존 회계 Master Application 명령으로 준비한다. 미지원 Asset/Inventory/AR/AP 온보딩 승격 차단은 유지한다.

## 재시도와 회사 경계

전표 생성·상태 명령·기초 전표 생성은 `Idempotency-Key`를 받는다. 회사+사용자+명령+키와 fingerprint를 저장하고 같은 요청은 연결된 전표를 재조회한다. 다른 fingerprint는 conflict다. 전체 응답 JSON은 저장하지 않는다. Replay는 현재 resource 상태를 반환하므로 최초 응답의 불변 복사본은 아니다.

회사 scoped query와 복합 FK로 다른 회사의 계정·거래처·Import·Evidence 연결을 차단한다. 멤버십이 없는 회사와 다른 회사 resource는 404, 같은 회사 권한 부족은 403이다. JWT 역할 claim을 정본으로 사용하지 않는다.

동일 Transaction을 출처로 한 POSTED 전표는 회사별 부분 unique index로 하나만 허용한다. Transaction 연결 후에는 거래 원천의 수정도 차단하며, 제출 이후 전표 합계가 연결 거래의 금액과 일치해야 한다. 거래·전표 목록에는 회사+일자 복합 index가 있다. 기초 전표는 온보딩 session별 하나만 생성하여 관련 없는 Draft 버전 변경으로 중복 생성되지 않게 한다.

## 공식 샘플과 Reference

native Google Sheet `AI_Accounting_Office_SAMPLE_COMPANY_2025`를 다시 확인했다. 기존 macro 없는 `sample-company-2025-v1.xlsx`와 명시적으로 버전 관리된 파생 온보딩 fixture를 사용한다. 원본 SHA-256은 `c4df64f12fc517b73f1ef0c164bdeb541c1039a6c43d8ee3971310b414761d02`이며 조용히 수정하지 않는다. 기초잔액 차변·대변은 각각 280,000,000원이다. 세무 source fact를 신고 정답으로 사용하지 않는다.

이번 회계 엔진은 NEW다. 과거 프로젝트 코드를 COPY/ADAPT하지 않았다. 기존 저장소의 UoW·권한 검사·Sequence·온보딩 typed value·Evidence 구조를 재사용했다. nobadai/mainproject 등의 업종·시뮬레이션 코드는 참고 필요가 없어 가져오지 않았다.

## API

`/transactions`, `/journals`의 조회·작성과 초안 수정, `/journals/{id}/submit`, `request-review`, `approve`, `reject`, `post`, `reverse`, `/opening-balances/imports`, `/ledger`, `/trial-balance`를 제공한다. 회사는 `X-Company-ID`, 인증은 기존 Bearer 계약, 변경 명령은 CSRF 보호를 사용한다. 날짜·UUID·Decimal·enum은 typed contract이고 command extra 입력은 거부한다.

## 후속 경계

Tax 정본, Asset/Inventory/AR/AP 전체, 결산·재무제표, Period 재개방, Agent/LLM은 제외한다. 후속 Domain은 POSTED Journal FK와 회사 scope를 사용하고 수정은 별도 correction/reversal 명령으로 연결한다. Opening snapshot 자체는 원장 계산에 포함하지 않는다.

현재 Import Receipt는 접수 정본이며 자동 Transaction promotion worker는 제공하지 않는다. 사용자가 거래에 같은 회사의 Import/Evidence를 연결할 수 있다. 반려된 전표를 다시 편집하는 상태 전이는 열지 않았으며 새 초안을 작성한다. 원장·시산표는 조회 시 계산하고, 거래·전표 목록은 날짜 범위에서 최대 500개다. 대량 조회의 cursor pagination과 projection은 후속 성능 측정 후 도입한다.

현재 전표 작성 화면은 일반 회계 분개를 작성하며 세무 판단을 생성하지 않는다. 정상 거래를 여러 전표로 분할 인식하거나 복수 통화를 사용하는 기능은 지원하지 않는다. 별도 회계정책 없이 이를 허용하지 않는다.

## 검증 재현

일반 품질 명령은 README를 따른다. 실제 PostgreSQL 통합 검증은 이름이 `_test`로 끝나는 비어 있는 전용 DB의 `TEST_POSTGRES_URL`이 필요하다. migration lifecycle 테스트는 그 DB의 업무 테이블이 비어 있는지 확인한 뒤 downgrade/upgrade하며, 개발 DB에 실행하지 않는다. 동시 확정 테스트는 별도의 일회성 `_test` DB를 생성하므로 테스트 계정에 CREATEDB 권한이 필요하다.

브라우저 스크립트는 `scripts/accounting-browser-smoke.cjs`다. 별도 테스트 DB에 연결된 backend와 frontend를 각각 8001/3001에서 실행한다. backend의 `FRONTEND_ORIGIN=http://127.0.0.1:3001`, frontend의 `BACKEND_API_ORIGIN=http://127.0.0.1:8001`을 맞추고 RBAC/COA seed를 준비한다. Playwright를 설치한 Node 환경에서 실행하거나 `PLAYWRIGHT_MODULE_PATH`에 Playwright가 설치된 `node_modules` 경로를 지정한다. 기본 브라우저는 Edge이며 `BROWSER_CHANNEL`로 변경한다. `--allow-synthetic`은 합성 사용자·회사 생성의 명시적 실행 옵션이다. 서버 URL은 `ACCOUNTING_API_ORIGIN`과 `ACCOUNTING_BROWSER_ORIGIN`으로 바꿀 수 있다. 이 스크립트는 전용 테스트 환경에 합성 회사·확정 전표를 남긴다.

DB 실측 스크립트 `scripts/verify_accounting_schema.py`는 조회만 수행하며 프로젝트 public schema의 모델·테이블 일치, JSON/JSONB 0, 실제 FK 수와 고아 참조 0을 검사한다. CI의 PostgreSQL job에서도 같은 스크립트를 실행한다.
