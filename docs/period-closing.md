# 월마감 V1 계약

설계 정본은 Google Drive `AI_Accounting_Office_v0.2.6_통합설계_정본`의 `결산_기간마감_조정_역분개` 및 Physical ERD·API·상태전이·권한 문서입니다. 구현 기준은 PR #14 병합 후 main `f1915db34688e6dc41b46f0db08ef8a843e41520`입니다.

## 상태와 계산 경계

회계기간은 전용 명령으로 `OPEN → CLOSING → CLOSED`가 됩니다. `CLOSING`에는 일반 전표의 신규 작성·기표를 막고, 결산 실행에 연결된 `CLOSING` 원천 전표만 기존 Journal 명령을 통해 승인·기표할 수 있습니다. `CLOSED`의 일반 기표는 기존 기간 잠금이 차단합니다. 재개는 별도 승인과 이유를 요구하며, 과거 Closing Run을 삭제하지 않고 마감 버전을 증가시킵니다.

결산 실행은 장부 잔액 정본이 아닙니다. 장부 숫자는 POSTED Journal Line과 기존 Trial Balance, AR/AP 및 Bank/Card 대사 Application의 결과에서 읽습니다. 실행에는 장부·금융 대사·조정 상태 digest를 고정합니다. 새로운 거래, 기표, 금융대사, 조정 상태 변경으로 digest가 바뀌면 기존 승인이나 마감 명령이 `CLOSING_RUN_STALE`로 실패하며 검사를 다시 실행해야 합니다.

검사 결과는 `PASS`, `WARNING`, `BLOCKER`로 저장합니다. V1 차단 항목은 미처리 거래, 미승인 전표, 미대사 은행/카드, AR/GL·AP/GL 차이, 시산표 불균형, 미완료 필수 조정입니다. 회계일과 거래일이 다른 컷오프 자료는 검토용 `WARNING`입니다. 자동 조정분개로 차이를 감추지 않습니다. Asset/Inventory/Cost/Tax 미구현 모듈은 V1 필수 차단 항목이 아닙니다.

Bookkeeper의 `closing.readiness`는 이 결정론적 검사 결과를 읽기 전용으로 전달합니다. `AI 회계팀` 화면에서 차단 항목을 물으면 검사 코드와 영향 금액을 표시하지만 마감·재개나 조정을 실행하지 않습니다.

## 조정과 승인

지원 조정 유형은 `ACCRUED_EXPENSE`, `ACCRUED_REVENUE`, `PREPAID_EXPENSE_RELEASE`, `UNEARNED_REVENUE_RELEASE`, `MANUAL_CUTOFF_ADJUSTMENT`입니다. 조정 생성은 균형 잡힌 Journal DRAFT를 만들고, 기존 제출→검토 요청→다른 사용자 승인→Posting을 거칩니다. 결산이 GL을 직접 바꾸지 않습니다. 다음 기간 자동 역분개 옵션은 예정일을 기록하며, 실행 시 기존 Reversal 명령으로 다음 열린 기간에 DRAFT만 만듭니다. 스케줄러나 무승인 자동기표는 포함하지 않습니다.

최종 마감·재개는 요청자와 다른 활성 권한자의 승인을 필요로 합니다. 마감은 최신 실행, 차단 0건, 게시된 필수 조정, 유효한 승인과 현재 digest를 기간 row lock 안에서 확인하고 기간·마감 버전·실행·승인·감사 이벤트를 원자적으로 변경합니다. 재개 역시 승인과 이유를 기록하고 새 결산 주기를 시작할 수 있도록 과거 실행 이력을 보존합니다.

## API와 권한

조회: `GET /closing/periods`, `GET /closing/periods/{id}/runs`, `GET /closing-runs/{id}`, `GET /closing-runs/{id}/approvals`, `GET /closing-runs/{id}/trial-balance?stage=UNADJUSTED|ADJUSTED`.

명령: `POST /closing-runs`, `POST /closing-runs/{id}/checks`, `POST /closing-runs/{id}/adjustments`, `POST /closing-runs/{id}/submit`, `POST /closing-approvals/{id}/approve`, `POST /closing-runs/{id}/close`, `POST /closing-runs/{id}/reopen-request`, `POST /closing-runs/{id}/reopen`, `POST /closing-adjustments/{id}/reversal`.

명령은 로그인, 활성 회사 membership, `X-Company-ID`, CSRF, `Idempotency-Key`, 회사별 권한을 서버에서 검사합니다. 필요한 권한은 `period.read`, `period.start_closing`, `period.close`, `period.reopen.request`, `period.reopen.approve`, `period.reopen.execute`이며 조정·역분개는 기존 Journal 권한도 요구합니다. 다른 회사 UUID는 조회·변경할 수 없습니다. 같은 key와 같은 입력은 기존 결과를 재생하고 다른 입력은 `IDEMPOTENCY_CONFLICT`입니다.

## 관계형 스키마와 후속 경계

`015_period_closing`은 `closing_runs`, `closing_checks`, `closing_adjustments`, `closing_approvals`, `closing_events`, `closing_commands`를 추가하고 회계기간 상태·마감 버전을 확장합니다. 회사 복합 FK, 활성 실행 부분 유일 인덱스, 검사 버전 유일성, typed status/CHECK를 둡니다. 원본 prompt/전표 payload/검사 결과 JSON blob을 저장하지 않습니다.

후속 BS/IS는 `CLOSED` 기간, 마감 버전, 실행 ID, `ADJUSTED` Trial Balance와 digest, 대사 digest를 명시적 Application 조회로 사용합니다. BS/IS Snapshot·Asset·Inventory·Cost·Tax·연말 물리적 손익마감은 이번 범위가 아닙니다.
