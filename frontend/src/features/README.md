# 기능 경계

각 feature가 UI와 feature local state를 소유한다. 공유 UI 및 API transport는 shared에 둔다.
각 화면은 인증된 API 호출에 `X-Company-ID`를 전달한다. 서버 상태 캐시를 공통으로 두지 않으며, 회사 변경 시 회사별 화면 컴포넌트를 다시 생성해 입력과 응답을 폐기한다.
`ai-team`은 기간 선택과 질문·결과 표시만 소유한다. 마감 검사·재무제표 금액·Tool 선택·Controller 판정은 기존 Backend 정본을 사용한다.
