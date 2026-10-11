# 채권·채무 정산 검증 기록

## 기준과 변경

- 작업 시작 main: `52f173decd38189dda05f042af291487421309f9` (PR #7 병합)
- branch: `feat/finance-subledger-settlement`
- 시작 전과 push 전 원격 fetch, main SHA·열린 PR·열린 Issue 재확인: 기준 SHA 유지, 열린 항목 없음
- Drive: `AI_Accounting_Office_v0.2.5_통합설계_정본`, 활성 문서만 사용, fallback 없음
- 신규 migration: `009_finance_subledger`, 직전 `008_governance`, 기존 migration 수정 없음
- 최종 HEAD와 전체 커밋 목록은 이 문서를 포함한 PR 본문 및 `git log --reverse origin/main..HEAD`에 기록합니다.

## 구현 결과

확정 전표 → 회사별 채권/채무 인식 → 수금/지급 헤더 → 1:N·N:1 배분 → 명시적 확정 → 부분/완납 → 기준일 잔액·Aging → GL 대사 → UI 재접속을 연결했습니다. 회계 장부는 계속 POSTED Journal이며 Finance는 이를 수정하거나 자동 Posting하지 않습니다.

신규 테이블: receivables, payables, collections, payments, collection_allocations, payment_allocations, finance_command_receipts, reconciliation_matches, reconciliation_match_lines. 마지막 두 테이블은 DDL 호환용이며 은행/카드 매칭 기능은 제외합니다.

실제 PostgreSQL 검사 결과:

| 항목 | 값 |
| --- | ---: |
| 전체 업무 테이블 | 62 |
| JSON 컬럼 | 0 |
| JSONB 컬럼 | 0 |
| 전체 FK | 148 |
| 고아 참조 | 0 |
| 신규 Finance FK | 30 |
| 신규 Finance CHECK | 28 |
| 신규 Finance UNIQUE | 12 |
| 신규 Finance PK | 9 |
| 신규 Finance 인덱스, 제약 인덱스 포함 | 53 |

`scripts/verify_accounting_schema.py`가 public 업무 schema와 ORM metadata의 테이블 일치, JSON/JSONB, 모든 FK의 실제 고아 참조, migration head를 단언합니다. `information_schema`와 PostgreSQL catalog에서 실측했으며 추정값이 아닙니다.

## 검증 명령과 결과

PostgreSQL 테스트는 개발 DB와 다른 `_test` DB에서 실행했습니다. 실행기는 새 DB를 만들고 finally에서 삭제합니다. 기존 DB를 발견하면 덮어쓰지 않습니다.

| 명령 | 결과 |
| --- | --- |
| `python -m pytest` | 175 passed / 125 PostgreSQL 설정 없음으로 skip / warning 1 |
| `TEST_POSTGRES_URL` 설정 후 `python -m pytest tests --require-postgres` | 295 passed / failed 0 / skip 0 / warning 1, 1081.52초 |
| 추가 공식 상세 행 테스트 | 2 passed |
| 추가 native 금액 완납·MISMATCH 해소 PostgreSQL 테스트 | 2 passed |
| 추가 파일→증빙→거래→전표→채권 출처 PostgreSQL 테스트 | 1 passed |
| `python -m ruff check .` | 통과 |
| `python -m ruff format --check .` | 통과 |
| `python -m mypy app` | 283 source files, 통과 |
| `python -m pip check` | No broken requirements found |
| `npm ci` | 통과, 0 vulnerabilities |
| `npm run lint` | 통과 |
| `npm run typecheck` | 통과 |
| `npm test` | 25 passed |
| `npm run build` | 통과, 13 static pages |
| Compose config / `up -d --build --wait` / ps | frontend·backend·PostgreSQL·Redis 모두 healthy |
| `GET /health` | 200, status=ok |
| Alembic current / upgrade head / current --check-heads / check | 009_finance_subledger, metadata diff 0 |
| clean DB→head / head→base→head / 008↔009 | 실제 PostgreSQL 통합 검증 |
| 브라우저 Finance smoke | AR/AP 각각 로그인·회사·등록·배분·확정·부분 잔액·대사·reload 통과 |
| `git diff --check` | 통과 |

CI는 backend 정적 검사·기본 테스트, PostgreSQL 전체 integration·migration·스키마 gate, frontend 전체 검사, 네 서비스 Compose 기동을 수행합니다. 브라우저 smoke는 로컬에서 실행했으며 CI에서 실행했다고 주장하지 않습니다.

전체 PostgreSQL 실행이 시작된 뒤 추가한 공식 상세 단위 2건과 PostgreSQL 완납·출처 3건은 별도 명령으로 전부 통과했습니다. 현재 **300개 테스트(단위·계약 175, PostgreSQL 125)**를 모두 실행했으며, 한 번의 명령에서 300개가 통과했다고 합산해서 표현하지 않습니다. 기본 pytest의 DB skip은 위 PostgreSQL 실행과 추가 통합 검증에서 모두 보완됐습니다. 이번 작업에서 만든 브라우저 전용 DB와 임시 회귀 DB는 검증 후 제거했습니다.

### 실패를 발견하고 수정한 과정

첫 전체 PostgreSQL 실행은 288 passed / 4 failed였습니다. 신규 테스트의 Repository 회사 인자 검사 범위와 필수 출처 인자 누락을 수정했습니다. 타 회사 정산 요청은 통화 설정 확인보다 회사별 resource 조회를 먼저 수행하여 404 계약을 유지했습니다. 연간 회귀가 실제 access token TTL을 넘겨 실패한 경우 테스트에서 240초마다 정상 로그인으로 인증을 복구했습니다. 운영 TTL·인증 정책을 완화하지 않았습니다.

Compose `exec`의 초기 Alembic 호출은 호스트용 주소로 접속해 실패했습니다. entrypoint와 동일하게 내부 `postgres:5432` 주소를 적용하여 재실행했고 current/upgrade/check가 통과했습니다. 자격 증명을 출력하지 않았습니다.

기존 Starlette TestClient의 httpx deprecation warning 1건이 있습니다. 이번 변경의 실패나 skip을 성공으로 기록하지 않습니다.

## 회계·보안 시나리오

- 단건 Golden: AR 5,500,000 / AP 1,650,000, 각각 GL MATCHED.
- 기존 TB 차변/대변 62,650,000 유지, 회계 현금 50,550,000, 카드미지급금 0 확인. Treasury/Card workflow 구현을 뜻하지 않습니다.
- 하나의 6,000,000 헤더를 4,000,000 / 2,000,000에 배분하는 1:N, 복수 헤더로 한 대상을 완납하는 N:1을 AR/AP 모두 PostgreSQL에서 확인.
- 미배분액 보존, 헤더/대상 초과 차단, stale version 409, 동일 키 replay·다른 fingerprint conflict 확인.
- 독립 사용자·독립 DB 연결의 동시 확정: 한 요청만 성공, 다른 요청은 SETTLEMENT_TARGET_STALE, 초과 수금·지급 없음.
- 실패 주입 시 헤더·배분·대상 버전 rollback을 확인했습니다. 영수증·Audit도 같은 UoW에 속합니다. SQL/예외 원문 API 노출 없음.
- 확정된 헤더와 배분의 직접 UPDATE/DELETE는 DB trigger에서도 차단.
- 401, 재무 권한 없는 OWNER 403, 타 회사 ID 404, 폐기된 membership 차단, DRAFT 원천 차단, extra/float 요청 거부.
- Ledger 차이 MISMATCH를 숨기거나 자동 보정하지 않으며 배분 확정 후 해소를 확인.
- 신규 Finance runtime에서 legacy 식별자, get_by_id, Repository commit 검색 0건. API의 float 타입 검사는 금액 변환이 아니라 입력 거부를 위한 검사입니다.
- 기존 architecture guard와 malicious spreadsheet 회귀를 유지합니다. Agent/LLM·SQL/ORM 직접 접근 경계를 변경하지 않았습니다.

## 연간 공식 정본

공식 native Sheet `AI_Accounting_Office_SAMPLE_COMPANY_2025`에서 SYN_MFG_001의 매출 청구서 240건·매입 74건·거래처 20개와 정산 행을 읽었습니다. 상세 행 486/148의 합계를 공급가액과 Decimal로 비교했습니다. 입력 snapshot의 hash와 원본 XLSX hash는 [fixture 기록](../backend/tests/fixtures/finance/native-2025-v1/README.md)에 있습니다.

발생일보다 앞선 COLL_MULTI_001/PAY_MULTI_001 전체 batch를 명시적으로 거부합니다. 유효한 정산만 반영한 2025-12-31 AR은 **445,109,940**, AP는 **94,178,810**이며 각각 GL과 일치합니다. 원본 유효 행은 AR PARTIAL 171/OPEN 69, AP PARTIAL 55/OPEN 19입니다. 완납은 원본 금액을 이용한 별도 파생 시나리오에서 검증하며 원본의 부분 정산 값을 바꾸지 않습니다.

`_v1.xlsm`은 legacy/raw artifact이며 공식 Onboarding fixture가 아닙니다. native Sheet 정본·기존 macro 없는 XLSX를 수정하지 않았고 세무 sample fact를 신고 정답으로 쓰지 않았습니다.

## 브라우저 재현

1. Compose를 실행합니다. 별도 터미널에서 `TEST_POSTGRES_URL`을 **아직 없는 로컬 `_test` DB** 주소로 설정합니다. credential은 문서/명령 이력에 공유하지 않습니다.
2. backend 가상환경 Python으로 루트에서 `python scripts/finance_browser_api.py`를 실행합니다. 새 테스트 DB만 만들고 localhost:8002에서 서비스합니다.
3. Playwright가 설치된 환경에서 `node scripts/finance-browser-smoke.cjs --allow-synthetic`를 실행합니다. 필요하면 `PLAYWRIGHT_MODULE_PATH`와 `BROWSER_CHANNEL`을 설정합니다.
4. 실제 Compose frontend를 열되 `/api` 요청만 격리 API에 연결합니다. 개발 회사·계정은 사용하지 않습니다. 등록/회계 승인/Posting 준비는 실제 API로 수행하고, Finance 업무는 실제 브라우저에서 수행합니다.
5. API를 Ctrl+C로 종료하면 생성한 테스트 DB를 삭제합니다. 강제 프로세스 종료로 finally가 실행되지 않았다면 **자신이 생성한 정확한 테스트 DB만** 확인 후 정리합니다. 개발 DB나 기존 다른 테스트 DB를 삭제하지 않습니다.

## 한계와 후속 계약

기능통화 KRW, 서버 고정 통제계정 이름 매핑을 사용합니다. 확정 후 미배분 추가 적용, 정산 취소·원천 역분개 연계, adjustment/writeoff, pagination은 후속 범위입니다. 현재 MISMATCH와 source/evidence 참조는 Closing blocker 및 후속 reconciliation이 사용할 계약입니다.

실제 은행 이체·은행/카드 전체 workflow·Expense·Treasury·자산·재고·원가·결산·재무제표·세무·Jobs/Agent/LLM은 구현하지 않았습니다. 다음 작업은 최신 main/Drive를 다시 대조하여 Finance 확장 또는 Asset·Inventory 중 실제 gap을 선택합니다.

실제 참고 원본 파일·함수와 PATTERN/DROP 판단은 [구조 및 참고 코드 기록](finance-subledger.md)에 있습니다. COPY는 없습니다.
