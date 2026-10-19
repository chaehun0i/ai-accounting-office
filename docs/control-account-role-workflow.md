# 회사 Control Account 역할 변경 업무

## 정본과 경계

활성 v0.2.6 설계의 Accounting Policy·COA, Permission Matrix, Physical ERD, Error/Idempotency/Concurrency Contract와 최신 main의 계정 관리 계약에 맞춘다. Drive에서 복사한 원본 설계 폴더는 읽기 전용이며 Git에 포함하지 않는다. 일반 계정 수정·비활성화는 Control Account 역할을 바꾸지 않는다.

회사별 관계형 정본 `control_account_mappings`는 `AR`, `AP`, `TAX_INPUT`, `TAX_OUTPUT`, `BANK_CASH`, `CARD_CLEARING`, `CARD_PAYABLE`을 계정 ID로 명시한다. 계정명으로 역할을 추정하지 않는다. 버전이 고정된 기본 템플릿 계정은 명확한 역할만 seed하며, 카드 미수처럼 유일한 기본 계정이 없는 역할은 비워 둔다. 이전 회사의 명시적 BANK/CARD 표식도 회사 안에서 유일한 경우에만 Alembic 020으로 이관한다.

## 신청과 영향검사

`GET /control-account-roles`는 현재 역할과 매핑 버전을 보여준다. `POST /control-account-roles/impact`는 신청 전 역할·대상 계정·기대 매핑 버전·기대 계정 버전을 받아 deterministic facts, 차단 여부, SHA-256 digest를 반환한다. `POST /control-account-roles/requests`는 같은 값을 `Idempotency-Key`와 함께 받아 신청 당시 현재·대상 계정, 두 버전, 역할, digest, 요청자를 고정한다. 같은 키와 같은 입력은 원 요청을 재생하며, 다른 입력은 `IDEMPOTENCY_CONFLICT`를 반환한다. 차단된 신청은 `CONTROL_ACCOUNT_PROTECTED`다.

영향검사는 회사 범위에서 현재와 대상의 POSTED 전표, AR/AP 참조, 은행·카드 계정 참조를 세고 계정 활성·전기 가능·자산/부채 유형과 다른 역할 충돌을 확인한다. 참조가 있는 현재 역할을 다른 계정으로 옮기는 신청은 차단한다. 현재 구현에 직접 계정 FK가 없는 Tax 업무는 근거 없는 참조를 만들어 안전하다고 표시하지 않는다. Tax 전표에 실제로 쓰인 계정은 POSTED 전표 사실에 포함된다.

매핑된 계정은 일반 계정 수정·비활성화 API에서도 `CONTROL_ACCOUNT_PROTECTED`로 차단한다. 저장소의 참조 검사에도 관계형 매핑 FK를 포함해 계정 보호 경로를 일치시킨다.

## 독립 승인과 실행

`POST /control-account-roles/requests/{id}/approve`, `/reject`, `/execute`는 별도 `control_account.manage` 권한을 요구한다. 거절에는 사유가 필요하다. 신청자는 자기 신청을 승인하거나 실행할 수 없다. 승인과 실행은 회사 행·요청 행을 잠그고 매핑 및 대상 계정 버전, 최신 영향 facts·digest를 다시 계산한다. 하나라도 바뀌면 기존 승인을 소비하지 않는다. 실행은 매핑 변경, 요청 상태, 실행 키, 전후 이벤트를 한 Unit of Work에서 커밋한다. 같은 실행 키로 같은 요청을 재시도하면 적용 결과를 돌려준다. `GET /control-account-roles/requests/{id}/events`는 관계형 감사 이력을 보여준다.

모든 조회·명령은 `X-Company-ID`와 회사 멤버십으로 범위를 제한한다. 타 회사 요청 ID는 404로 숨기고, 접근 가능한 회사에서 권한이 없으면 403이다. 상태 변경 API는 CSRF 검증을 적용한다. OWNER는 자기 회사의 모든 등록된 권한을 가지지만 다른 회사에는 접근할 수 없다. ADMIN은 명시된 `control_account.manage` 권한으로 승인할 수 있다.

## 설정 화면과 검증

설정 관리 → 계정과목에서 현재 역할, 대상 선택, 신청 전 영향검사, 신청, 다른 권한자의 승인·거절, 실행 결과와 전후 이력을 볼 수 있다. 회사 변경 시 선택·요청 상태를 초기화한다. 실행 뒤 최신 매핑·영향·이력을 다시 조회한다.

Alembic 020, 직접 관련 PostgreSQL core 및 승인 통합, 기존 채권·채무 정산 최소 subset, Ruff·format·mypy, frontend lint·typecheck를 확인했다. Docker backend/frontend를 재빌드해 health와 요청 로그를 확인하고 Playwright MCP로 OWNER 신청 → 다른 ADMIN 승인 → 실행을 직접 수행했다. 전체 Golden·연간 fixture·브라우저 E2E 묶음은 이번 변경 때문에 추가 실행하지 않았다.
