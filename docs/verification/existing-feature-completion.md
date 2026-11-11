# 기존 회계 기능 점검과 보완

2026-11-12. 사용자 확인에 따라 신규 자산·재고·세무 Domain 구현보다 기존 지원 기능의 결함·누락을 우선한다. 기준 main은 `80da1c0e680f37597dfa50ba3c6bf7c56c753b03`이다.

## 수정한 항목

- 전표 승인 대상·생성 멱등성과 마감 원천의 typed digest 직렬화 3곳을 core 함수로 통합했다. 이전 해시 값과 Decimal 표현을 보존한다. [호환성 검증](digest-consolidation.md).
- BS/IS 생성·계정 매핑의 늦은 완료/실패가 새 기간의 Snapshot·오류·busy 상태를 덮어쓰던 경로를 차단했다. 기간을 나갔다 돌아와도 이전 요청을 재사용하지 않는다.
- BS/IS 원천 항목 연속 선택 및 제표 종류·Snapshot 변경 시 이전 원천 응답을 폐기한다. 비교 화면의 기존 RequestScope를 재사용한다.
- 기간별 Snapshot 이력을 다시 읽는 동안 이전 이력을 지우고, 원천 조회 중에는 빈 결과 대신 조회 상태를 표시한다. 실패를 원천 전표 0건으로 표시하지 않는다.

## 유지한 경계

CF/SCE/Notes의 기존 요청 격리와 회사별 조회, Notes의 현재 원천·독립 승인, 비교 Snapshot 승인, Report Center의 회사별 권한·완료 Artifact SHA-256 검사를 확인했다. 기존 회계 기능을 새 모듈로 복제하지 않았다. 입력 schema가 다른 거래처 수정/상태 라우터와 보안 token digest는 합치지 않는다.

설계와 구현을 대조했을 때 SCE의 물리적 hard-close/IS 표시 계약은 여전히 #112의 미지원 범위다. `PROFIT_TRANSFER_IS_MISMATCH`를 제거하거나 차액을 보정하지 않는다. 전체 재무제표 세트 승인은 Notes·비교 승인과 별도 후속 기능이다. 이 점검은 해당 신규 기능 구현이나 저장소 모든 줄의 무결성 증명을 뜻하지 않는다.

## 검증

단위 10건, 전표·마감 PostgreSQL 11건, frontend 60건 및 lint/typecheck, 변경 Python Ruff/mypy가 통과했다. frontend 검증은 상태 제어·모델 테스트이며 실제 브라우저 전체 E2E는 실행하지 않았다. SCE·Notes·비교·Report Center 집중 PostgreSQL 8건도 통과했다(101.29초). 전체 Golden·전체 PostgreSQL·실고객 Pilot·운영 Release Gate는 이번 점검 범위 밖이다.

PR #127의 digest 통합이 먼저 병합되어, BS/IS 화면·테스트·이 문서는 최신 main 96c632e 기준 후속 PR로 분리했다. 실제 merge는 사용자가 수행했으며 이 작업에서는 merge하지 않았다.

