# AI Accounting Office

[현재·과거 문서 읽기 안내](docs/README.md)를 먼저 확인하면 기능 계약과 당시 검증 기록을 구분할 수 있습니다.

회계 장부와 세무 계산·신고 정본을 분리하고, AI의 제안을 결정적 검증과 사람의 승인으로 연결하는 서비스입니다.

현재 구현 범위는 **Repository Skeleton + DB Foundation + Identity/Company + Accounting Master + Storage/Evidence/Intake + Onboarding/Data Exchange + Transaction/Journal/Ledger + Finance Subledger + Business Document + Bank/Card Reconciliation + Closing V1 + BS/IS Snapshot + Bookkeeper Agent 기간 질의와 AI 회계팀 화면**입니다. 직접입력 초안, Excel 충돌 병합, 검증/재계산, 지원 Domain의 원자적 승격을 제공합니다. [온보딩 구조](docs/onboarding-data-exchange.md), [검증 기록](docs/onboarding-verification.md), [약어 풀이](docs/abbreviations.md)를 참고하세요. 사용자·회사·권한·인증 세션과 회사별 거래처·지급조건·회계 설정·계정과목·기간·전표번호 기반과 CSV/XLSX 업로드·항목 연결·검증·미리보기·명시적 접수·증빙 출처·Receipt를 제공합니다. [파일·증빙·인테이크 구조](docs/storage-evidence-intake.md), [회계 마스터 구조와 API](docs/accounting-master.md), [인증·회사 구조](docs/identity-company.md)를 참고하세요.

**채권·채무** 메뉴에서 확정 전표 연결 → 수금·지급 등록 → 배분 → 확정 → 기준일 잔액·기한 분석·원장 대사를 사용할 수 있습니다. 수금·지급은 먼저 사람 승인과 장부 반영을 마친 회계 전표를 참조합니다. 실제 은행 이체 기능은 아닙니다. [재무 보조부 사용법과 경계](docs/finance-subledger.md), [검증 결과](docs/finance-verification.md)를 참고하세요.


**매출 · 매입 문서** 메뉴에서 청구서 작성 → 승인 요청 → 별도 담당자 확정 → 거래·채권채무 연결을 사용할 수 있습니다. 확정 문서는 직접 수정하지 않고 감액/증액 정정문서를 남깁니다. 문서 확정은 장부 Posting과 다르며 전표 승인 절차가 별도로 필요합니다. [업무문서 계약과 제한](docs/business-documents.md), [검증 기록](docs/business-documents-verification.md)을 참고하세요.

**은행 대사 · 카드 대사**에서 기존 CSV/XLSX 확인 자료를 금융 원천으로 연결하고 후보 검토 → 다중·부분 배분 → 사람 확정 → 사유 있는 해제 → 원천/장부 잔액 비교를 사용할 수 있습니다. 원번호 대신 별칭을 사용하며 카드매출 수납과 법인카드 비용을 구분합니다. 대사 차이를 자동 분개로 상쇄하지 않습니다. [은행·카드 계약과 제한](docs/bank-card-reconciliation.md)을 참고하세요.

**월마감**에서 기간을 `OPEN → CLOSING → CLOSED`로 전환하고 미처리 거래·미승인 전표·은행/카드 미대사·채권채무 원장 차이·시산표·필수 조정을 결정론적으로 검사합니다. 결산조정은 기존 전표 초안 → 별도 담당자 승인 → 기표를 거치며, 최종 마감과 재개에도 별도 사람 승인이 필요합니다. [월마감 계약과 제한](docs/period-closing.md), [검증 범위와 남은 항목](docs/period-closing-verification.md)을 참고하세요. **재무제표** 메뉴에서는 CLOSED 기간의 조정 시산표로 BS/IS를 생성하고 계정·전표까지 조회할 수 있습니다. [BS/IS 계약과 제한](docs/financial-statements.md)을 참고하세요.

## 바로 실행하고 테스트하기

회사별 계정과목 추가와 준비된 2025년 체험 로그인은 [계정과목·연간 체험 안내](docs/company-accounts-demo.md)를 참고하세요. 기본 계정과목은 통합 목록 175개이며 회사 전용 계정은 다른 회사에 표시되지 않습니다.

