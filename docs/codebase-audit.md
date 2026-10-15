# 저장소 코드·테스트 정리 기록

이 문서는 PR #19에서 수행한 저장소 전반의 정적·회귀 점검과 안전한 정리 범위를 기록한다. 전체 코드를 한 줄씩 수동 검토했다는 의미는 아니다. 설계 정본은 `AI_Accounting_Office_v0.2.6_통합설계_정본`, 구현 정본은 현재 GitHub main과 이 PR의 차이다.

## 점검 범위

- Backend `app` Python 409개와 `tests` 124개, Frontend `src` 71개와 `tests` 14개, `docs` 39개 파일의 구조를 조사했다.
- 전체 Backend Ruff·format·mypy·pip dependency 검사, 전체 Frontend 테스트 36개를 실행했다. PostgreSQL을 포함한 전체 Backend 테스트 결과는 아래 검증 결과에 별도로 기록한다.
- Repository 독립 `commit()` 호출, 회계 금액의 `float()` 계산, 업무 JSON/JSONB 유입, Accounting/Finance/Closing/Reporting에서 Agent SDK 직접 import를 검색했다. 이 정적 검색에서는 신규 위반을 확인하지 못했다.
- `TODO`/`FIXME`, skip/xfail, 자리표시 파일과 큰 모듈을 조사했다. PostgreSQL 환경이 없을 때 integration을 건너뛰는 fixture와 명시적으로 opt-in인 실 Gemini 테스트는 의도된 경계로 보존했다.

## 변경

- 은행·카드 단일 계좌 조회가 회사의 전체 계좌 목록을 먼저 읽던 경로를 회사·ID 조건의 단일 조회로 바꾸고, 목록·단건의 Domain 변환 코드를 공유했다.
- 월마감 검사에서 같은 회사의 은행 명세 목록을 두 번 조회하던 부분을 한 번의 조회 결과로 계산한다. 검사 순서와 digest 입력은 유지한다.
- 이미 구현 파일이 있는 디렉터리의 `.gitkeep`만 제거했다. 아직 비어 있는 향후 기능 디렉터리의 자리표시자는 보존했다.

## 보존한 경계

큰 파일이라는 이유만으로 Closing/Bank 대사 명령, 기존 migration, Golden fixture, 금융·회계 상태 전이를 분할하거나 재작성하지 않았다. 이 영역은 승인·잠금·원자성의 결합도가 높아 별도 설계·성능 근거 없이 이동하면 회귀 위험이 크다. 제거 여부가 증명되지 않은 public command·테스트 helper도 그대로 둔다.

## 검증 결과

- 전체 Backend Ruff·format·mypy·pip dependency 검사 통과.
- 전체 Frontend 테스트 **36 passed**, lint·typecheck 통과. 이전 PR 커밋의 production build 및 원격 CI 네 작업도 통과했다.
- 변경된 금융·월마감 경로의 PostgreSQL 통합 **23 passed**.
- 로컬 Windows에서 PostgreSQL 포함 전체 Backend 테스트를 실행했으나 약 30% 지점 이후 출력 없이 멈춰 중단했다. PostgreSQL 없이 다시 시작한 전체 실행도 초반에 멈췄다. 이 두 실행을 전체 통과로 기록하지 않는다. PR 최신 커밋의 Linux CI 결과를 별도로 확인한다.
- 별도 테스트 DB를 지정한 첫 집중 실행은 DB가 존재하지 않아 setup에서 실패했다. 기존 테스트 DB로 재실행해 위 23개가 통과했다.
