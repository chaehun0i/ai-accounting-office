# 월마감 V1 검증 기록

설계 정본은 Google Drive `AI_Accounting_Office_v0.2.6_통합설계_정본`이며 fallback과 Archive는 사용하지 않았다. 구현 시작 시 `origin/main`은 PR #14 병합 커밋 `f1915db34688e6dc41b46f0db08ef8a843e41520`, Alembic head는 `014_bank_card_reconciliation`이었다. PR #14의 은행/카드 대사는 재구현하지 않았다.

## 재사용 판정

현재 저장소의 Journal Proposal·Approval·Posting·Reversal, Trial Balance, AR/AP↔GL 및 Bank/Card 대사 Application을 **ADAPT**했다. 외부 `nobadai/mainproject`의 일일 simulation closing은 마감 전 불일치 차단과 단일 거래 경계라는 **PATTERN**만 참고했다. 금액·기간·simulation state·직접 SQL 구현의 **COPY**는 없고, `sim_run_id`, `finance_state_id`, `financing_mode`, `daily_closings`는 **DROP**했다.

## 현재 확인된 검증

| 검증 | 결과 |
| --- | --- |
| 결산 단위·API 계약·아키텍처 검사 | 30 passed |
| 결산 PostgreSQL 동시성·워크플로 | 10 passed |
| `SYN_RETAIL_001` native 카드 원천 결산 차단 | 1 passed |
| 014 → 015 forward upgrade 및 Alembic metadata check | 통과 |
| 빈 PostgreSQL의 baseline → 015 upgrade | 통과 |
| 업무 스키마 검사 | 94 tables, 274 FK, JSON 0, JSONB 0, orphan 0 |
| Ruff check / format, mypy | 통과 |
| pip check | 통과 |
| Frontend Linux 컨테이너 빌드 | 통과, `/closing` route 생성 |
| Frontend Linux 컨테이너 lint / typecheck / test | 통과 / 통과 / 32 passed |
| Docker Compose config / up --wait | 통과, PostgreSQL·Redis·backend·frontend healthy |
| 로컬 PostgreSQL Alembic current --check-heads / check | `015_period_closing` / metadata 차이 없음 |

위 수치는 각각 별도의 실행 결과다. PostgreSQL 테스트는 이름이 `_test`로 끝나는 격리 DB에서 실행했다. 실제 Gemini 네트워크 호출은 수행하지 않았다. 결산 판단에는 LLM을 사용하지 않는다.

전체 PostgreSQL `pytest --require-postgres` 실행은 별도로 진행 중이며 이 문서의 개별 통과 건수에 합산하지 않는다. 완료 전에는 전체 회귀 통과로 표시하지 않는다.

## Fixture와 한계

`GOLDEN_CORP_001`의 장부 기준값을 수정하지 않았다. 서비스업 은행 원천 차단, 소매업 native 카드 원천 차단, 2025년 12개 기간 이력을 PostgreSQL 테스트에서 확인했다. `SYN_RETAIL_001` 및 `SYN_MFG_001` 원본 Sheet를 변경하지 않았다. 공식 회귀 원천은 세 개의 native Google Sheet이며 `_v1.xlsm`은 legacy/raw 파일이다. 현재 테스트의 연간 결산 입력은 기존 결정론적 adapter를 사용하며, 원본 Sheet 전체를 월별로 새로 가져와 결산하는 경로는 포함하지 않는다.

브라우저에서 새 로컬 검증 계정·회사를 생성하고 월마감 화면의 회사별 메뉴와 회계기간 없음 상태를 확인했다. 기간 생성 저장은 자동 승인 검토가 2026년 기본값과 2025년 회귀 자료의 불일치 위험을 이유로 거절했다. UI의 2025년 입력도 기존 `min=2026` 제약에 걸려, DB 제약과 일치하도록 `min=1900`으로 수정했다. 거절된 브라우저 저장 동작은 재시도하지 않았다. 따라서 브라우저의 시작→조정→승인→마감 전체 시나리오는 아직 통과했다고 주장하지 않는다. PostgreSQL API 통합 테스트는 별도로 결산 전 과정을 검증한다.

Windows 호스트의 `npm ci`는 진행이 지연되어 완료되지 않았다. 같은 lock 파일의 `npm ci`를 캐시한 Linux Docker 빌드 단계에서 빌드·lint·typecheck·test를 검증했다. `docker compose exec backend python -m alembic ...`는 Compose 환경값인 호스트용 `localhost` DB 주소를 그대로 받아 실패한다. 실행 중인 API는 기존 `docker-entrypoint.py`가 내부 서비스 주소로 변환한 뒤 migration과 seed를 적용한다. Compose 환경값 자체를 바꾼 임시 수정은 비밀번호 URL 인코딩을 보존하기 위해 되돌렸다.

마감은 재고·자산·원가·세무 엔진의 부재를 필수 차단 조건으로 사용하지 않는다. 자동 역분개는 다음 기간에 기존 Reversal 명령으로 DRAFT를 만들며, 승인 없는 자동 Posting은 수행하지 않는다. BS/IS 실제 스냅샷은 다음 범위다.
