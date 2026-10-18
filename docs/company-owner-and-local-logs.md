# 회사 OWNER 권한과 로컬 요청 로그

`OWNER`는 자신이 활성 멤버인 회사에서 등록된 모든 회사 기능 권한을 받는다. 접근 가능한 회사 목록과 개별 명령은 서버의 활성 회사·멤버십 검사로 제한한다. 다른 회사의 리소스는 기존 정책대로 404로 응답한다. 모든 권한을 갖더라도 승인 요청자와 승인자를 분리하는 업무 불변식은 그대로 적용한다.

새 permission code가 등록되면 `OWNER` 멤버십의 권한 응답에도 즉시 포함된다. 권한 seed는 `OWNER`와 각 permission의 관계를 보강하므로 기존 데이터베이스에서 재실행할 수 있다. 다른 역할의 권한 묶음은 변경하지 않는다.

로컬 Compose에서 요청을 확인하려면 `docker compose --env-file .env -f infra/docker-compose.yml logs -f backend frontend`를 실행한다. 백엔드는 Uvicorn access log를, 프론트는 Next Proxy의 메서드와 경로를 stdout에 기록한다. 프론트 로그에는 query, cookie, authorization header, 요청 본문을 넣지 않는다. `/health` 같은 healthcheck 요청도 백엔드 로그에 나타난다.

Playwright MCP로 새 로컬 OWNER 계정의 회사 생성, 거래 작성 화면 접근, 브라우저 요청 후 양쪽 컨테이너 로그 출력을 확인했다. 테스트용 계정과 회사는 로컬 Compose DB에만 생성했다.
