# 서비스 생존과 회계 DB 준비 상태

`GET /health`는 프로세스 생존 확인이며 외부 연결을 하지 않는다. `GET /ready`는 PostgreSQL 연결과 배포 코드의 Alembic head를 실제 DB revision과 비교한다. Docker backend healthcheck는 `/ready`를 사용한다. migration 실행이나 데이터 수정은 readiness의 책임이 아니다.

| HTTP | reason_code | 의미 |
| --- | --- | --- |
| 200 | READY | DB 연결 및 migration head 일치 |
| 503 | DATABASE_UNAVAILABLE | DB 접속 또는 조회 실패 |
| 503 | MIGRATION_UNAVAILABLE | 접속 후 migration metadata 조회 실패 |
| 503 | MIGRATION_MISMATCH | 빈 revision, 이전 revision 또는 추가 head |

조회는 읽기 전용 트랜잭션에서 수행하고 statement timeout은 2초다. 연결 timeout과 pool 대기는 각각 5초이며, 전체 HTTP 요청의 엄격한 5초 제한을 뜻하지 않는다. 응답에는 SQL·접속정보·실제 schema revision을 노출하지 않고 `Cache-Control: no-store`를 적용한다. LLM은 `not_probed`, Redis는 현재 core 경로에서 `not_required`로 표시한다. 이 응답은 외부 서비스 정상 동작이나 전체 회계 기능 통과를 증명하지 않는다.

2026-11-12 검증: 로컬 Docker PostgreSQL의 격리 DB `accounting_pilot_test`에서 readiness와 migration lifecycle 2건 통과. liveness 유지, 오류 비밀정보 비노출, 빈/과거/추가 head 차단을 포함한 단위·DB 오류 계약 6건 통과. Ruff/format 및 변경 Application 파일 mypy 통과. 신규 migration은 없고 head는 `034_statement_comparatives`다. 전체 PostgreSQL 회귀·전체 Compose·실제 운영 배포는 이 검증 범위에 포함하지 않는다.

설계 정본의 운영 복구 목표는 RPO 15분 이하, RTO 4시간 이하 및 월간 복원 훈련이다. 기존 로컬 복원 시험은 운영 목표 충족 증명이 아니다. DB와 파일의 일관 백업, 오프사이트 보존, 운영 측정 및 독립 담당자 sign-off가 남아 있다.
