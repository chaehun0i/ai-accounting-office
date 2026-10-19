# 은행·카드 대사 검증 기록

기준일 2026-10-12. 시작 `origin/main=91918e98312204ee72b660b8d6550ae64ed07b67`, 최근 merge PR #13, 열린 PR/일반 Issue 없음, 실제 head `013_business_documents`를 fetch와 GitHub 조회로 확인했습니다. 기존 Business Document main tree와 009 schema를 직접 읽었습니다. 완료 여부는 아래 실제 실행 결과로 구분합니다.

## 설계와 문서 동기화

semantic version 최신 유효 SSOT는 `AI_Accounting_Office_v0.2.6_통합설계_정본`입니다. 문서지도를 먼저 읽고 활성 00/02/07/08/09를 사용했으며 fallback/Archive는 사용하지 않았습니다. 읽은 제목과 Drive ID는 다음과 같습니다.

| 문서 | Drive ID |
| --- | --- |
| 읽기안내_문서지도_용어집 | 18L_6SaI3IFzAzmhmKxxc3AIqMyx5-HUydoHQu31Zokg |
| 제품_개발로드맵_구현순서_릴리즈게이트 | 1IFxly_Qtvj-VzWwwhIvH0OsLGEXkf44i5ZiuWKEI-NY |
| 재무운영_AR_AP_은행카드_자금 | 1pm3CsLn6bNaitp2dvVsrsJajQvqQhzckJz1nQohEGvc |
| Physical_ERD_PostgreSQL_DDL_SQL | 1betNB4Kps9TaUpZc9avGdeKIPsJtxwApXzKlvtaDCgc |
| Complete_DDL_Migration_Map | 11Ll8SNDw1yYWDq-QhDcpx2NErfhU3lLrEyG_0GMNTeU |
| API_Pydantic_Contract | 1seqmSKIwjyWP5mKQYJt-RTG-e2XKbqAoIXxuGzUOWBw |
| Error_Idempotency_Concurrency_Contract | 13t98aKXmUqESBXfHDgjgYn1sy2DGB2rOHEH6Cgp_p3g |
| Permission_Matrix_RBAC | 1ErPSu4ouGwZKLzjSV_yYDTT5cWy-uyTMCPVJG4mYP4k |
| Repository_Module_Architecture | 19YI_AEJxAiBnv6LSFP-uwNklluRWe1DHfnwtqIHSmDs |
| State_Transition_Matrix | 12WGXtpu9mLhd-Ta6t2kvnLiXeECMswtsjlwh1O9QDl0 |
| Implementation_DoD_Review_Checklist | 1oF8ELWdWcZl5X-q6hGltcOpaj2Ftwy35SZpijCdnJEY |
| Golden_Dataset_Fixture | 17e3trqnSRBoR5g2oC4XXguAUX37TX_htMrWLCJcrH8o |
| 전산회계운용사_1급_2급_3급_Coverage_Matrix | 1PTpYcxOButx866i0D2-LGicy2vOgTDG1j4rkcbruJ4A |
| 샘플회사_페르소나_데이터셋_가이드 | 1PBsy7tsIlopLgvXCj7QDEWm9wQ9KiBmpCfu35LmmCBE |

Roadmap과 Coverage의 Current 문구가 PR #12/c4f983 기준으로 남아 있었습니다. Google Docs revision guard를 사용해 해당 문단만 실제 PR #13/main 91918e9/head 013과 Business Document verified 상태로 수정하고 readback을 검증했습니다. 다음 Target을 Bank/Card로 맞췄으며 진행 중 branch를 merge/verified로 과장하지 않았습니다. 다른 문서의 과거 구현 기록을 일괄 치환하지 않았습니다.

## DB 실측과 migration

전용 `accounting_bank_browser_test`에서 schema 검증 스크립트와 PostgreSQL catalog를 조회했습니다.

