# PostgreSQL CI와 테스트 정리

2026-10-29 기준 전체 PostgreSQL 통합 테스트는 CI의 단일 작업에서 순차 실행되어 최근 main 실행에 약 20분이 걸렸다. 사용자 피드백에 따라 작업 분할과 추가 PostgreSQL 작업은 제거했다. `postgresql` 검사 하나에서 전체 통합 테스트를 실행한다.

CI는 전체 실행에서 느린 테스트 20개를 출력해 병목을 확인한다. Alembic의 `current`와 `check`를 반복 실행하던 부분은 하나씩 줄였고, 마지막 schema check와 seed 재실행 검사는 유지한다. 빠른 PR 경로의 Agent 읽기 통합 테스트도 유지한다.

Migration 검사는 빈 DB에서 `base → head`, 최신 revision의 `downgrade → head`, metadata 일치와 관계형 스키마 정책을 검증한다. 오래된 revision마다 `head`까지 반복 왕복하던 검사는 제거했다. 과거 전체 revision 연결을 하드코딩한 단위 테스트도 제거했다. 이전 migration 파일을 수정하거나 재배포할 때는 해당 revision의 downgrade/upgrade를 별도로 검증한다.

도메인별 PostgreSQL 통합·Golden·동시성 테스트는 유지한다. 파일 수를 줄이기 위해 서로 다른 회계 불변식을 한 파일에 억지로 합치지 않는다.
