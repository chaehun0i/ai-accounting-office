# 기능 경계

각 feature가 UI와 feature local state를 소유한다. 공유 UI 및 API transport는 shared에 둔다.
서버 상태는 향후 query layer에서 관리하고 company id를 query key에 포함한다.
회사 변경 시 이전 회사의 query cache와 AI context를 분리한다.
현재 feature 디렉터리는 경계만 예약하며 업무 화면이나 인증을 구현하지 않는다.
