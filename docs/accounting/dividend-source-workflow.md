# 배당 원천 선택과 지급 연결

기준 main은 `87a72c2689eca0a5534a05178e95749df16cb5ed`다. 로컬 `docs/AI_Accounting_Office_v0.2.6_통합설계_정본/`의 읽기안내, 결산/기간마감 및 재무제표 완전세트의 배당·SCE 계약을 사용했다. 이 설계 복사 폴더는 Git 제외 대상이다.

## 지원 업무 경로

`/financial-statements`의 SCE에서 회사·기간을 선택하고 배당 원천 작업 영역을 연다. 해당 기간의 승인된 POSTED 전표 중 유효한 이익잉여금 매핑의 차변과 부채 대변이 일치하는 후보만 표시한다. 사용자가 전표와 실제 결의일·지급 예정일을 확인해 등록한다. 금액은 서버가 검증한 Decimal 문자열을 그대로 전송하고 프론트엔드가 다시 계산하지 않는다. 후보라는 이유로 배당임을 자동 확정하지 않으며, 등록도 전표 Posting이나 새로운 승인을 수행하지 않는다.

실제 지급은 지급기간을 선택하고 기존 결의를 고른 후, 해당 기간의 CF 재무활동 `DIVIDENDS_PAID` 원천을 확인해 연결한다. 부분지급과 후속 기간 지급을 지원하며 전체 연결 지급액·잔액·지급 전표·증빙 ID·CF 원천 digest를 표시한다. 결의 등록 자체는 현금유출이 아니다. 이후 기존 SCE 대사, Snapshot 생성, 독립 검토·승인, Report Center PDF/XLSX/CSV와 다운로드를 사용한다. 결과는 `INTERNAL_VALIDATION_ONLY`다.

## API와 불변식

- `GET /equity/dividend-sources?period_id=...`: 회사·기간 범위 결의 후보, 승인 참조, 금액·증빙·등록 여부.
- `GET /equity/dividends/{id}/payment-sources?period_id=...`: 회사 범위 결의의 지급기간 후보, 지급 누계·잔액, 차단 사유. 최신 CF가 stale이면 과거 CF로 조용히 대체하지 않는다.
- 기존 결의/지급 POST를 그대로 사용한다. 후보 조회는 `financial_statement.read`, 등록은 `financial_statement.generate`와 CSRF를 요구한다. 조회 결과를 신뢰해 바로 쓰지 않고 트랜잭션 안에서 원천을 다시 검증한다.
- 결의 등록은 POSTED 전표 행을 잠그고 동일 원천·동일 내용이면 기존 결과를 반환한다. 다른 날짜·금액은 충돌한다. `036_dividend_source`의 회사/결의 전표 unique constraint가 중복 등록을 막는다.
- 지급은 기존 결의 행 잠금에 지급 전표 행 잠금을 추가한다. 다른 CF revision의 이벤트라도 같은 현금 분개/상대 분개 조합이 이미 연결되었으면 충돌한다. 동일 CF 이벤트·동일 결의 재요청은 기존 지급을 반환한다. 과거 지급·Snapshot·승인 이력은 수정하지 않는다.
- 지급 검증은 조회와 명령에서 공유한다. 기간/현재성, 승인된 결의, POSTED 지급, 배당 CF 분류, 날짜, 상대 부채 계정, 지급 누계 한도를 검증한다. 조회에서는 결정론적 reason code, 명령에서는 기존 `STATE_CONFLICT` 계약을 유지한다.

## 마이그레이션과 호환성

035 → 036 단일 head다. 기존 원천 없는 PROPOSED 결의는 그대로 보존한다. 기존 데이터에 동일 회사/전표의 결의 중복이 있으면 unique 생성이 실패하며, 자동 삭제·병합하지 않는다. 운영 적용 전에 중복 원천과 연결 지급을 검토해야 한다. 과거 완료 Artifact의 다운로드 계약은 바꾸지 않는다. 원천 없는 제안에서 승인 전표를 생성하거나 자동 연결하는 기능은 제공하지 않는다.

## 손익마감 제한과 범위 선택

정본은 ADJUSTED와 POST_CLOSING을 구분하고 물리적 마감 전표 연결을 요구하지만, 현재 구현에는 fiscal-year hard-close 원천 identity와 IS 표시 기준 분리 계약이 없다. Equity Event를 보고 IS 금액을 소급 복원하면 기존 BS/IS/CF source digest의 의미를 바꾸므로 이번 변경에서는 수행하지 않는다. `PROFIT_TRANSFER_IS_MISMATCH`와 #112는 유지한다.

요청의 대체 마일스톤 조건에 따라 #83의 핵심 UX 중 기존 SCE 배당 업무를 선택했다. 수동 UUID 입력, 중복 결의, CF revision 간 동일 지급 재연결을 해소하며 #129의 승인·Export를 재작성하지 않는다. 손익마감 지원을 완료하려면 별도 명시적 hard-close 원천/기간/IS 표시 계약과 BS/IS/CF 교차 검증이 필요하다. 자산·재고·세무 확장, 실고객 Pilot, 운영 복구 및 최종 Release Gate는 제외한다.

## 검증

PostgreSQL migration lifecycle·SCE·독립 연결 검증 5건 통과. 결의 후보·동일 요청 재시도·다른 요청 충돌·DB unique·회사 격리·부분/후속 지급 및 기존 손익 대체 BLOCKED assertion을 유지했다. 최종 추가 검증은 CF 정책 버전 변경 → 새 CF 이벤트 → 동일 지급 재연결 차단과 독립 연결의 동시 결의/지급 요청이다. 이 최종 SCE subset 4건도 통과했다. Ruff/format/mypy와 frontend lint/typecheck를 통과했다. 검증 결과는 PR에 함께 기록한다.

Frontend 상태 모델 62건 통과. 전체 Golden/전체 PostgreSQL regression/브라우저 E2E/실고객 자료 검증은 수행하지 않는다.
