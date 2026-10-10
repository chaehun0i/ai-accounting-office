# 거래·전표·원장 검증 기록

검증일: 2026-10-10. 시작 main: `42368174ae85db110e9e2043d784e736d62544f1`. 작업 branch: `feat/transaction-journal-ledger`.

설계 정본은 [v0.2.5 통합설계](https://drive.google.com/drive/folders/14f9qJtr7eKzC12n8GpdHcNc3Ff2nyYpf)이며 [문서 지도](https://docs.google.com/document/d/18L_6SaI3IFzAzmhmKxxc3AIqMyx5-HUydoHQu31Zokg/edit)를 먼저 확인했다. 더 높은 유효 semantic version은 없었고 fallback은 사용하지 않았다. 원격 main 재확인 결과도 시작 SHA와 같았다.

## 실행 결과

| 영역 | 실제 실행 명령 | 결과 |
| --- | --- | --- |
| 전체 PostgreSQL 회귀 | `python -m pytest --require-postgres -q` | 257 passed, fail/skip 0, 1 warning (725.57초) |
| 기본 pytest | `python -m pytest -q` | 156 passed, 101 skipped, 1 warning (TEST_POSTGRES_URL 미설정에 따른 통합 검사 생략) |
| CI 비통합 검사 | `python -m pytest --ignore=tests/integration -q` | 156 passed, 1 warning |
| 수정 경계 재검증 | `python -m pytest tests/integration/test_journal_security.py tests/integration/test_migrations.py --require-postgres -q` | 4 passed, 1 warning |
| Backend lint | `python -m ruff check .` | 통과 |
| Backend format | `python -m ruff format --check .` | 309 files, 통과 |
| Backend type | `python -m mypy app` | 248 source files, 통과 |
| 의존성 | `python -m pip check` | No broken requirements found |
| Frontend 설치 | `npm ci --offline --ignore-scripts --no-audit --no-fund` | 123 packages 설치 성공 |
| Frontend lint | `npm run lint` | 통과, 경고 허용 0 |
| Frontend type | `npm run typecheck` | 통과 |
| Frontend test | `npm test` | 10 passed, fail/skip 0 |
| Frontend production | `npm run build` | 통과, `/` 및 not-found 정적 생성 |
| 스키마 실측 | `python scripts/verify_accounting_schema.py` | 통과, 아래 실측 수치 참고 |
| Git | `git diff --check` | 통과 |

Python 명령은 backend의 기존 `.venv`를 사용했다. 일반 pytest의 101개 skip을 PostgreSQL 검증 성공으로 간주하지 않는다. PostgreSQL 필수 전체 실행 결과를 별도로 기록한다.

경고 1개는 기존 Starlette TestClient의 httpx 사용 중단 예정 안내다. 이번 회계 로직 실패가 아니며 의존성 변경을 이번 범위에 섞지 않았다. 최초 전체 검사에서는 테스트의 멤버십 폐기 시각 누락과 개발 중 먼저 적용한 테스트 DB의 신규 인덱스 부재가 발견됐다. 테스트 입력을 보완하고 빈 전용 DB에서 다시 검증했다. 최초 npm 설치는 npm의 `Exit handler never called`로 종료되어 lockfile을 유지한 offline 설치로 재시도했다. 실패한 시도를 성공으로 계산하지 않는다.

## PostgreSQL migration과 스키마

기존 001~005 migration을 수정하지 않았다. 추가 revision은 `006_transactions → 007_journal_core → 008_governance`다.

별도 `accounting_cli_20261010_test`에서 다음 CLI를 순서대로 실행했다.

```text
python -m alembic current
python -m alembic upgrade head
python -m alembic current --check-heads
python -m alembic check
python -m alembic downgrade 005_onboarding_data_exchange
python -m alembic upgrade head
python -m alembic downgrade base
python -m alembic upgrade head
```

빈 DB에서 head 적용, 005↔head, base↔head가 모두 성공했다. 최종 head는 `008_governance`, metadata diff는 `No new upgrade operations detected`다. 통합 migration 테스트는 추가로 기존 001/002/003/004 경계를 왕복하고 재적용한다. 처음 CLI 연결이 일시적으로 실패한 뒤 같은 전용 DB의 연결을 확인하고 전체 순서를 재실행했다.

`public` schema에서 Alembic 관리 테이블을 제외한 실제 값:

| 항목 | 실측 |
| --- | ---: |
| 업무 테이블 | 53 |
| JSON 컬럼 | 0 |
| JSONB 컬럼 | 0 |
| FK constraint | 118 |
| 고아 FK 참조 row | 0 |

신규 테이블은 `transactions`, `journal_entries`, `journal_lines`, `journal_evidences`, `journal_proposals`, `opening_balance_imports`, `opening_balance_lines`, `approvals`, `audit_events`, `idempotency_records`다. 회사 복합 FK, 상태·금액·version CHECK, 회사별 전표번호 UNIQUE, 거래별 POSTED 전표 부분 UNIQUE, 회사·날짜 INDEX와 metadata 일치를 검사한다. 확정 헤더·분개·증빙 변경 및 감사 UPDATE/DELETE는 DB trigger로 차단한다.

Docker Compose `config --quiet`, `up -d --wait`, `ps`가 성공했다. PostgreSQL 17과 Redis 7 모두 healthy였다. 기존 개발 DB 대신 이번 작업의 전용 `_test` DB만 사용했다.

## 회계·보안·동시성

- Decimal/NUMERIC(19,4), 분개 한쪽 양수, 최소 두 분개, 정확한 차대변 균형, 활성 회사 계정, 열린 회계기간을 검증한다.
- 다른 회사 계정/전표/거래/증빙의 query와 FK 연결, 위조 출처, stale version, 제출 전 불균형, 본인 승인, 승인자 현재 권한 상실을 차단한다.
- 전표 작성·상태 명령·기초 전표 생성은 typed receipt를 사용한다. 같은 key/fingerprint replay와 다른 fingerprint conflict를 검증한다.
- 독립 PostgreSQL 연결의 동시 확정에서 서로 다른 전표는 `J-2026-000001`/`000002`, 같은 전표의 동시 중복 요청은 200/409다.
- 번호 발급 직후 강제 실패 시 전표 상태·version·승인 소비·번호가 함께 rollback되고 재시도 번호는 `000001`이다.
- 역분개는 원 전표를 수정하지 않는 새 초안이다. 별도 승인·확정 후 원장·시산표 기말 잔액을 상쇄한다.
- 기존 architecture guard와 JSON/JSONB schema guard를 유지했다. 신규 runtime에서 과거 프로젝트 식별자와 Repository 독립 commit을 추가하지 않았다. `.env`는 추적되지 않는다.

## 공식 2025 Golden

[native Google Sheet](https://docs.google.com/spreadsheets/d/1C_URD6dlROitLTmN6ZTAhBdebF0Dc3_bl3dzaIiXvA8/edit)의 SYN_MFG_001/가온푸드웍스 주식회사 기준을 재확인했다. 기존 macro 없는 export `sample-company-2025-v1.xlsx`의 SHA-256은 `c4df64f12fc517b73f1ef0c164bdeb541c1039a6c43d8ee3971310b414761d02`다. 원본과 버전 관리된 파생 fixture를 수정하지 않았다. `.xlsm`은 공식 fixture로 쓰지 않는다.

Golden은 기존 Master Application으로 2025 계정과목을 준비하고 온보딩 기초잔액 8개 계정을 전표로 전환한다. 별도 사람의 승인·확정 후 전표 합계 차변/대변 각각 **280,000,000.0000**, 계정별 원장 및 시산표를 Decimal로 비교한다. Import Evidence 추적과 중복 기초 전표 차단도 포함한다. 세무 값은 신고 정답이 아니다.

## 브라우저

새 전용 합성 DB `accounting_browser_final_test`와 최신 API 코드, Edge headless에서 `node scripts/accounting-browser-smoke.cjs --allow-synthetic`을 실행하여 통과했다. 로그인·접근 가능한 회사 선택, 거래 작성, 분개 추가/삭제와 합계, 제출·승인 요청, 다른 사용자 로그인·승인·장부 반영, 원장·시산표의 차대변 100.0000 및 전표 상세 이동을 검사했다. 원장과 시산표 응답이 독립적으로 도착하므로 각각의 완료를 기다린다. 최초 smoke의 조회 대기 문제를 수정한 뒤 최종 재실행이 성공했다.

이 브라우저 smoke는 정상 사용자 흐름이다. 기초잔액·역분개·권한 실패·롤백·동시성은 PostgreSQL API/Golden 자동 테스트에서 별도로 검증하며, 모든 오류 조합을 브라우저로 검증했다고 주장하지 않는다. 상세 실행 환경과 옵션은 [회계 구조 문서](transaction-journal-ledger.md)에 있다.

## 알려진 제한과 후속 계약

- 단일 기능통화 KRW이며 외화·분할 인식·결산·재무제표는 제외한다.
- Import는 원본 접수 정본을 유지하고 자동 Transaction promotion worker는 아직 없다.
- 거래·전표 목록은 날짜 범위에서 최대 500개이며 cursor pagination은 아직 없다. 원장·시산표는 POSTED 분개를 조회 시 계산한다.
- 사람 Proposal은 현재 전표 초안의 관계형 분개·증빙을 공유한다. Agent용 proposal line과 runtime은 만들지 않았다.
- 반려 전표 재편집/기간 재개방 명령은 열지 않았다. 수정은 새 초안과 별도 승인·역분개로 처리한다.
- Opening Balance는 회계 Master가 준비된 회사에서 스냅샷·초안·승인·확정을 거친다. Asset/Inventory/AR/AP 전체 및 Tax 승격은 제공하지 않는다.
- 후속 Domain은 company-scoped Transaction/POSTED Journal/Evidence FK와 Application/UoW를 사용한다. 잔액 직접 수정이나 generic JSON 저장을 도입하지 않는다.

기존 외부 프로젝트 코드를 COPY/ADAPT하지 않았으며 회계 엔진은 NEW다. 현재 저장소의 UoW·RBAC·Sequence·Intake/Evidence·Onboarding 계약을 재사용했다. 개발 도구나 업종 시뮬레이션 Domain을 가져오지 않았다.
