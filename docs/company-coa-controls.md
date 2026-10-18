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

**Control Account Role Mapping은 이번 API에 포함하지 않는다.** 활성 설계는 별도 승인과 영향검사를 요구한다. 기존 승인 저장소는 전표 FK가 필수라 COA 명령에 재사용할 수 없다. 신청·별도 승인·실행 경로가 생기기 전까지 계정명으로 역할을 추정하거나 일반 PATCH로 역할을 바꾸지 않는다. 이 남은 완료 조건은 이슈 #29 및 #62에서 추적한다.
