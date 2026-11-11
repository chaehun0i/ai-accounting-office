# 전표·마감 digest 중복 통합

2026-11-12, main `80da1c0e680f37597dfa50ba3c6bf7c56c753b03` 기준.

전표 승인 대상, 생성 멱등 fingerprint, 마감 원천에서 반복하던 typed value 직렬화를 `core.digests.value_digest`로 모았다. UUID·날짜·Decimal 문자열 변환과 canonical JSON SHA-256 순서를 보존한다. 전표가 Intake 모듈에서 digest를 가져오던 의존성은 core 직접 참조로 바꿨다. 저장된 digest나 Snapshot을 재작성하지 않는다.

금액의 소수점 표현, 한글, timezone, tuple, null, dict 순서에 대한 이전 알고리즘 호환성을 확인했다. 기존 plain digest와 보안 token digest는 용도가 달라 합치지 않았다. 같은 구현처럼 보이는 거래처 수정·상태 라우터도 입력 schema가 달라 유지했다.

검증: 단위 10건, 실제 Docker PostgreSQL의 전표·마감 integration 11건 통과(151.90초), Ruff 및 변경 Application 3개 파일 mypy 통과. 전체 회귀·Release Gate는 미실행. 이 정리는 전체 잔여 제품 기능 완료를 뜻하지 않는다.
