# PostgreSQL CI와 테스트 정리

2026-10-29 기준 전체 PostgreSQL 통합 테스트는 CI의 단일 작업에서 순차 실행되어 최근 main 실행에 약 20분이 걸렸다. 일반 PR과 main push에서는 `postgresql` 작업 하나로 Alembic upgrade/head, 스키마 정책, Decimal·UUID 저장, 전표 흐름, posting 동시성, Agent 읽기 경계와 seed 재실행을 검증한다. 통합 테스트 파일을 여러 작업으로 분할하지 않는다. 일반 CI의 목표 시간은 5분 이내이며 실제 시간은 PR #111의 최종 실행으로 확인한다.

전체 PostgreSQL 회귀는 GitHub Actions의 **Quality → Run workflow**로 수동 실행한다. 이 실행에는 모든 통합·Golden·동시성 테스트와 전체 Docker 환경 검사가 포함되며 느린 테스트 20개를 출력한다. 회계 핵심 경계를 바꾸거나 배포 전 전체 확인이 필요할 때 사용한다. Alembic의 `current`와 `check`를 반복 실행하던 부분은 하나씩 줄였고, 마지막 schema check와 seed 재실행 검사는 유지한다.

Migration 검사는 빈 DB에서 `base → head`, 최신 revision의 `downgrade → head`, metadata 일치와 관계형 스키마 정책을 검증한다. 오래된 revision마다 `head`까지 반복 왕복하던 검사는 제거했다. 과거 전체 revision 연결을 하드코딩한 단위 테스트도 제거했다. 이전 migration 파일을 수정하거나 재배포할 때는 해당 revision의 downgrade/upgrade를 별도로 검증한다.

도메인별 PostgreSQL 통합·Golden·동시성 테스트는 유지한다. 파일 수를 줄이기 위해 서로 다른 회계 불변식을 한 파일에 억지로 합치지 않는다.
