# 기존 프로젝트 활용 근거

COPY한 파일은 **0개**입니다. 기존 history를 merge/subtree로 가져오지 않았습니다. 아래 실제 source를 고정 commit에서 읽고 개념만 새 PostgreSQL/UUID/UoW 계약으로 작성했습니다. 원본 내려받은 검토 자료는 Git에서 제외된 `.local/source-review`에만 있습니다.

- CommitLens `chaehun0i/gitproject`: `afa35ed6a2f08b3835a4508111c83e08105db62d`
- WITH ESG `shell-files/dev_skm`: `720e33c7923a679c2cff694ca12c9f92646ed06b`
- 우선 설계: **AI_Accounting_Office_v0.2.3_통합설계_구현보강**. ServIQ/햇들농산 Domain은 참조·이식하지 않았습니다.

## Source file → 신규 책임

| 실제 출처 | 분류 | 신규 파일·책임 | 참고와 제거·변경 |
| --- | --- | --- | --- |
| [CommitLens apis/auth.py](https://github.com/chaehun0i/gitproject/blob/afa35ed6a2f08b3835a4508111c83e08105db62d/backend/src/apis/auth.py) | PATTERN | backend/app/identity/auth/api/router.py | router→service, endpoint 책임 분리. /signup과 기존 response를 제거하고 /auth/register, logout-all, 신규 typed 계약 사용 |
| [services/auth_service.py](https://github.com/chaehun0i/gitproject/blob/afa35ed6a2f08b3835a4508111c83e08105db62d/backend/src/services/auth_service.py) | ADAPT | backend/app/identity/auth/application/service.py | access/refresh 분리와 expiry/hash 검증 개념. MariaDB/int ID/HTTPException/Redis 필수/JWE 고정을 제거. UUID 가족 계보·ROTATED·reuse 가족 폐기로 재설계 |
| [repositories/refresh_session_repository.py](https://github.com/chaehun0i/gitproject/blob/afa35ed6a2f08b3835a4508111c83e08105db62d/backend/src/repositories/refresh_session_repository.py) | PATTERN | backend/app/identity/sessions/infrastructure/repository.py | hash와 session lookup. raw SQL placeholder/utils.db/독립 save/UTC_TIMESTAMP/JTI 원문을 제거. SQLAlchemy/UoW/jti_hash/history 사용 |
| [repositories/user_repository.py](https://github.com/chaehun0i/gitproject/blob/afa35ed6a2f08b3835a4508111c83e08105db62d/backend/src/repositories/user_repository.py) | PATTERN | backend/app/identity/users/infrastructure/repository.py | 이메일/ID 조회와 생성 분리. raw SQL/int ID/global transaction/Repository commit 제거. Identity Control Plane 조회만 명시적 예외로 사용 |
| [utils/rediscl.py](https://github.com/chaehun0i/gitproject/blob/afa35ed6a2f08b3835a4508111c83e08105db62d/backend/utils/rediscl.py) | ADAPT 분석, runtime 미채택 | backend/app/identity/sessions/infrastructure/repository.py | namespace/TTL 개념 검토. Redis session dict JSON과 필수 가용성 의존을 제거. 이번 구현은 PostgreSQL session/security event만 사용하며 Redis adapter를 불필요하게 만들지 않음 |
| [core/security.py](https://github.com/chaehun0i/gitproject/blob/afa35ed6a2f08b3835a4508111c83e08105db62d/backend/core/security.py) | ADAPT/PATTERN | backend/app/core/security.py | constant-time 비교/random identifier/token hash/expiry 분리. 자체 PBKDF2 format·iteration/JWE 복사 없이 argon2-cffi/PyJWT로 신규 구현 |
| [models/auth.py](https://github.com/chaehun0i/gitproject/blob/afa35ed6a2f08b3835a4508111c83e08105db62d/backend/src/models/auth.py) | DROP/PATTERN | backend/app/identity/auth/api/schemas.py | Request/Response 분리만 참고. 공통 AuthRequest/int ID/camelCase/default developer role 제거. Register/Login/Read/Result 및 extra=forbid 사용 |
| [ESG hooks/AuthContext.jsx](https://github.com/shell-files/dev_skm/blob/720e33c7923a679c2cff694ca12c9f92646ed06b/frontend/src/hooks/AuthContext.jsx) | PATTERN/ADAPT | frontend/src/features/auth/auth-provider.tsx; features/companies/company-provider.tsx | session recovery/준비 상태/회사 하나 자동 선택. localStorage 인증 정본/전체 선택 객체 저장/React Router/Redux 중복/role 직접 검사/ESG report state 제거. 인증과 회사 context 분리 |
| [homes/logins/CompanySelect.jsx](https://github.com/shell-files/dev_skm/blob/720e33c7923a679c2cff694ca12c9f92646ed06b/frontend/src/homes/logins/CompanySelect.jsx) | ADAPT | frontend/src/features/companies/components/company-selector.tsx | 회사 목록/이름 검색/선택/완료/실패 안내. integer ID/POST company/alert/CSS브랜드/전체 HTTP helper import 제거. Next.js UUID와 서버 재검증 사용 |
| [models/model.py](https://github.com/shell-files/dev_skm/blob/720e33c7923a679c2cff694ca12c9f92646ed06b/backend/src/models/model.py) | ADAPT/DROP | backend/app/companies/api/schemas.py; companies/domain/entities.py | 회사명·등록번호·개업일·주소 개념. int 사업자번호/ESG industry/role/license/taxName/거대 signup을 제거. string 사업자번호와 UUID, Tax Profile 분리 |
| [repositories/companycontextrepository.py](https://github.com/shell-files/dev_skm/blob/720e33c7923a679c2cff694ca12c9f92646ed06b/backend/src/repositories/companycontextrepository.py) | DROP | 대응 복사 파일 없음 | 실제 merge conflict marker와 ESG context/JSON 저장 구조를 확인. 재사용하지 않고 companies/infrastructure/repository.py를 신규 회사 scope 계약으로 작성 |

CommitLens [docs/current-status.md](https://github.com/chaehun0i/gitproject/blob/afa35ed6a2f08b3835a4508111c83e08105db62d/docs/current-status.md)도 읽어 기존 인증의 상태와 검증 한계를 확인했습니다. 기존 검증 결과를 신규 프로젝트의 테스트 성공으로 간주하지 않았습니다.

## 실제 충돌과 해결

1. CommitLens는 매 refresh마다 JTI를 새로 발급하고 기존 session을 revoke하지만 session_family_id/rotated_at/reuse 계보가 없습니다. v0.2.3대로 원본 row를 ROTATED로 유지하고 가족 UUID를 계승하며 reuse event+가족 폐기를 하나의 UoW로 보존했습니다.
2. 기존 Redis live state가 없으면 refresh가 실패합니다. v0.2.3은 PostgreSQL이 영구 정본이므로 Redis 필수 의존을 제거했습니다. 향후 cache를 추가하더라도 PostgreSQL 이력을 대체할 수 없습니다.
3. MariaDB integer ID/raw SQL/global helper는 PostgreSQL UUID, SQLAlchemy 2.x 및 UoW와 충돌합니다. 모든 repository를 새로 작성했고 commit/rollback/begin 정적 금지 검사를 유지했습니다.
4. 기존 service HTTPException과 camelCase/default developer role은 새 API·RBAC 계약과 충돌합니다. framework 없는 ApplicationError/Principal/Protocol과 분리 Pydantic 모델, 서버 permission 조회로 변경했습니다.
5. 자체 password format/JWE 구현은 신규 보안 구현의 근거가 될 수 없습니다. 검증된 Argon2id/PyJWT 라이브러리, 고정 알고리즘·issuer/audience/만료 검증, 해시 저장으로 대체했습니다.
6. ESG localStorage/Redux/Context의 인증·선택 객체 및 ESG report coupling은 회사별 권한 정본과 충돌합니다. 메모리 access token, HttpOnly refresh cookie, 독립 company context와 매 요청 membership 검증으로 변경했습니다.
7. ESG 회사 입력의 세무·ESG 속성과 conflict marker가 있는 repository는 회사 정본에 부적합합니다. 허용된 회사 필드만 신규 DTO에 반영하고 Tax Profile/ESG context/JSON은 제외했습니다.

전송 방식, 신규 Tenant 생성 정책, 조건부 권한의 보수적 seed와 초대 OWNER 승격 제한은 [구현 계약](identity-company.md)에 기록했습니다. 이전 구현의 편의를 이유로 Drive 설계를 변경하지 않았습니다.