| 측정 | 실제 값 |
| --- | ---: |
| 업무 테이블 | 88 |
| 업무 FK | 250 |
| public 인덱스 | 495 |
| public CHECK | 232 |
| FK orphan 행 | 0 |
| 업무 JSON 컬럼 | 0 |
| 업무 JSONB 컬럼 | 0 |
| 신규 014 테이블 | 8 |
| 해당 DB의 framework JSON/JSONB 컬럼 | 0 / 0 |

실제 head는 `014_bank_card_reconciliation`입니다. Framework checkpoint가 설치된 DB의 allowlist 정책을 변경하지 않았습니다. 빈 DB full upgrade, alembic metadata diff, 013으로 clean downgrade 후 재upgrade와 재diff가 통과했습니다. 기존 개발 DB도 Compose 시작 시 013→014 forward upgrade 후 health가 정상입니다. 사용자 데이터/volume을 초기화하지 않았습니다.

실제 Compose 개발 DB도 READ ONLY transaction으로 별도 검사했습니다. 업무 테이블 88/FK 250/JSON 0/JSONB 0/orphan 0/head 014가 동일했고 `/health`와 frontend HTTP는 200입니다. 컨테이너 내부 CLI는 기존 entrypoint와 동일하게 URL host를 postgres:5432로 맞춰 `current --check-heads`/`check`를 통과했습니다. 원래 호스트용 URL로 실행한 첫 CLI는 연결 오류였으며 이를 성공으로 집계하지 않습니다.

## 실행 결과

- 최종 전체 PostgreSQL 실행: **463 passed, 1 skipped** (단일 실행 1913.01초, 총 464개). 기존 Accounting/Journal/Posting/Reversal/GL/TB/Finance/Agent/Dimension/Intake/Promotion/Business Document와 연간 회귀를 포함합니다. skip 1개는 기존 `test_opt_in_gemini_structured_output`의 실 Gemini 호출 opt-in 미설정이며 이번 기능 테스트를 skip하지 않았습니다. 뒤이어 Ruff/format/mypy/pip check/Alembic current·check/schema guard가 모두 통과했습니다.
- 최종 집중 PostgreSQL/Domain/Architecture/API 계약 검증: **58 passed** (단일 실행 382.63초). 산업별 실제 후보 확정과 기존 Golden T002/T007, 1:N/N:1/부분·초과/stale·동시 요청, CSRF/권한, 정상 명세 마감 및 마감 후 해제 차단, 같은 Import를 다른 카드로 재승격하는 요청 차단을 포함합니다.
- 기존 확정 Collection/Payment→은행 대사: **2 passed** (별도 단일 실행 57.66초). 부분 정산 잔액 60과 source/GL 차이 0을 보존합니다. 위 58개와 합산하지 않습니다.
- 최종 unit/contract 전체: **262 passed** (단일 실행 57.89초). 새로운 migration chain과 SDK/Repository/Agent architecture guard를 포함합니다.
- Ruff check/format check: 통과. mypy: 379 source files 통과. pip check: broken requirements 없음.
- Frontend npm ci: 통과, 151 packages/취약점 0. lint/typecheck/test/build: 통과, frontend test 단일 실행 32 passed, 운영 static route 16개.
- Compose config/build/up --wait: 통과, frontend/backend/PostgreSQL/Redis 4개 healthy.

최종 코드의 실제 Edge production UI smoke가 통과했습니다. 로그인→관리자 별칭/통제계정 설정→ACCOUNTANT CSV 업로드/검증/접수→원천 생성→후보/초안/사람 확정→GL 차이 보존→해제/재확정→reload→카드 원천/확정→다른 회사 전환 후 미노출을 실행했습니다. 작은 테스트에는 POSTED 전표가 없는 원천의 GL 차이를 그대로 표시합니다. 서로 다른 실행의 passed 수를 합산하지 않습니다.

