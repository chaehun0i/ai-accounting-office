# 회사 관리차원

계정과목은 회계 분류이고, 관리차원은 사업장·부서·프로젝트·원가센터 분석축입니다. 계정과목을 분석축마다 복제하지 않습니다. 이번 변경은 `feat/accounting-dimensions`에서 구현하며 기존 Transaction/Journal/Finance/Agent 기능을 다시 만들지 않습니다.

## 설계 기준과 적용 결정

시작 main은 `05ce5b4ae8f4defa1d11564e4b8aff4dde7d9744`입니다. Google Drive `AI_Accounting_Office_v0.2.6_통합설계_정본`의 활성 문서를 사용했으며 fallback과 Archive는 사용하지 않았습니다.

직접 확인한 문서는 읽기안내_문서지도_용어집, 제품_개발로드맵_구현순서_릴리즈게이트, 회계코어_계정과목_분개_원장_시산표, Accounting_Policy_COA_기초잔액_전표번호, Complete_DDL_Migration_Map, Physical_ERD_PostgreSQL_DDL_SQL, API_Pydantic_Contract, Error_Idempotency_Concurrency_Contract, Permission_Matrix_RBAC, Repository_Module_Architecture, Relational_First_No_JSON_DB_Policy, Implementation_DoD_Review_Checklist, 전산회계운용사_1급_2급_3급_Coverage_Matrix, Golden_Dataset_Fixture, 샘플회사_페르소나_데이터셋_가이드입니다.

로드맵/Coverage에 남은 PR #7 기준 구현 현황은 실제 PR #10 main과 구분합니다. 설계 방향은 Drive, 구현 사실은 GitHub를 기준으로 판단했습니다. 설계 migration map의 003/007 소속 의미를 유지하되 배포 이력을 고치지 않고 `011_accounting_dimensions`를 010 다음에 추가합니다.

설계가 구체적인 required_policy 값을 정의하지 않아 이번 계약은 `OPTIONAL`(기본)과 `REQUIRED`(활성 분석축을 모든 제출·승인·확정 분개에 요구)로 제한했습니다. Draft에는 미입력을 허용합니다. 같은 유형의 활성 필수 분석축은 하나만 허용하며, 생성·수정 시 회사 잠금 안에서 중복을 차단합니다.

## 관계형 구조와 실행 경계

- `accounting_dimensions`: 회사별 코드 UNIQUE, 유형/상태/필수정책/version CHECK.
- `accounting_dimension_values`: 분석축별 코드 UNIQUE, 회사·분석축을 포함한 부모 composite FK, 기간/version/self-parent CHECK. Application은 조상 경로의 순환도 차단합니다.
- `journal_line_dimensions`: 회사·분개·분석축·유형·항목을 composite FK로 연결합니다. 분개별 분석축 및 유형 UNIQUE가 중복을 차단합니다. 모든 삭제 규칙은 RESTRICT입니다.

Application Service가 UoW를 소유하고 Repository는 flush만 합니다. 라우터는 Repository를 호출하지 않습니다. `dimension.read`와 `dimension.manage` 권한을 사용하며 관리 권한은 OWNER/ADMIN/ACCOUNTANT에만 부여합니다. 모든 변경은 CSRF와 서버 검증 회사 문맥을 요구합니다. PATCH는 전체 변경 가능 필드와 expected_version을 받습니다. 코드/유형은 분석축 생성 후 변경하지 않습니다.

Posting은 기존 전표·기간·계정 잠금 이후 회사, 분석축, 항목 순서로 잠근 뒤 상태와 전표일 기준 적용기간을 재검증합니다. 관리차원 생성·수정도 같은 회사 잠금을 사용하여 검증 도중 필수 분석축이 새로 생기는 경우까지 차단합니다. 보수적으로 회사 내 관리차원 변경과 Posting을 직렬화합니다. 조회 규모가 커지면 잠금 범위 최적화를 별도로 검토할 수 있습니다.

