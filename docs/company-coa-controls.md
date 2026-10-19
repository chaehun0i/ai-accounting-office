# 회사 계정과목 변경 구현 범위

## 기준과 범위

활성 설계의 `Accounting_Policy_COA_기초잔액_전표번호`, `Physical_ERD_PostgreSQL_DDL_SQL`, `API_Pydantic_Contract`, `Permission_Matrix_RBAC`, `Implementation_DoD_Review_Checklist`를 현재 `main`의 계정과목 구현과 대조했다. 가져온 설계 정본 DOCX와 Sheet는 변경하지 않는다.

이번 변경은 회사가 직접 추가한 **아직 참조되지 않은** 계정의 코드·이름 수정과 비활성화, 변경이력을 제공한다. 기존 `POST /accounts`, `GET /accounts`와 전표·원장 계산을 재사용한다. DB는 Alembic 019에서 관계형 `account_changes` 테이블을 추가한다. 변경마다 회사·계정·수행자, 작업, 이전/이후 코드·이름·상태·버전, 사유, 시각을 같은 트랜잭션에 기록한다.

## 명령과 권한

| API | 입력 | 권한 | 결과 |
| --- | --- | --- | --- |
| `PATCH /accounts/{id}` | `expected_version`, `account_code` 또는 `account_name` | `account.update` | 변경된 계정 |
| `POST /accounts/{id}/deactivate` | `expected_version`, `reason` | `account.deactivate` | 비활성 계정 |

두 명령 모두 `X-Company-ID`, 인증 및 CSRF를 검증한다. 리소스 조회는 회사 범위로 제한하며 다른 회사 계정은 404다. 현재 OWNER·ADMIN·ACCOUNTANT에게 두 쓰기 권한을 부여한다. 오래된 버전, 중복 코드, 이미 비활성인 계정, 원본 템플릿 계정 및 Control Account 변경은 409로 거부한다. 사용 이력이 있거나 부모 계정·채권채무·은행카드·보고서 매핑으로 참조되는 계정의 수정·비활성화도 409다. 계정 삭제 API는 없다.

변경 명령은 대상 계정 row를 잠근 뒤 참조와 버전을 검사한다. 전표 확정과 같은 계정 참조 생성이 동시에 진행돼도 이미 사용된 계정을 변경하지 않도록 같은 트랜잭션에서 판정한다.

`GET /accounts`와 명령 응답은 `control_account_type`, `status`, `version`을 반환한다. 설정 화면은 권한이 있을 때 회사 추가 계정의 수정·비활성화 버튼을 보여준다. 버전 충돌 시 최신 목록을 다시 읽고 재시도를 안내한다. 회사 변경 시 목록과 편집 상태를 초기화한다.

## 검증과 제한

별도 PostgreSQL 테스트 DB에서 계정 변경·감사 이력, 버전 충돌, 회사 격리, 템플릿·참조·Control Account 보호, 기존 계정/보고기간 회귀를 확인한다. Alembic upgrade/check와 스키마 검사에서 019 head, JSON/JSONB 0개, FK orphan 0개를 확인한다. 전체 compose를 새 이미지로 빌드해 백엔드·프론트엔드 health를 확인한다.

일반 계정 PATCH는 Control Account 역할을 변경하지 않는다. 역할 변경은 아래의 독립 신청·승인 절차를 따른다. 기존 전표 전용 승인 저장소는 재사용하지 않는다.

## Control Account 역할 변경 신청 (Alembic 020)

역할 매핑의 관계형 정본은 `control_account_mappings`다. 회사별 `AR`, `AP`, `TAX_INPUT`, `TAX_OUTPUT`, `BANK_CASH`, `CARD_CLEARING`, `CARD_PAYABLE`을 조회한다. 매핑이 없으면 계정 ID는 `null`, 버전은 `0`이다. 계정명은 역할 판정에 사용하지 않는다. 기존 회사의 BANK/CARD 역할은 명시된 `control_account_type`이 회사 내 해당 역할에 하나뿐일 때만 이관한다. AR/AP/Tax 등의 기본 역할은 버전이 고정된 계정 템플릿 ID와 코드로 seed한다. 애매한 CARD_CLEARING은 자동 지정하지 않는다.

`GET /control-account-roles`는 현재 역할을 보여준다. `POST /control-account-roles/impact`는 신청 전 대상, 역할, mapping/account 예상 버전을 받아 deterministic 영향 facts와 SHA-256 digest, 차단 여부를 반환한다. `POST /control-account-roles/requests`는 동일 입력과 `Idempotency-Key`로 신청한다. `GET /control-account-roles/requests`, `GET /requests/{id}`, `GET /requests/{id}/impact`는 요청과 현재 영향 상태를 조회한다. 모두 `X-Company-ID`로 범위를 제한한다. 신청·영향 확인에는 `control_account.manage`가 필요하며 상태 변경에는 CSRF 검증이 적용된다.

신청은 현재 계정 ID, 대상 계정 ID와 버전, mapping 버전, 요청자, 영향 digest를 `control_account_requests`에 고정하고 REQUESTED 이벤트를 `control_account_events`에 기록한다. 같은 키와 같은 payload를 재시도하면 원 요청을 돌려준다. 같은 키로 다른 payload를 보내면 `IDEMPOTENCY_CONFLICT`다. POSTED 전표, AR/AP, 은행·카드의 실제 계정 참조를 세어 영향 facts에 포함한다. 기존 role 계정이 참조되거나 대상이 비활성·전기 불가·유형 불일치·다른 role과 충돌하면 `CONTROL_ACCOUNT_PROTECTED`로 신청을 막는다. 현재 구현에 계정 직접 FK가 없는 Tax 참조는 안전하다고 추정하지 않고 해당 지원 범위가 없음을 유지한다.

이 단계에서는 승인을 소비하거나 매핑을 실행하는 API를 열지 않는다. 별도 승인, 실행 직전 최신 영향 재검증, 감사 결과 조회 및 설정 UI는 이슈 #62의 후속 검토 범위다.