현재 지원 제한은 파일 2,000,000 bytes/1,000행/40열/5 Sheet입니다. 최종 58개 실행 중 원천 승격 API 단일 측정은 제조업 은행 346행 **3.553초**, 카드 88행 **1.798초**였습니다. Windows 호스트 Python→Docker PostgreSQL, 다른 회귀 실행과 동시 측정이며 p95나 성능 보증이 아닙니다. 50k/120초 Gate는 미검증입니다. 더 큰 규모는 parser 안전 제한 검토와 batch/Worker/원자적 staging 설계가 필요하며 이번 PR에서 제한을 확대하지 않았습니다.

## Golden와 산업 fixture 의미

GOLDEN_CORP_001의 TB 62,650,000/62,650,000, AR 5,500,000, AP 1,650,000, Cash 50,550,000을 변경하지 않았습니다. T002 카드 사용 1,100,000과 T007 카드 결제 1,100,000의 기존 사람 승인 POSTED 전표를 source Transaction/Bank/Card 대사로 연결해 Card Payable 0을 검증했습니다. 작은 은행 명세만으로 전체 Golden cash를 0 차이로 위장하지 않았습니다.

서비스업 은행 3건, 소매업 은행 2건/카드매출·환불 2건은 원천 적재와 대상 거래 후보·사람 확정·미대사 잔액 0을 검증합니다. GL이 없는 원천은 차이를 보존합니다. 제조업 2025 은행 346건/법인카드 88건은 원천 수·정확한 Decimal 합계·source identity·provenance·retry 중복 0을 검증합니다. 기존 연간 회계 회귀는 별도로 실행하며 모든 연간 source를 자동 확정했다고 주장하지 않습니다.

공식 원천은 native Google Sheet 3개입니다. 추가 legacy `_v1.xlsm`은 MIME까지 확인했으며 공식 fixture로 사용/수정/삭제하지 않았습니다. [원본 metadata·스냅샷 SHA·fixture version](../../backend/tests/fixtures/reconciliation/README.md)을 보존했습니다.

## 발견·수정한 검사 실패

초기 테스트에서 카드매출을 법인카드 채무와 섞는 CHECK 오류를 발견해 MERCHANT/CORPORATE와 통제계정 role을 분리했습니다. Decimal 표기 차이에 따른 replay fingerprint 문제와 DRAFT를 target version에 포함한 자기 stale 문제도 수정했습니다. 초기 navigation expected 수와 Sandbox 빌드 권한 오류는 각각 실제 메뉴 수 반영과 승인된 운영 빌드로 해결했습니다. 브라우저에서 OWNER의 거래 생성 403은 기존 권한을 유지하고 ACCOUNTANT 작성으로 수정했으며, 선택 필드의 접근성 이름은 명시적으로 보강했습니다. 실패를 삭제/skip하지 않았습니다.

첫 전체 실행은 451 passed/1 skipped/1 failed(2953.14초)였고 실패는 unit의 오래된 head 013 기대값이었습니다. 014 단일 head/연결을 검증하도록 수정했습니다. 다음 전체 실행은 같은 Confirmed Import를 다른 카드로 재승격할 수 있는 경계를 발견해 중단했고 성공으로 집계하지 않았습니다. 회사 잠금 안에서 최초 계좌 연결을 검증하고 회귀를 추가한 뒤 전체를 다시 실행했습니다. 추가 보안 테스트의 기본 CSRF header 제거 오류와 명세 마감 테스트의 전표 source_type 누락도 각각 명시적인 빈 헤더와 기존 TRANSACTION 출처 계약으로 수정했습니다. 모두 production 권한이나 Accounting 규칙을 완화하지 않고 재검증했습니다. 최종 브라우저 재실행에서는 테스트 서버 시작 전 요청의 연결 종료가 있었으며 startup 완료 확인 후 전체 흐름을 다시 실행해 통과했습니다.

알려진 기능·성능 제한과 재사용 판정, 제외 범위는 [구현 계약](../accounting/bank-card-reconciliation.md)을 따릅니다. 다음 후보는 Closing V1이며 이 PR에는 포함하지 않습니다.
