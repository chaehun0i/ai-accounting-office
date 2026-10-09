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
| NEXT_PUBLIC_API_ORIGIN | 예제 http://localhost:8000 | 예약값; 현재 frontend 소비 없음 |

URL credential은 URL-encode해야 합니다. Compose 환경변수와 backend URL은 자동 조합하지 않으므로 변경 시 일치시켜야 합니다. Redis는 로컬 전용이며 인증 없이 loopback에만 공개합니다. 운영 배포 구성은 이번 범위가 아닙니다.

Backend 필수값 누락/잘못된 설정은 application factory에서 고정 메시지 `설정을 확인해 주세요. 필수 환경변수와 값의 형식은 docs/environment.md를 참고해 주세요.`로 실패합니다. 서버 시작 실패에 원문 credential을 출력하지 않습니다. Settings repr에서도 URL이 숨겨집니다.

앱 debug는 항상 false입니다. CORS는 단일 명시적 origin의 GET만 허용하며 credential/wildcard를 활성화하지 않습니다. 오류 응답은 code/message/request_id/field_errors를 사용합니다. 내부 오류 메시지·traceback·입력값은 응답과 앱 로그에 포함하지 않습니다. 개발 실행 스크립트는 URL query 유출을 피하도록 access log를 끕니다. 향후 로그 필드를 추가할 때도 raw request/response, secret, 재무 원문을 기록하지 않습니다.


## Persistence 설정

엔진은 `postgres`/`postgresql`/`postgresql+psycopg` URL을 psycopg 3 드라이버로 정규화합니다. 엔진 생성·모듈 import는 연결하지 않습니다. 최초 사용 시 연결하며 timeout 5초, 연결별 timezone UTC를 사용합니다. URL query로 timezone이나 SQL echo를 활성화하지 않습니다. echo/echo_pool은 false, hide_parameters는 true입니다. 엔진 소유자가 종료 시 dispose합니다.

Alembic은 backend에서 실행하며 같은 환경변수 우선순위와 `.env`를 사용합니다. ini에는 접속 주소를 넣지 않습니다. 통합 검사는 `.env`의 개발 DB를 자동 재사용하지 않으며 OS의 TEST_POSTGRES_URL을 별도로 요구합니다. 테스트 주소에 실제 운영 credential을 쓰지 마세요.
