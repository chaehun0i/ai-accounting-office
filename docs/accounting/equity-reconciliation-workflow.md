# 자본변동 대사 근거와 차단 해결 작업함

## 결정과 지원 범위

기준 main은 `a20bcbd6a55e2a501d559b7c3fe5e8610772fa0e`이다. 로컬 Design SSOT는 `docs/AI_Accounting_Office_v0.2.6_통합설계_정본/`이며 Git 제외를 유지한다. 문서지도, 재무제표 완전세트의 SCE 당기손익·Roll-forward 절과 결산 문서의 Trial Balance Stage 절을 확인했다.

설계는 연말 physical closing Journal과 SCE의 연결을 허용하지만 `POST_CLOSING`을 월별 soft close의 `ADJUSTED`와 구분한다. 현재 Closing V1·BS/IS는 ADJUSTED를 사용하고 Journal 원천에는 검증된 연말 hard-close 분류가 없다. 기존 Equity Event는 POSTED 자본 라인의 분류이며 과거 IS 순이익을 다시 쓰는 권한이 아니다. 따라서 명시적인 hard-close 단계·원천/표시 계약 없이 PROFIT_TRANSFER Journal을 IS에서 임의 제외하지 않는다.

#112의 `PROFIT_TRANSFER_IS_MISMATCH` 차단을 유지한다. 지시된 fallback에 따라 #83의 핵심 UX 중 차단 사유 → 원천 금액·Journal/Evidence → 명시적 분류 검토 → 기존 마감/Notes 독립 승인/Export 경로를 완성한다. 물리적 손익마감이나 전체 제표 세트 승인을 구현 완료로 표시하지 않는다.

## 사용자 경로

1. 재무제표 화면에서 CLOSED 기간과 현재 BS/IS를 선택한다.
2. SCE 상태·검사 코드와 제표 금액, 원천 진단금액, 차이를 확인한다. 금액은 모두 backend Decimal 결과이며 프론트는 계산하지 않는다.
3. 현재 기간 자본·손익 대체 전표의 account/line ID와 연결 증빙을 확인한다. 분류가 필요한 라인은 선택해 기존 입력란으로 가져오고 사용자가 변동 유형을 명시적으로 선택한다. 선택만으로 POST나 전표 생성이 발생하지 않는다.
4. 매핑·미분류·기간·stale 문제는 연결된 기존 화면에서 해결한다. 손익 대체 IS 충돌은 현재 지원 불가 계약으로 안내하며 숫자 보정·자동 재개/Posting을 하지 않는다.
5. READY일 때만 기존 SCE Snapshot을 생성한다. 원천 셀 Drill-down과 Report Center의 PDF/XLSX/CSV·이력·다운로드를 사용한다. RECONCILED는 법정 승인 상태가 아니다.
6. Notes는 기존 SCE 원천 현재성·BS/IS/CF 교차 검증을 통과한 뒤 별도의 작성·독립 검토·승인을 진행한다. Notes 승인과 SCE 생성 상태를 혼동하지 않는다.

## API의 추가 진단 계약

기존 `GET /equity/reconciliation?period_id=`의 기존 필드는 유지하며 아래 필드를 추가한다. 새 업무 table/JSON column/migration은 없다.

- `checks`: code/status, reported_amount, source_amount, difference, basis, next_action, 관련 Journal ID. `difference=source_amount-reported_amount`이며 원천 부족 시 null이다.
- `source_rows`: 현재 기간 자본 계정과 분류된 손익 대체 Journal의 POSTED line, 계정/금액, 기존 Event 유형, classification_required, Evidence ID. 회사 조건을 모든 원천 조회에 적용한다.
- `statement_set_id`, `close_version`: 현재 검증 기준의 식별자다.

`SCE_CLOSING_VS_BS_EQUITY`는 SCE 기말합계와 BS 자본을 비교한다. `POSTED_PL_EXCLUDING_CLASSIFIED_TRANSFER_DIAGNOSTIC_ONLY`는 분류된 대체 Journal을 제외한 당기 POSTED 손익을 IS Snapshot과 비교하는 진단 기준이다. 이 금액은 공식 순이익이나 대체 IS Snapshot이 아니며 이를 이용해 SCE·Notes·Export의 차단을 우회할 수 없다.

OPEN/CLOSING 기간은 `BLOCKED/PERIOD_NOT_CLOSED`, 현재 마감 원천 stale은 `BLOCKED/REPORT_SOURCE_STALE`로 표시한다. 이때 금액과 source digest는 null이며 0으로 채우지 않는다. 타 회사·존재하지 않는 기간은 기존 권한/404 계약을 유지한다. 생성 명령의 엄격한 오류와 원천 검증은 바꾸지 않는다.

## 검증과 불변식

기존 SCE 정상·손익 대체 차단 테스트에 다음 assertion을 추가했다: OPEN readiness, 회사 격리, 진단 IS -50/대체 제외 손익 50/차이 100의 정확한 Decimal 대사, 대체 Journal의 두 POSTED line 추적, 원천 부족/stale null 반환, 차단 시 생성 실패 및 Journal 미변경. 기존 승인 분리·Snapshot 불변성·배당 지급·Notes·PDF/XLSX/CSV assertion은 보존한다.

SCE 원천 조회 경쟁 응답은 마지막 선택과 같은 기간/Snapshot일 때만 반영한다. 프론트 정적 검사와 허용된 내부 후속 경로의 최소 단위 검증을 수행한다. 전체 Golden/연간 synthetic/전체 regression/브라우저 E2E를 이번 변경의 증거로 주장하지 않는다.

## #112를 종료하기 위한 남은 선행 계약

연말 hard close의 명시적 기간/원천 identity·정책·승인·재개·재마감, ADJUSTED/POST_CLOSING과 IS 표시의 관계, 전기 누적손익/당기손익의 구분, 새 불변 Snapshot 및 CF/Notes와의 교차 대사 계약을 확정해야 한다. 기존 승인본과 POSTED Journal을 재작성하거나 Event 이름만 보고 손익을 제거하는 구현은 허용하지 않는다. 실제 고객 Pilot과 운영 출시 조건은 별도 마일스톤이다.

## 실제 실행 결과

로컬 Docker PostgreSQL의 개발 DB와 분리된 `accounting_pilot_test`에서 SCE·Notes·Closing·Journal·Report Center·migration 6개 파일을 실행했다. **19 passed, skip 0, 220.46초**이며 GenAI 의존성 deprecation 경고 1건이 있다. 이는 합성 fixture 기반 검증으로 실제 고객 회계 승인이나 법정 공시 검증을 뜻하지 않는다.

아키텍처·모듈 경계·재무제표 계산 규칙·Export 렌더 subset은 **33 passed**다. 변경 backend Ruff/format/mypy와 frontend lint/typecheck가 통과했으며 frontend **59 passed**다. 원본 fixture expected와 기존 고가치 assertion은 약화하지 않았다.

과거 IS Snapshot의 stale 진단 전후 동일성을 추가 확인한 최종 SCE subset도 **3 passed, skip 0, 55.32초**로 통과했다. 물리적 손익 대체 사례의 기존 BLOCKED assertion은 그대로 유지한다.
