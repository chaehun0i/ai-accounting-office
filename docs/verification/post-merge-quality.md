# PR #18 이후 오류·코드 정리 검증

시작 main: `96618cb56505bbf60743cc76a7ab4dd3a0242364` (PR #18 병합). 설계 기준은 Google Drive `AI_Accounting_Office_v0.2.6_통합설계_정본`이며 이전 버전 fallback은 사용하지 않았다.

마감 차단 질의가 건수만 보여 주던 오류를 고쳐 기존 Closing Tool의 검사 코드·Decimal 영향 금액을 답변에 포함했다. Controller는 Tool의 차단 건수와 검사 목록이 다르면 응답을 차단한다. 프론트엔드는 회계기간 조회 실패를 빈 기간과 구분하고 같은 화면에서 재시도할 수 있게 했다. 처리 중인 질의는 기존 run 조회를 계속 사용할 수 있다. 사용되지 않는 AI Team 자리표시 파일과 금액 문자열을 그대로 반환하던 불필요한 helper를 제거했다.

초기 오류 수정 검증: Backend 집중 unit/contract **4 passed**, Agent PostgreSQL 통합 **2 passed**, Ruff·format·mypy 통과. Frontend **36 passed**, lint·typecheck 통과. Next.js production build는 Windows 제한된 실행에서 `.next` 디렉터리 생성 `EPERM`이 발생했으나 동일 작업공간의 빌드 산출물을 정리하고 실행 권한을 확장해 19개 정적 페이지 생성까지 통과했다. Migration·업무 DB schema는 변경하지 않았다.

현재 문서의 구현 설명과 메뉴 목록은 README·아키텍처·내비게이션·Agent·월마감·재무제표·feature 안내에 동기화했다. 과거 `*-verification.md`의 SHA·수치는 해당 시점의 실행 기록으로 보존한다. [문서 읽기 안내](../README.md)가 현재 계약과 과거 기록을 구분한다.

후속 유지보수에서는 거래 전표 제안과 기간 질의의 LangGraph 정의를 분리하고, AI 회계팀 화면에서 API/폴링 상태를 전용 hook으로 분리했다. 기능이나 DB 계약은 바꾸지 않았다. Backend 집중 unit/contract **15 passed**, PostgreSQL 통합 **12 passed**, Ruff·format·mypy 통과. Frontend **36 passed**, lint·typecheck·production build 통과. 이 변경은 파일의 책임을 좁히는 구조 정리이며 실행 성능 향상을 주장하지 않는다.

회계기간 재조회가 겹칠 때 이전 응답이 새 목록을 덮지 않도록 요청별 취소 상태를 적용하고, 재조회 시작 시 이전 기간 목록을 비운다. 관련 AI 회계팀 테스트 **2 passed**, lint·typecheck 통과.

AI 회계팀 화면은 기존 업무 화면의 초록색·패널 스타일을 유지하면서 회사·기간 입력, 답변, 검증 상태, 장부 금액, 출처를 분리해 읽기 쉽게 정리했다. 상태 표시는 한국어 레이블을 사용하며 차단·실패를 별도 색상으로 구분한다. 숫자는 여전히 API의 `answer_amount` 문자열을 그대로 표시하고 출처 식별자는 줄바꿈해 확인할 수 있다.