Docker Desktop을 실행한 뒤 저장소 루트에서 다음 명령을 실행하세요.

```sh
python scripts/dev.py env
python scripts/dev.py start
python scripts/bootstrap_local.py
```

`http://localhost:3000`을 엽니다. Compose가 **frontend/backend/PostgreSQL/Redis 네 서비스**를 실행하고 backend 시작 시 migration과 기본 권한·COA seed를 적용합니다. 첫 build에는 패키지 다운로드 시간이 필요합니다. Backend API 문서는 `http://localhost:8000/docs`입니다.

| 로그인 이메일 | 사용 목적 |
| --- | --- |
| `local-accountant@example.com` | 자료 업로드, 거래·전표 작성과 제출 |
| `local-owner@example.com` | 회사 설정, 별도 사용자 전표 승인과 장부 반영 |

비밀번호는 실행할 때 무작위로 만들며 [.local/development-accounts.ini](.local/development-accounts.ini)에만 저장합니다. 이 파일은 Git에서 제외됩니다. 준비 명령을 다시 실행해도 기존 비밀번호·회사·계정을 유지합니다. 다른 기존 계정의 비밀번호를 바꾸지 않습니다.

전역 root 또는 권한 우회 계정은 없습니다. 회사 관리자는 모든 회계 동작을 대신하는 역할이 아닙니다. **회계 담당자로 작성·제출 → 로그아웃 → 회사 관리자로 승인·장부 반영** 순서로 테스트하세요. 작성자가 본인을 승인할 수 없습니다. 회사 설정·계정과목·현재 연도의 열린 회계기간은 준비 명령이 생성합니다.

종료는 `python scripts/dev.py stop`입니다. 데이터 volume은 보존합니다. 포트를 바꾸면 `.env`의 `FRONTEND_PORT`, `BACKEND_PORT`, `FRONTEND_ORIGIN`과 bootstrap의 `--origin`을 맞추세요. 기존 호스트 방식 개발을 원하면 아래 독립 backend/frontend 실행 방법을 이용하고 `infra-start`로 PostgreSQL·Redis만 실행하세요.

## 설계 기준과 원칙

업무 화면은 홈·회사 관리·회계 준비·파일 가져오기·거래·전표·총계정원장·시산표·회계 설정으로 나뉩니다. 로그인 후 왼쪽 업무 메뉴를 이용하세요. [페이지 구성과 참고 코드·검증](docs/page-navigation.md)에 경로와 권한 안내가 있습니다.

