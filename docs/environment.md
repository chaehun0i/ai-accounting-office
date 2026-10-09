# 환경변수 계약

Backend는 `backend` 작업 디렉터리 기준 `../.env`를 읽고 OS 환경변수가 우선합니다. `scripts/dev.py backend-run`이 작업 디렉터리를 맞춥니다. `uvicorn app.main:create_app --factory`를 직접 실행할 때는 backend에서 실행하세요. 직접 uvicorn을 실행하면 host/port는 uvicorn CLI 옵션이 소유합니다.

| 변수 | 필수 / 기본값 | 검증 / 소비자 |
| --- | --- | --- |
| APP_ENVIRONMENT | 필수 | local/test/staging/production; backend |
| POSTGRES_URL | 필수 | PostgreSQL DSN; SecretStr로 표현을 숨김; 명시적 엔진 사용/Alembic에서 연결 |
| TEST_POSTGRES_URL | integration 실행 시 필수 | OS 환경변수; 별도 PostgreSQL DB, 이름은 `_test`로 끝나야 함; 앱 Settings에는 포함하지 않음 |
| REDIS_URL | 필수 | Redis DSN; SecretStr로 표현을 숨김; 현재 연결하지 않음 |
| BACKEND_HOST | 127.0.0.1 | IPv4/IPv6; 개발 실행 스크립트 |
| BACKEND_PORT | 8000 | 1..65535; 개발 실행 스크립트 |
| FRONTEND_ORIGIN | http://localhost:3000 | 단일 HTTP(S) origin, 경로/credential/query/fragment 금지; staging/production은 HTTPS |
| POSTGRES_DB | Compose 필수 | 로컬 DB 이름 |
| POSTGRES_USER | Compose 필수 | 로컬 DB 사용자 |
| POSTGRES_PASSWORD | Compose 필수 | 로컬 placeholder; 운영 secret으로 재사용 금지 |
| POSTGRES_PORT | 5432 | Compose host port, URL에도 동일하게 반영 |
| REDIS_PORT | 6379 | Compose host port, URL에도 동일하게 반영 |
| AUTH_SIGNING_KEY | local/test 선택, staging/production 필수 | 최소 32바이트 SecretStr, 운영 placeholder 금지; dev.py env가 무작위 키 생성 |
| ACCESS_TOKEN_TTL_SECONDS | 600 | 60..900 |
| REFRESH_TOKEN_TTL_SECONDS | 2592000 | 3600..2592000 |
| BACKEND_API_ORIGIN | http://127.0.0.1:8000 | frontend/.env.local; Next.js 서버 프록시, build/dev 시작 시 반영 |

URL credential은 URL-encode해야 합니다. Compose 환경변수와 backend URL은 자동 조합하지 않으므로 변경 시 일치시켜야 합니다. Redis는 로컬 전용이며 인증 없이 loopback에만 공개합니다. 운영 배포 구성은 이번 범위가 아닙니다.

Backend 필수값 누락/잘못된 설정은 application factory에서 고정 메시지 `설정을 확인해 주세요. 필수 환경변수와 값의 형식은 docs/environment.md를 참고해 주세요.`로 실패합니다. 서버 시작 실패에 원문 credential을 출력하지 않습니다. Settings repr에서도 URL이 숨겨집니다.

앱 debug는 항상 false입니다. CORS는 단일 명시적 origin의 GET/POST/PATCH/DELETE와 필요한 header 및 cookie credential만 허용합니다. wildcard는 허용하지 않습니다. 변경 요청은 X-CSRF-Protection: 1과 Origin 검증을 거칩니다. 오류 응답은 code/message/request_id/field_errors를 사용합니다. 내부 오류 메시지·traceback·입력값은 응답과 앱 로그에 포함하지 않습니다. 개발 실행 스크립트는 URL query 유출을 피하도록 access log를 끕니다. 향후 로그 필드를 추가할 때도 raw request/response, secret, 재무 원문을 기록하지 않습니다.


## Persistence 설정

엔진은 `postgres`/`postgresql`/`postgresql+psycopg` URL을 psycopg 3 드라이버로 정규화합니다. 엔진 생성·모듈 import는 연결하지 않습니다. 최초 사용 시 연결하며 timeout 5초, 연결별 timezone UTC를 사용합니다. URL query로 timezone이나 SQL echo를 활성화하지 않습니다. echo/echo_pool은 false, hide_parameters는 true입니다. 엔진 소유자가 종료 시 dispose합니다.

Alembic은 backend에서 실행하며 같은 환경변수 우선순위와 `.env`를 사용합니다. ini에는 접속 주소를 넣지 않습니다. 통합 검사는 `.env`의 개발 DB를 자동 재사용하지 않으며 OS의 TEST_POSTGRES_URL을 별도로 요구합니다. 테스트 주소에 실제 운영 credential을 쓰지 마세요.

인증 키가 없는 local/test에서는 /health가 정상 동작하고 인증 요청은 안전한 503을 반환합니다. 기존 .env에는 `python scripts/dev.py auth-key`로 키를 추가하세요. 운영은 HTTPS, Secure cookie와 별도 비밀 관리가 필요합니다. 자세한 전송 정책은 [Identity/Company](identity-company.md)를 참고하세요.


## 원본 파일 저장 위치

`STORAGE_ROOT`는 backend 실행 경로 기준 로컬 저장소 디렉터리이며 기본값은 `../.local/storage`입니다. 생성 시 디렉터리를 만들지 않고 실제 업로드 때만 생성합니다. 애플리케이션 운영 계정만 쓸 수 있는 위치를 지정하고 별도 백업·보존 정책을 적용하세요. 원본 파일은 DB 외부에 보관하며 key에 사용자 filename을 사용하지 않습니다. [.env.example](../.env.example)은 로컬 placeholder만 포함합니다.