POSTED 연결의 INSERT/UPDATE/DELETE는 PostgreSQL trigger도 거부합니다. 역분개는 기존 Application 흐름을 사용하며 원 분개의 관리항목을 보존하고 새 전표의 Posting 시 다시 검증합니다. 기존 항목이 중지됐다면 역분개도 유효한 관리항목 정책을 먼저 확인해야 합니다.

새 선택 필드는 기본 빈 배열이며 기존 API 입력은 호환됩니다. 다만 승인 fingerprint에 선택 항목이 포함되므로 배포 전에 생성한 대기 승인/요청의 digest가 달라질 수 있습니다. 이를 조용히 승인하지 않고 기존 stale/conflict 정책으로 다시 검토하게 합니다. 확정된 전표는 변경하지 않습니다.

## 조회와 화면

설정 관리의 관리차원 탭에서 분석축·항목 생성, 부모/적용기간 지정, 사용 중지/재사용을 지원합니다. 전표 분개마다 항목을 선택하며 같은 유형 선택은 교체합니다. 전표 상세에도 관리항목을 표시합니다. 회사 전환 시 workspace를 새로 마운트하여 이전 회사 상태를 제거합니다. 기존 회사 문맥은 메모리 상태이므로 복수 회사 사용자가 전체 페이지를 새로고침하면 회사를 다시 선택해야 합니다. 저장된 관리차원은 서버에서 복구됩니다.

`GET /ledger`에 선택적 `dimension_value_id`를 추가했습니다. EXISTS 기반 필터라 분개를 중복 합산하지 않습니다. 기본 원장, 계정 기준 시산표, AR/AP 대사 계산은 바꾸지 않습니다. 이번 범위에서 별도 Dimension TB/group-by, Import Promotion, Agent mutation Tool을 구현하지 않습니다.

## 재사용과 샘플 정합성

| 후보 | 판정 | 실제 적용 |
|---|---|---|
| 현재 Accounting Master/UoW/RBAC | PATTERN/ADAPT | 관리차원 Service/Repository/API |
| 현재 Journal validation/Posting 잠금 | PATTERN/ADAPT | 기존 검증 함수 안에서 항목 재검증 |
| 현재 company-scoped Ledger query | ADAPT | 선택적 EXISTS 필터 |
| 현재 settings workspace | ADAPT | 관리차원 탭과 상태 복구 |
| 외부 프로젝트 Domain 코드 | DROP | 직접 이식/COPY 없음 |

Drive 샘플 폴더를 MIME/metadata로 확인했습니다. 공식 regression source는 native Google Sheet 3개 `AI_Accounting_Office_SYN_SERVICE_001`, `AI_Accounting_Office_SYN_RETAIL_001`, `AI_Accounting_Office_SAMPLE_COMPANY_2025`입니다. 추가로 macro-enabled `AI_Accounting_Office_SAMPLE_COMPANY_2025_v1.xlsm`과 가이드가 존재합니다. `.xlsm`은 legacy/raw artifact이며 공식 업로드 fixture가 아닙니다. 파일은 삭제하거나 수정하지 않았습니다. 문서의 ‘설계문서 1개 + native Sheet 3개’ 설명과 실제 legacy 파일 동시 존재는 후속 Drive 정리 대상입니다.

SYN_MFG_001의 native Sheet Company/COA metadata와 기존 읽기 전용 `native-2025-v1` CSV snapshot을 확인했습니다. 테스트 adapter만 관리항목을 추가하며 fixture 원본 및 expected는 수정하지 않습니다. 세무 값은 synthetic source fact이며 신고 정답으로 사용하지 않습니다.

## 용어

COA는 계정과목표, GL은 총계정원장, TB는 합계잔액시산표, AR/AP는 매출채권/매입채무, UoW는 작업단위 트랜잭션, FK는 외래키, RBAC는 역할 기반 권한, CSRF는 사이트 간 요청 위조, TOCTOU는 검증과 실행 사이 상태 변경 위험을 뜻합니다. 화면은 내부 약어보다 한국어 업무 용어를 우선합니다.

