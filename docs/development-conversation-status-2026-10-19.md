# Control Account Role Mapping 작업 인수인계 — 2026-10-19

이 문서는 PR #65–#67의 확인된 작업 상태와 병합 경계를 기록한다. 실제 병합 여부와 CI의 최신 값은 GitHub PR을 다시 확인한다. 이 문서는 `docs/AI_Accounting_Office_v0.2.6_통합설계_정본/`의 Drive 복사 설계 정본이 아니다.

## 현재 확인 상태

- [PR #65](https://github.com/chaehun0i/ai-accounting-office/pull/65): `fix/company-owner-observability` → `main`, 병합 완료. 자기 회사 OWNER의 등록 permission 전체 사용, 회사 격리, 프론트·백엔드 요청 로그, favicon과 관련 테스트를 포함한다. `Closes #64`; #64는 닫혔다.
- [PR #66](https://github.com/chaehun0i/ai-accounting-office/pull/66): `feat/control-account-role-mapping` → `main`, 열림. 7개 Control Account 역할의 관계형 매핑, 명시적 template identity 기반 초기 매핑, 영향검사, 변경 신청, 멱등성, 계정 보호와 AR/AP의 명시적 매핑 사용을 포함한다. `Refs #62`, `Refs #29`.
- [PR #67](https://github.com/chaehun0i/ai-accounting-office/pull/67): `feat/control-account-role-approval` → `feat/control-account-role-mapping`, 열림. 신청자와 승인자 분리, 승인·거절·실행, stale version/digest 차단, 동시성·중복 실행 보호, 관계형 감사와 설정 UI를 포함한다. #66이 병합된 뒤 `main`으로 base를 변경해야 한다. `Closes #62`; #29는 실제 잔여 완료조건 확인 후에만 닫는다.

## 검증과 병합 경계

- 2026-10-19 확인 시 #65·#66·#67의 GitHub backend/frontend/infrastructure/scope/PostgreSQL 체크는 모두 성공했다. #66·#67은 mergeable이었다. 새 push 또는 base 변경 후에는 해당 체크를 다시 확인한다.
- Docker Compose의 backend/frontend/PostgreSQL/Redis는 모두 healthy였다. #67의 OWNER 신청 → 별도 ADMIN 승인 → 실행 → 현재 매핑·감사 이력 확인과 브라우저 console error 0건은 PR 설명에 기록된 이전 검증이다. 이번 문서 정리에서는 브라우저를 다시 실행하지 않았다.
- 권장 병합 순서는 현재 열린 PR 기준 **#66 → #67**이다. 이 문서 작성 과정에서 PR을 직접 병합하거나 auto-merge를 설정하지 않았다.
- Drive 복사 설계 정본은 로컬 읽기 전용 자료이며 두 PR의 diff와 이 문서의 commit에 포함하지 않는다.

## 남은 절차

1. #66의 `main` base와 CI 성공, diff 범위를 확인한 뒤 사람이 병합한다.
2. #66 병합 후 #67의 base를 최신 `main`으로 변경하고 diff·CI·PostgreSQL·mergeability를 재확인한다.
3. #67 완료 시 #62를 닫고, #29는 모든 잔여 조건을 확인한 경우에만 닫는다.