단일 기준선: [AI_Accounting_Office_v0.2.6_통합설계_정본](https://drive.google.com/drive/folders/14f9qJtr7eKzC12n8GpdHcNc3Ff2nyYpf).
이전 설계 버전으로 fallback하지 않습니다. [설계 추적과 모듈 경계](docs/architecture.md)를 함께 참고하세요.

- **Relational-First**: 업무 데이터는 명시적 table/column/FK/constraint로 표현합니다. 업무 PostgreSQL **JSON/JSONB column은 0개**입니다. ADR-035의 공식 LangGraph 체크포인트만 별도 `agent_checkpoints` 스키마에 격리하며 허용 목록을 검사합니다. 체크포인트는 장부 정본이 아닙니다.
- **정본 분리**: accounting은 회계 장부, tax는 세무 계산·신고, evidence는 증빙/provenance, jobs/agents/tool executions는 실행 이력을 소유합니다.
- **Agent 경계**: Agent → Tool Registry → Tool Adapter → Application Service → Domain/Repository. Agent는 ORM/Session/SQL/Repository에 직접 접근하지 않습니다.
- **Deterministic calculation**: 금액·세금·잔액·집계는 Decimal, Domain Rule, Application Service와 결정적 query/calculation이 소유합니다. LLM이 계산하지 않습니다.
- **Human approval**: Posting, Period Close/Reopen, Tax Filing, Payment 확정은 사람의 승인과 Application Command 경계를 통과해야 합니다.

## 저장소 구조

```text
backend/app/     FastAPI 및 독립적인 업무 모듈 경계
backend/app/contracts/       ORM에 의존하지 않는 오류·UoW·Repository 계약
backend/app/core/database/  SQLAlchemy persistence primitive
backend/migrations/         Alembic 환경과 Identity/Company/Master/Storage/Intake migration
backend/tests/              unit, PostgreSQL integration, contract, golden
frontend/src/   app, features, shared
infra/          Backend/Frontend/PostgreSQL/Redis Docker Compose
scripts/        플랫폼 공통 개발 진입점
docs/           설계 추적, 환경변수, 검증 기록
.github/        backend/frontend 품질 CI
```

## 준비 사항

- Python 3.14 권장 (패키지 최소 버전 3.12; 현재 CI/검증은 3.14)
- Node.js 24 LTS, npm 11
- Docker Engine/Desktop 및 Compose v2 (`--wait` 지원), Git
- Windows는 Docker Desktop의 Linux 컨테이너 모드를 사용합니다.

명령은 별도 표시가 없으면 저장소 루트에서 실행합니다. Windows PowerShell에서 `npm` 실행 정책 문제가 있으면 `npm.cmd`를 사용하세요.

## 환경 설정

```sh
python scripts/dev.py env
```

루트 `.env.example`을 `.env`로 복사하고 무작위 로컬 인증 서명 키를 생성합니다. 기존 `.env`는 덮어쓰지 않습니다. 기존 개발환경에 키가 없다면 `python scripts/dev.py auth-key`로 추가하세요. 키 원문은 출력하지 않습니다. 파일의 값은 로컬 placeholder입니다. 실제 운영 비밀번호를 사용하거나 커밋하지 마세요. `.env`는 Git에서 제외됩니다.

[환경변수 계약](docs/environment.md)에 필수값, validation, URL/포트 동기화와 로그 정책을 설명합니다.

## PostgreSQL / Redis

```sh
python scripts/dev.py infra-start
# 또는
docker compose --env-file .env -f infra/docker-compose.yml config --quiet
docker compose --env-file .env -f infra/docker-compose.yml up -d --wait postgres redis
docker compose --env-file .env -f infra/docker-compose.yml ps
```

두 컨테이너가 `healthy`여야 합니다. 공개 포트는 localhost에만 바인딩됩니다. PostgreSQL 기본 5432, Redis 기본 6379입니다. 충돌하면 `.env`의 `POSTGRES_PORT`/`REDIS_PORT`와 `POSTGRES_URL`/`REDIS_URL`을 함께 수정하세요. 예: PostgreSQL 5433. 전체 Compose 실행에서는 백엔드 시작 스크립트가 호스트용 URL의 자격 증명을 유지하면서 내부 접속 주소를 `postgres:5432`와 `redis:6379`로 바꿉니다. `docker compose exec`로 Alembic을 직접 실행할 때는 이 시작 스크립트가 적용되지 않으므로 테스트 전용 DB 또는 컨테이너 내부 주소를 명시하세요.

```sh
python scripts/dev.py infra-stop
# 또는
docker compose --env-file .env -f infra/docker-compose.yml down
```

named volume은 유지합니다. `down -v`는 데이터를 삭제하므로 일상적인 종료에 사용하지 마세요. 이미 초기화된 PostgreSQL volume의 사용자/비밀번호는 환경변수 수정만으로 변경되지 않습니다.

## Backend

```sh
cd backend
python -m venv .venv
```

가상환경 활성화:

```powershell
# Windows PowerShell
.venv/Scripts/Activate.ps1
```

```sh
# Unix
. .venv/bin/activate
```

활성화 후 두 플랫폼에서 동일한 명령:

```sh
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
python -m alembic upgrade head
python -m app.companies.infrastructure.seed
python -m app.accounting.templates.infrastructure.seed
cd ..
python scripts/dev.py backend-run
```

기본 `http://127.0.0.1:8000`에서 실행합니다. 포트 충돌 시 `.env`의 `BACKEND_PORT=8100`처럼 변경하세요. 실제 기동 검증에서는 8100을 사용했습니다. `/docs`와 `/openapi.json`에서 메타데이터와 계약을 확인할 수 있습니다.

```sh
curl http://localhost:8000/health
```

기대 응답: HTTP 200, `{"status":"ok"}`. 변경한 포트를 사용하세요. PowerShell에서는 `curl.exe` 또는 `Invoke-RestMethod`를 사용할 수 있습니다.

`/health`는 **liveness**입니다. DB/Redis 연결이나 업무 데이터 존재를 검사하지 않습니다. 시작 시 필수 설정은 검증하지만 실제 DB 연결은 시도하지 않으므로 의존 서비스가 내려가도 앱은 시작합니다. DB Foundation도 이 계약을 유지합니다. DB 연결은 migration 또는 명시적인 persistence 사용 시 수행하며 실패는 안전한 공통 오류로 변환합니다. import 시 DB side effect나 자동 schema 생성은 없습니다.

## Frontend

```sh
cd frontend
npm ci
npm run dev
```

`http://localhost:3000`에서 가입·로그인 후 회사를 만들거나 접근 가능한 회사를 선택합니다. 포트 충돌 시 `npm run dev -- --port 3100`을 사용하고 backend의 `FRONTEND_ORIGIN`도 수정하세요. 실행 시 세션 복구를 요청하므로 인증 동작에는 backend가 필요합니다. lint/type/build는 backend 없이 독립 실행합니다.

`frontend/.env.example`을 `frontend/.env.local`로 복사하세요. backend가 8100이면 `BACKEND_API_ORIGIN=http://127.0.0.1:8100`으로 바꾸고 Next.js를 다시 시작하거나 다시 build하세요. 브라우저는 같은 origin의 `/api` 프록시를 사용합니다. root `.env` 전체를 frontend로 복사하거나 비밀값을 `NEXT_PUBLIC_*`에 넣지 마세요. backend `FRONTEND_ORIGIN`은 브라우저 주소와 일치해야 합니다.

## 품질 검사

활성화된 Python 가상환경에서:

```sh
cd backend
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy app
```

```sh
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

GitHub Actions가 backend/frontend를 독립 검증하고, 별도 PostgreSQL 17 service job에서 migration 및 schema/transaction/type integration을 필수 실행합니다. DB 없이 실행하는 pytest에서는 integration만 명시적으로 skip됩니다. Compose 설정도 별도 검사합니다. 현재 검증 기록은 [Identity/Company 검증](docs/identity-verification.md), 이전 기록은 [DB Foundation 검증](docs/database-verification.md), 기존 실행 기반 기록은 [Skeleton 검증](docs/verification.md)을 참고하세요.

## Migration과 PostgreSQL 통합 검사

가상환경을 활성화하고 backend에서 실행합니다. Alembic은 기존 typed settings의 `POSTGRES_URL`을 읽습니다.

```sh
cd backend
python -m alembic current
python -m alembic upgrade head
python -m alembic current --check-heads
python -m alembic check
```

현재 head는 `017_accounting_agent_queries`입니다. 회사별 관리차원과 분개 분석축, 원장 관리항목 필터를 지원합니다. [관리차원 계약과 검증](docs/accounting-dimensions.md)을 참고하세요. `015_period_closing → 016_financial_statements → 017_accounting_agent_queries`가 기존 migration chain 뒤에 이어집니다. upgrade 후 위 권한 seed 명령을 실행하세요. `alembic_version`은 내부 migration 상태입니다. 배포된 이력을 보존하고 v0.2.6 정책에 따라 순방향 revision을 추가했습니다. 공식 checkpoint table은 별도 schema에서 최초 실행 때 설치합니다.

통합 검사는 개발 DB와 분리된, 이름이 `_test`로 끝나는 PostgreSQL DB가 필요합니다. 예제 로컬 계정을 그대로 사용하는 경우 루트에서 한 번 생성합니다.

```sh
docker compose --env-file .env -f infra/docker-compose.yml exec -T postgres psql -U accounting_local -d postgres -c "CREATE DATABASE accounting_foundation_test;"
```

이미 있으면 다시 만들지 마세요. 계정과 포트는 자신의 `.env`에 맞추세요. backend에서 테스트 주소를 설정합니다.

```powershell
$env:TEST_POSTGRES_URL='postgresql://accounting_local:local_placeholder_change_me@localhost:5432/accounting_foundation_test'
```

```sh
# Unix
export TEST_POSTGRES_URL='postgresql://accounting_local:local_placeholder_change_me@localhost:5432/accounting_foundation_test'
```

```sh
python -m pytest --require-postgres
```

`--require-postgres`는 설정 누락을 실패로 처리합니다. 테스트는 전용 DB의 migration 상태를 초기화하고 복구하므로 공유·개발·운영 DB를 지정하지 마세요. 예상하지 않은 테이블이나 알려진 업무 테이블의 데이터가 있으면 삭제하지 않고 중단합니다. seed는 테스트 fixture 내부 transaction에서 실행하므로 통합 검사 전 테스트 DB에 영구 seed를 실행하지 마세요. [DB 구조와 정책](docs/database-foundation.md)에 lifecycle, 타입, 오류 및 schema guard를 설명합니다.

## 제외 범위와 다음 구현

Transaction/Journal/사람 승인/Posting/Reversal/원장/시산표, Governance와 Finance Subledger는 구현되어 있습니다. Agent Runtime은 거래 기반 조회·검증·전표 초안과 사람 검토 대기/재개, 기간별 월마감·BS/IS 읽기 질의를 지원합니다. Tax 정본, 자율 승인·Posting, 대화방/장기 메모리 UI, 상시 queue worker, 인증 이메일 검증·비밀번호 복구·초대 이메일 발송은 별도 범위입니다. Kafka/vector DB/pgvector는 포함하지 않습니다.

확정 가져오기 승격, 매출·매입 업무문서 → 거래·채권채무 연결, 은행·카드 대사와 Closing V1을 제공합니다. CLOSED 기간 BS/IS 스냅샷을 제공합니다. 비교재무제표·CF/SCE·주석·보고서 파일 Export는 후속 범위입니다. 후속 작업 시작 시 최신 main과 Drive를 다시 대조합니다.

## 거래 기반 회계 제안 실행

`LLM_PROVIDER=fake` 기본값으로 API Key 없이 실행할 수 있습니다. `/docs`에서 회계 담당자 권한으로 `POST /agent/runs/bookkeeper`에 `transaction_id`와 `Idempotency-Key`를 전달합니다. 대기 상태를 조회한 뒤 `POST /agent/runs/{id}/resume`에 현재 `expected_version`과 `CONTINUE` 또는 `REJECT`를 전달하세요. CONTINUE도 전표 초안까지만 만들며 회계 승인이 아닙니다.

기간 질의는 `POST /agent/queries/bookkeeper`에 `period_id`, `question`, `Idempotency-Key`를 전달합니다. Bookkeeper는 월마감 준비도와 CLOSED 기간 BS/IS 스냅샷만 읽고, 권한·회사 범위·숫자·출처를 Tool Registry와 Controller에서 확인합니다. 이 경로는 마감이나 기표를 실행하지 않습니다.

화면의 **AI 회계팀**에서 회사를 선택한 뒤 회계기간과 질문을 입력하면 이 기간 질의 API의 답변, 장부 기준 금액, 검증 상태와 스냅샷 근거를 확인할 수 있습니다. 회사 전환 시 이전 질의 결과는 화면에서 제거됩니다.
마감 차단 질의는 검사 건수와 각 검사 코드·영향 금액을 기존 Closing 결과에서 표시합니다. 입력·응답은 대화 이력 DB에 저장하지 않으며, 질문 실패와 검증 차단을 성공 답변과 구분합니다.

Gemini/LangGraph/LangChain/MCP 역할, 실제 Tool 목록, 로컬 MCP 실행과 제한은 [Agent Runtime](docs/agent-runtime.md), 실제 검증 결과는 [검증 기록](docs/agent-runtime-verification.md)에 있습니다.

회사 선택 후 회계 관리 권한이 있으면 별도 초기 설정으로 기본 COA·12개월 기간·번호 기준을 만듭니다. 초기화는 같은 조건으로 재실행할 수 있습니다. 거래처와 지급조건 API, 번호·정책 규칙과 제외 범위는 [회계 마스터 문서](docs/accounting-master.md)를 참고하세요.

## 주석과 사용자 안내 문구

직접 작성하는 코드 주석과 docstring은 한글로 작성합니다. 도구가 자동 생성하는 파일과 타입 지시문은 생성 도구의 형식을 유지합니다.

사용자가 읽는 화면·API 메시지는 쉬운 한글로 작성하고, 필요한 경우 다음 행동을 안내합니다. 초기 화면에는 내부 개발 단계명이나 설계 버전을 표시하지 않습니다. 오류 원문이나 내부 구현 정보를 사용자 안내에 넣지 않습니다. API 필드명·오류 코드·환경변수명처럼 프로그램 간 계약에 해당하는 식별자는 유지합니다.


## 파일과 자료 가져오기

현재 회사의 ACCOUNTANT/TAX_ACCOUNTANT 중 Intake 권한을 가진 사용자는 화면의 자료 가져오기에서 CSV/XLSX를 올릴 수 있습니다. OWNER 역할만으로 업로드 권한을 자동 부여하지 않습니다.
원본 열을 회계 항목에 연결하고 검증 결과를 확인한 뒤 명시적으로 접수합니다. 미리보기는 15분간 유효합니다. **파일 확인 완료 → 확인한 자료로 거래 생성 → 거래 생성 완료**를 구분합니다. 거래 생성 후에도 전표 작성·사람 승인·장부 반영은 별도로 진행합니다. 실패한 거래 생성은 같은 접수에서 재시도할 수 있고, 새로고침하면 현재 회사의 최근 접수를 복구합니다.

UTF-8 CSV/UTF-8 BOM CSV와 XLSX, 최대 2MB·총 1,000행·40열·5시트를 지원합니다. 수식·매크로·외부 연결·삽입 개체는 제거해 주세요.
예를 들어 SALES CSV의 필수 header는 `source_id,transaction_date,amount,currency`이며 날짜는 `2026-01-02`, 금액은 `100.0001`, 통화는 `KRW` 형태입니다.
원본 파일은 backend 실행 기준 `STORAGE_ROOT=../.local/storage` 아래 서버 생성 키로 보관합니다. 이 경로는 Git에서 제외되며 파일 bytes를 PostgreSQL에 저장하지 않습니다.

API 사용 시 `/docs`에서 multipart 업로드와 typed 명령을 확인할 수 있습니다. 모든 Import 요청은 Bearer와 `X-Company-ID`, 변경 요청은 `X-CSRF-Protection: 1`, Confirm과 `POST /imports/{id}/promote`는 `Idempotency-Key`가 필요합니다. 승격에는 접수 영수증의 `confirmed_version`, `id`, `source_digest`를 전달합니다. 업로더에게 `import.confirm`과 `transaction.create` 권한이 모두 있어야 합니다. [승격 계약·검증·제한](docs/import-transaction-promotion.md)을 참고하세요.
[구조·API·파일 제한·후속 계약](docs/storage-evidence-intake.md), [실제 참고 파일과 충돌 처리](docs/intake-source-patterns.md), [검증 결과](docs/intake-verification.md)를 참고하세요.

## 거래·전표·원장·시산표

회사별 거래 입력부터 전표 작성, 제출, 별도 사용자 승인, 장부 반영, 원장·시산표 조회까지 연결했습니다. 기초잔액도 같은 승인·확정 흐름을 사용합니다.

- [회계 흐름과 API 계약](docs/transaction-journal-ledger.md)
- [최종 검증 기록](docs/accounting-core-verification.md)
- 브라우저 검증: `node scripts/accounting-browser-smoke.cjs --allow-synthetic` (전용 테스트 서버 필요)
- DB 실측: `python scripts/verify_accounting_schema.py` (`TEST_POSTGRES_URL`, `_test` DB 필요)

## 처음 회사 설정과 설정 관리

새 회사는 업무 홈에서 회사정보 → 회계 기준 → 거래처 → 기초잔액 → 최종 확인 순서로 준비합니다. 완료한 회사는 업무 홈에서 바로 일을 시작하고, 변경할 내용은 설정 관리에서 수정합니다. 서버 기본 계정과목은 175개이며 권한이 있는 사용자는 회사 전용 계정을 추가할 수 있습니다. [현재 계정과목·체험 안내](docs/company-accounts-demo.md)를 참고하세요.
