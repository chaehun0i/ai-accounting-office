# 은행·카드 원천과 장부 대사

설계 SSOT는 [v0.2.6 활성 설계](https://drive.google.com/drive/folders/14f9qJtr7eKzC12n8GpdHcNc3Ff2nyYpf)이며 fallback/Archive를 사용하지 않았습니다. 구현 시작 main은 `91918e98312204ee72b660b8d6550ae64ed07b67`(PR #13)입니다. Invoice를 다시 구현하지 않았습니다.

## 사용자 흐름과 회계 경계

은행 대사 또는 카드 대사에서 관리자가 원번호 대신 별칭과 명시적 장부 통제계정을 연결합니다. 기존 파일 가져오기 화면의 업로드→Mapping→검증→Preview→Confirm을 거쳐 원천을 생성합니다. 은행은 기간과 기초·기말잔액을 추가로 확인합니다. 후보의 근거와 배분액을 검토해 초안을 저장하고 사람이 확정합니다. 해제에는 사유가 필요하며 기존 연결 이력은 삭제하지 않습니다.

은행 입출금과 카드 승인은 매출·비용이나 Posting이 아닙니다. 현재 대상은 확정 Collection/Payment와 Canonical Transaction입니다. Expense/급여/대출 전용 Domain을 가짜 대상으로 만들지 않았습니다. Source를 생성하거나 대사해도 Journal/GL을 쓰지 않습니다. 전표 없는 대상은 연결 가능하지만 GL 차이는 남습니다.

카드 용도는 `CORPORATE`(법인카드 사용, CARD_PAYABLE 부채)와 `MERCHANT`(카드매출 수납, CARD_CLEARING 자산)를 구분합니다. 은행은 BANK_CASH 자산입니다. 계정명을 추측하지 않고 설정된 계정 ID와 control role을 사용합니다. 현재 한 통제계정은 같은 종류의 한 별칭에만 연결할 수 있습니다.

## 상태·계산·잠금

명세는 IMPORTED→RECONCILING→CLOSED, 대사는 DRAFT→CONFIRMED→UNMATCHED입니다. source의 UNMATCHED/PARTIAL/MATCHED는 확정 match line 합계로 계산합니다. AUTHORIZED/CANCELLED/REVERSED 카드 원천은 REVIEW로 보존하고 금액 대상으로 확정하지 않습니다. REFUNDED는 반대 현금 방향의 별도 원천 사실입니다. 같은 issuer identity의 경제적 내용 변경은 overwrite 대신 source conflict입니다.

금액은 Decimal/NUMERIC(19,4), 정규화된 source fingerprint, 외부 source ID와 company/account/system identity로 중복을 방어합니다. ID가 없으면 원천 행의 결정적 digest를 사용합니다. 모든 Import 원본 행을 JSON으로 보존하지 않습니다. source→Import/Receipt/sheet/row→Transaction/Settlement를 관계형 FK와 locator로 추적합니다.

동일 Confirmed Import는 최초 연결 계좌·카드에 묶입니다. 다른 key로 재시도해도 동일 원천을 재사용하고, 같은 파일 접수를 다른 별칭에 재승격하면 company lock 안에서 SourceConflict로 차단합니다. 계좌/카드별 외부 source ID unique와 별도로 Import 재사용 경계를 적용합니다.

대사 초안에는 source/target version을 저장합니다. 확정·해제는 회사 단위 PostgreSQL advisory transaction lock 안에서 상태·version·이미 소비한 금액을 다시 읽습니다. source별/target별 신규 합계가 남은 금액을 초과하면 422 `RECONCILIATION_AMOUNT_EXCEEDED`, stale 후보는 409 `RECONCILIATION_SOURCE_STALE`입니다. 다른 회사 UUID는 기존 404/403 계약으로 차단합니다. Repository는 commit하지 않습니다.

P0 Import/대사/해제/차이 기록/명세 마감 명령의 key scope는 company+actor+command+Idempotency-Key입니다. 이벤트에 fingerprint와 typed resource reference를 보존합니다. 동일 fingerprint는 resource를 replay하고 다르면 409입니다. 이력 조회는 현재 resource 상태이며 raw response snapshot을 DB에 저장하지 않습니다. 별칭 설정은 company lock과 UNIQUE로 중복을 거부하는 Master 설정 명령입니다.

## 후보 정책과 차이

중앙 `MatchingPolicy` 기본값은 날짜 차이 7일, 금액 tolerance 0, 자동 후보 점수 90, 검토 후보 40, materiality 0입니다. 회사별 관계형 policy/version과 Application 변경 계약을 제공하지만 이번 UI에는 policy 편집을 넣지 않았습니다. 정확한 잔여 금액 60점/부분 금액 20점, 날짜 20점에서 일수별 2점 차감, 동일 참조 15점, 거래처 정확 일치 5점입니다. direction과 source 상태를 먼저 검사하고 동점은 안정적인 identity 순서로 정렬합니다. AUTO_MATCHED는 우선 검토 후보이며 자동 확정이 아닙니다.

후보의 REVIEW_CANDIDATE는 조회 시 계산하는 분류이고 원천 REVIEW와 구분합니다. 은행의 미확정 후보는 source UNMATCHED를 유지하며, 원천 REVIEW는 현재 확정 대상이 아닌 카드 상태를 나타냅니다. 후보 점수만으로 원천 상태를 확정하지 않습니다.

은행은 명세 기말잔액, 기초잔액+확정 source 흐름, 명시적 GL 계정 잔액을 각각 반환합니다. 입력 명세가 기초+입금−출금과 다르면 422 `BANK_STATEMENT_NOT_BALANCED`이며 전체 source 승격을 rollback합니다. 카드 summary는 사용/환불 및 명시적 통제계정에 연결된 POSTED 지급·정산 target의 확정 은행대사를 별도로 반영합니다. 복수 경제사건이 섞인 지급전표를 임의 비례 배분하지 않습니다.

차이 원인은 TIMING_ITEM/MISSING_TRANSACTION/DUPLICATE_SOURCE/WRONG_ACCOUNT/MANUAL_ADJUSTMENT_CANDIDATE/UNKNOWN으로 남깁니다. 해결 근거·actor·시각·version을 보존해도 GL은 바뀌지 않습니다. 차이/미대사/부분/검토/미해결 item은 `blocker`를 반환하고 명세 마감을 막습니다. Closing/Period Close는 구현하지 않았습니다.

## API와 권한

기존 전역 convention에 따라 root path를 사용합니다. `/bank-accounts`, `/card-accounts`, `/card-transactions/imports`, `/card-transactions/{id}/match-candidates`, `/card-accounts/{id}/summary`는 카드/별칭 capability를 위한 명시적 확장입니다. 설계의 `/bank-statements/imports`, `/bank-statements/{id}`, `/bank-statements/{id}/match-candidates`, `/reconciliations`, `/{id}/confirm`, `/{id}/unmatch`, `/bank-statements/{id}/close`, `/reconciliation/summary?period_id=...`를 제공합니다. 원천·이력·item/resolve 조회 및 명령도 제공합니다. 상태 PATCH는 없습니다.

모든 endpoint는 인증·활성 membership·X-Company-ID를 검사하고 mutation은 CSRF를 요구합니다. READ는 `reconciliation.read`, 대사 변경은 `reconciliation.manage`, 별칭/통제계정 연결은 추가 `control_account.manage`, 명세 마감은 `bank_statement.close`를 요구합니다. 입력은 extra forbid, 닫힌 enum, Decimal/date입니다. Agent mutation Tool은 추가하지 않았습니다.

## 스키마와 배포

기존 009에는 reconciliation_matches/lines만 실제 존재했습니다. 이를 재사용하고 `014_bank_card_reconciliation`에서 8개 테이블(bank_accounts/card_accounts/bank_transactions/card_transactions/bank_statements/reconciliation_policies/reconciliation_items/reconciliation_events)을 추가합니다. 기존 013 이하 migration은 변경하지 않았습니다. company composite FK, typed source/target FK, unique identity, 금액·상태·version CHECK와 FK 인덱스를 추가합니다. 원천 경제적 사실은 UPDATE/DELETE trigger, event와 match line은 append-only trigger로 보호합니다.

빈 DB upgrade 및 metadata diff, 013↔014 clean round-trip을 검사합니다. 사용자 금융 데이터가 있는 downgrade와 기존 placeholder match line이 있는 upgrade는 임의 소실/가짜 FK backfill 대신 거부합니다. 운영 rollback은 복구 절차가 필요합니다. Framework LangGraph schema는 변경하지 않았습니다.

## 재사용과 제외

현재 Intake/Storage/Evidence/confirm digest와 Finance UoW·RBAC·Ledger query를 ADAPT했습니다. `nobadai/mainproject` commit `516449c08feb3d065d36d6c556eb59d14625d5d8`의 collection.py와 settlement.py는 Decimal/잠금/transaction ownership PATTERN, cash_adjustments.py는 explicit event 아이디어만 PATTERN이고 직접 현금 조정은 DROP, closing.py는 unresolved 검증 경계만 PATTERN입니다. COPY는 없습니다. simulation 전용 identity와 직접 SQL finance state는 가져오지 않았습니다.

실제 은행/카드사 API, 자동 이체/지급, Treasury 전체, Expense/Loan 전체, Closing V1, 재무제표, Tax, OCR, Remote MCP/새 Agent는 제외합니다. 다음 후보는 최신 main/Drive 재확인 후 Closing V1입니다.

## 현재 제한

- KRW와 기존 Intake 안전 제한(2,000,000 bytes, 1,000행, 40열, 5 Sheet)을 유지합니다. 날짜 원천은 UTC 자정으로 정규화하며 시각 단위 은행 전문 adapter는 후속입니다.
- 동시성 안전을 위해 회사 단위 직렬화를 사용합니다. 대규모 병렬 처리와 Worker는 이번 범위가 아닙니다.
- 대상 조회에 원천·연결 합계 query가 추가됩니다. 연간 source 규모 측정은 별도 검증 기록에 남기며 50k/120초나 API p95를 달성했다고 주장하지 않습니다.
- PG 수수료/환불 회계사건을 자동 생성하지 않습니다. 순정산과 총액 차이는 item/차이로 남깁니다.
- source fact 정정은 기존 ID overwrite가 아닌 별도 원천 ID와 정정 관계가 필요합니다. 전체 issuer lifecycle connector는 후속입니다.
- [공식 fixture 스냅샷과 버전](../../backend/tests/fixtures/reconciliation/README.md), 실제 실행 결과는 검증 문서를 따릅니다.