## 검증 기록

2026-10-11, `4a95790`의 [전체 CI](https://github.com/chaehun0i/ai-accounting-office/actions/runs/38132970296)가 네 작업 모두 성공했습니다. 이후 회사 선택 팝업의 중복 HTML ID를 수정했고 최종 PR HEAD에서도 같은 CI를 다시 실행합니다. 실행별 결과는 합산하지 않습니다.

| 명령/검증 | 결과 |
|---|---|
| `python -m pytest --ignore=tests/integration` | 217 passed, 1 warning |
| `python -m pytest tests/integration --require-postgres` | 148 passed, 1 skipped, 1 warning; 477.91초 |
| `python -m ruff check .` / `python -m ruff format --check .` (backend) | 통과, 422 files |
| `python -m mypy app` / `python -m pip check` | 331 source files 통과 / 의존성 충돌 없음 |
| `alembic current`, `upgrade head`, `current --check-heads`, `check` | head `011_accounting_dimensions`, metadata diff 없음 |
| migration 통합 테스트 | clean → head, base 왕복, 010 ↔ 011 왕복 통과 |
| `python ../scripts/verify_accounting_schema.py` | 업무 table 70, FK 170, orphan 0, JSON 0, JSONB 0 |
| `npm ci`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` | CI 통과, frontend 27 passed |
| Compose config/build/up --wait/ps 및 bootstrap 재실행 | CI 통과, 로컬 backend/frontend/PostgreSQL/Redis healthy |
| `node scripts/accounting-browser-smoke.cjs --allow-synthetic --dimensions` | 격리 PostgreSQL API + 실제 Edge 브라우저 통과 |

Integration에는 관리차원 CRUD/권한/CSRF/회사 주입/상위항목 순환/stale version, 필수정책, POSTED 연결 INSERT·UPDATE·DELETE SQLSTATE 23514, 비활성 항목 Posting 재검증이 포함됩니다. 기존 Agent architecture guard와 Accounting/Finance 테스트도 재실행했습니다. 실 Gemini 네트워크 테스트는 키를 요구하므로 의도적으로 제외합니다.

브라우저는 로그인 → 관리차원·항목 생성 → 새로고침 복구 → 거래 생성 → 분개별 항목 선택 → 제출 → 별도 사용자 승인 → 장부 반영 → 원장 관리항목 필터 → 전표 상세 → 시산표 → 다른 회사 전환 → 빈 관리차원 목록을 검증했습니다. 팝업과 본문에 동시에 표시되는 회사 선택 입력의 중복 HTML ID도 수정했습니다. 합성 데이터는 격리 테스트 DB에만 만들었습니다.

GOLDEN_CORP_001에 관리항목을 붙인 동일 전표 흐름에서도 AR 5,500,000 / AP 1,650,000 및 TB 차변·대변 62,650,000을 유지했습니다. SYN_MFG_001의 기존 연간 회귀를 관리항목과 함께 실행하여 모든 계정별 차변·대변 합계와 AR/AP 대사가 동일함을 검증했습니다. 두 테스트 모두 위 PostgreSQL 실행에 포함됩니다. fixture 원본 변경은 없습니다.

Windows 공유 파일시스템의 로컬 전체 테스트 시도에서는 기존 Agent subprocess 복구 30초 제한과 한 Controller 테스트가 실패하여 중단했습니다(2 failed, 75 passed 시점). 이를 성공으로 기록하지 않습니다. 동일 코드의 Linux CI 전체 회귀는 위 결과로 통과했으며 로컬 집중 검증과 컨테이너 빌드도 별도로 수행했습니다. Python warning은 기존 google.genai의 Python 3.17 예정 폐기 항목 안내입니다. GitHub action Node 20 런타임의 향후 지원 종료 안내도 남아 있습니다.

최종 HEAD와 commit 목록, 최종 CI 링크는 PR 본문에 기록합니다. 다음 후보는 Intake → Canonical Transaction Promotion이며 이번 변경에는 포함하지 않습니다.
