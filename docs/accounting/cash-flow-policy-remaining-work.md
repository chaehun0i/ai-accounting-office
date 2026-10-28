# 현금흐름표 잔여 작업

현재 `main`은 직접 현금흐름 원천과 간접법 bridge, CLOSED 기간 snapshot, 조회 화면을 제공한다. 이 문서는 아직 제품 완료로 볼 수 없는 범위를 기록한다. 이 PR에 있던 미완성 정책 코드는 병합 대상에서 제외했다.

## 남은 백엔드 계약

- 이자 지급·수취와 법인세 납부의 회사별 분류 정책, 적용 시작일, 버전, 변경 이력을 관계형 모델로 확정한다.
- 비현금 거래는 전표의 차변·대변 line과 증빙을 명시적으로 연결하고 금액 보존과 중복 사용을 검증한다.
- 자산 처분손익 조정은 원천 전표와 현금 유입을 대조한 뒤 간접법 bridge에 반영한다.
- 정책·비현금 원천·bridge 규칙을 Cash Flow snapshot의 provenance와 digest에 포함하고, snapshot 생성 뒤 원천 의미가 바뀌지 않게 한다.
- PostgreSQL migration, 회사 격리, 권한, 멱등성, 집중 통합 테스트를 구현한다.
- Report Center의 Cash Flow export를 별도 연결한다.

## 별도 제품 범위

SCE와 Notes는 현재 미지원이다. 각각의 원천 event, 분류·검증, 승인, snapshot, 조회·export 계약이 필요하다. Issue #87의 현금흐름 완료 조건은 이 문서만으로 충족되지 않는다.

설계 정본 `docs/AI_Accounting_Office_v0.2.6_통합설계_정본/`은 읽기 전용으로 유지한다.
