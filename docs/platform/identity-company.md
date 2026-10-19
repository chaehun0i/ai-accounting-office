# Identity / Company 구조와 보안 계약

설계 기준: [AI_Accounting_Office_v0.2.3_통합설계_구현보강](https://drive.google.com/drive/folders/17FO3EYPA64MItPL-_RQbgg1NhKr4I5mn).
기준 main: `db0df108f17c3e5a562e8c3d17bc65b30d620f95`. 구현 전에 원격 fetch/pull과 병합 PR #1/#2를 확인했습니다.

직접 확인한 설계 문서: 56 Identity/Auth/Session, 44 Permission Matrix, 45 API/Pydantic, 41 Physical ERD/DDL, 42 Relational-First, 46 Error/Idempotency/Concurrency, 48 Module Architecture, 49 File Migration Map, 51 Bootstrap, 52 DoD, 59 Complete DDL Migration Map, 25 기존 프로젝트 Migration Map. 상세 migration 순서는 59를 우선합니다.

## 계층과 정본

- `identity/users/domain`, `sessions/domain`: UUID 기반 사용자·세션·Principal 값. framework import 없음.
- `identity/auth/application`: register/login/authenticate/rotation/logout, repository/UoW Protocol.
- `identity/*/infrastructure`: SQLAlchemy 모델·repository·UoW adapter. Repository는 commit하지 않습니다.
- `companies/domain`: Company 값과 명시적인 permission grant 표.
- `companies/application`: 접근 가능한 회사 조회, 생성/수정과 서버 권한 검증.
- `identity/invitations/application`: 초대 생성/수락/폐기, 인증 이메일에 묶인 capability.
- `*/api`: strict Pydantic 입력·출력과 transport. ORM을 response로 반환하지 않습니다.
- `app/composition.py`: adapter와 service 조립. `app/model_registry.py`: Alembic metadata 등록.
- `core/security.py`: Argon2id, 고정 알고리즘 JWT와 해시 primitive. 업무 상태는 core에 없습니다.

Accounting/Tax/Evidence/Finance/Governance/Runtime 정본을 합치지 않습니다. Agent → Tool Registry → Tool Adapter → Application Service → Repository/UoW 경계와 Decimal 결정적 계산, Human Approval 원칙을 유지합니다. 해당 후속 기능은 구현하지 않았습니다.

## 관계형 스키마와 migration

`db_foundation → 001_identity → 002_tenant_company_rbac` 순서이며 자동 `create_all()`은 없습니다.

| Revision | 테이블 | 주요 제약 |
| --- | --- | --- |
| 001_identity | users | UUID PK, normalized email UNIQUE/CHECK, 상태 CHECK |
| 001_identity | refresh_sessions | user FK, token/JTI hash UNIQUE, family index, 만료·회전·폐기 상태 CHECK |
| 001_identity | identity_security_events | user/session FK, 명시적 event code CHECK, email/IP·시간 index |
| 002_tenant_company_rbac | tenants, companies | tenant FK, tenant/business number UNIQUE, 사업자 번호·유형·버전 CHECK |
| 002_tenant_company_rbac | roles, permissions, role_permissions | code PK, 관계 FK와 복합 PK |
| 002_tenant_company_rbac | company_memberships | company/user/role FK, company+user UNIQUE, 상태·버전 CHECK |
| 002_tenant_company_rbac | company_invitations | company/user/role FK, inviter membership 복합 FK, token hash UNIQUE, PENDING company/email partial UNIQUE |

업무 테이블 10개와 내부 `alembic_version`만 존재합니다. JSON/JSONB/ARRAY column, generic payload/context/settings table은 없습니다. UUID/NUMERIC(19,4)/TIMESTAMPTZ 규칙은 기존 DB Foundation을 유지합니다. 금액 column은 아직 없습니다.

온라인 migration 전후와 실제 PostgreSQL integration test가 프로젝트 관리 schema `public`의 JSON/JSONB를 검사합니다. 위반 시 table/column 목록을 보여 줍니다. 추가 검사로 FK validation, PK/FK/UNIQUE/CHECK 및 초대 partial index를 확인합니다. 테스트 DB는 이름이 `_test`로 끝나야 하며 migration lifecycle 검사는 알려진 테이블이라도 데이터가 있으면 삭제하지 않고 중단합니다.

권한 seed는 DDL과 분리합니다. upgrade 후 다음 명령을 실행하세요. 동일 명령을 반복해도 중복 생성하지 않습니다. 기존 grant를 자동 삭제하는 배포 동작은 없습니다.

```sh
python -m app.companies.infrastructure.seed
```

## 인증과 세션

이메일은 API EmailStr 검증 후 Application/Domain에서 trim+lower하여 unique identity로 사용합니다. password는 12~128자, UTF-8 512바이트 이하이고 Argon2id 라이브러리 기본 정책으로 해시합니다. 사용자 미존재/비밀번호 오류/비활성 계정은 동일한 인증 실패를 반환합니다. 정상 로그인 시 필요한 KDF rehash를 수행합니다.

Access JWT는 기본 10분, 최대 15분입니다. Refresh JWT는 기본/최대 30일입니다. HS256 고정 allowlist와 issuer/audience/typ/필수 claim/UUID/JTI/만료를 검증합니다. claim은 sub/sid/jti/iat/exp 및 transport 검증용 값이며 회사 role/permission을 넣지 않습니다. PostgreSQL에는 refresh token/JTI의 SHA-256 hash만 저장합니다. 비밀번호는 Argon2 hash만 저장합니다.

Refresh는 PostgreSQL 시간과 사용자 row lock을 기준으로 처리합니다. 기존 row를 ROTATED로 보존하고 같은 session_family_id의 새 row를 하나의 UoW로 생성합니다. 회전된 토큰 재사용은 REFRESH_REUSED와 SESSION_FAMILY_REVOKED를 기록하고 가족 전체를 폐기한 뒤 인증 실패를 반환합니다. 실패 이벤트를 보존하기 위해 결정된 인증 실패는 필요한 transaction commit 후 반환합니다. 원문 토큰을 이벤트에 기록하지 않습니다.

동시 refresh도 사용자 lock으로 직렬화합니다. 두 요청이 같은 토큰을 사용하면 하나가 회전하고 나머지가 reuse로 판정되어 가족이 폐기됩니다. frontend는 탭 내 single-flight 및 지원 브라우저의 Web Locks로 회전을 직렬화합니다. Web Locks 미지원 브라우저의 여러 탭 동시 refresh는 보수적인 재로그인으로 이어질 수 있습니다.

로그아웃은 현재 가족을 폐기하며 로그아웃 전체는 사용자 모든 가족을 폐기합니다. 이력은 삭제하지 않습니다. Access 요청도 PostgreSQL 사용자/세션 상태와 JTI를 확인하므로 폐기·비활성화가 즉시 반영됩니다. 정상 ROTATED row의 이전 access는 짧은 access TTL 동안 유효하되 가족 폐기 시 무효입니다.

Redis는 이번 인증 구현에서 사용하지 않습니다. 영구 세션/폐기/보안 이벤트 정본은 PostgreSQL이며 Redis 장애가 인증 정본에 영향을 주지 않습니다.

## 전송과 CSRF 결정

Refresh token은 HttpOnly, SameSite=Strict, Path=/ cookie로만 전달합니다. staging/production은 Secure와 `__Host-aao-refresh`, local/test는 `aao-refresh`를 사용합니다. Access token은 응답 후 frontend 메모리에만 보관합니다. localStorage/sessionStorage에 토큰이나 회사 객체를 저장하지 않습니다.

브라우저는 Next.js의 같은 origin `/api` 프록시를 사용합니다. 프록시의 `BACKEND_API_ORIGIN`은 서버 설정이며 credential/path/query를 허용하지 않습니다. frontend build/dev를 시작할 때 설정합니다. backend `FRONTEND_ORIGIN`은 실제 브라우저 origin과 같아야 합니다.

모든 변경 요청에는 `X-CSRF-Protection: 1`이 필요합니다. Origin이 있으면 설정 origin과 정확히 같아야 합니다. CLI는 Origin 없이 해당 custom header와 Bearer/cookie를 명시할 수 있습니다. CORS는 명시적 한 origin, 필요한 method/header와 credential만 허용합니다. staging/production frontend origin은 HTTPS 필수입니다.

인증·회사 응답은 no-store입니다. request body/header/token을 앱 로그에 남기지 않고 HTTP 라이브러리 및 uvicorn access log의 초대 수락 URL 토큰도 숨깁니다. 운영 reverse proxy도 `/invitations/*/accept` 원문 URL과 Authorization/Cookie/body를 수집하지 않도록 설정해야 합니다. 개발 runner는 access log를 끕니다.

## 회사·권한과 활성 회사 결정

Company 생성은 새 Tenant+Company+OWNER membership을 하나의 UoW에서 만듭니다. 임의 tenant_id를 받아 다른 Tenant에 연결하지 않습니다. 여러 회사를 기존 Tenant에 묶는 Control Plane workflow는 후속 범위입니다. Tax Profile은 Company에 넣지 않습니다.

현재 Principal의 ACTIVE membership, ACTIVE Company/Tenant와 role_permissions를 요청마다 조회합니다. 회사 resource는 company_id+user scope query로 가져오며 다른 회사/미존재/폐기 membership은 404, 같은 회사의 permission 부족은 403입니다. OWNER도 wildcard를 갖지 않습니다. Role은 permission 묶음이며 실제 enforcement는 company.read/company.update/company.members.manage 등 code 기준입니다.

8종 role과 44 문서의 명시적 permission grant를 seed합니다. 조건부 permission은 자동 부여하지 않습니다. 예를 들어 evidence.download_raw, tax.rule.activate, payment.execute와 filing.submit은 승인·마스킹·Control Plane 설계가 없는 이번 단계에서 role에 자동 부여하지 않습니다. 후속 도메인 permission code seed는 해당 API 구현이나 승인 우회를 의미하지 않습니다. ADMIN은 OWNER 초대를 만들 수 없습니다.

활성 회사는 frontend 메모리 context입니다. 1개 회사는 서버 GET 검증 후 자동 선택, 여러 회사는 검색/선택 완료를 거칩니다. 선택은 경로 `/companies/{id}`로 서버 검증하며 JWT에 권한으로 저장하지 않습니다. 회사 전환/사용자 변경 시 이전 응답을 버리고 active 상태를 초기화합니다. 모든 후속 회사 API도 경로의 company_id를 다시 검증해야 합니다.

## 초대와 기본 공격 억제

초대는 7일 유효한 고엔트로피 일회용 capability이며 hash만 저장합니다. 생성 권한자에게 원문을 한 번 반환합니다. 이메일 발송은 이번 범위에 없으며 전달 채널은 운영 연동 전 별도로 정해야 합니다. 수락은 인증된 정규화 이메일과 capability를 함께 조회합니다. 다른 이메일/알 수 없는 token은 같은 404입니다. 기존 ACTIVE membership의 role을 덮어쓰거나 REVOKED membership을 초대로 복원하지 않습니다. 수락과 membership 생성은 원자적입니다. DELETE는 row 삭제가 아니라 REVOKED 전환입니다.

PostgreSQL security event와 transaction advisory lock으로 IP prefix당 분당 register 20회, login/refresh 60회를 제한합니다. 로그인은 이메일 hash당 15분 내 실패 10회도 제한합니다. IP는 IPv4 /24, IPv6 /56으로 축약하고 User-Agent는 hash만 저장합니다. 프록시 헤더는 앱이 직접 신뢰하지 않습니다. 운영 배포 시 신뢰 proxy 목록과 edge 제한을 별도 설정해야 합니다. API 오류 확장 RATE_LIMITED는 HTTP 429이며 원문 입력을 반환하지 않습니다. 사용자 이메일 존재 여부를 중복 가입 응답으로 공개하지 않습니다.

## API 계약

| 영역 | 경로 |
| --- | --- |
| 인증 | POST /auth/register, /auth/login, /auth/refresh, /auth/logout, /auth/logout-all; GET /auth/me |
| 회사 | GET/POST /companies; GET/PATCH /companies/{id} |
| 초대 | POST /companies/{id}/invitations; DELETE /companies/{id}/invitations/{invite_id}; POST /invitations/{token}/accept |

Create/Update/Read/Result 모델은 분리하고 변경 입력은 extra=forbid입니다. Company PATCH는 expected_version과 company_name/address만 허용합니다. 오류는 기존 code/message/request_id/field_errors 계약입니다. `/health`는 DB와 무관한 liveness로 유지합니다. API의 JSON 직렬화는 DB JSON column을 뜻하지 않습니다.

## 후속 범위

Accounting Master: counterparty/payment term/accounting settings/COA/templates/accounting period/journal sequences. 구현하지 않았습니다. 인증 이메일 검증·비밀번호 복구, 초대 이메일 발송, 기존 Tenant 관리 UI, 역할 관리 workflow 및 운영 key rotation/edge rate limit은 별도 범위입니다. 전체 Governance/Audit, idempotency persistence, Approval, Accounting/Tax 업무와 Agent/LLM도 포함하지 않습니다.
