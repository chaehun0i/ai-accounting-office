# 확정 가져오기에서 정규 거래로 승격

## 기준과 범위

시작 main은 `8577111c93e48c55d4f04368e1e5653cd6a19871` / PR #11이며 시작 시 열린 PR·Issue는 없었습니다. 설계 SSOT는 [AI_Accounting_Office_v0.2.6_통합설계_정본](https://drive.google.com/drive/folders/14f9qJtr7eKzC12n8GpdHcNc3Ff2nyYpf)입니다. 이전 버전이나 Archive fallback은 사용하지 않았습니다.

활성 00의 읽기안내·로드맵, 03의 Excel/CSV Mapping·Intake Physical Schema·Onboarding·Evidence, 07의 Physical DDL·Migration Map·API·Error/Idempotency/Concurrency·Repository Architecture·Relational-First·Permission·State Transition, 08의 Golden·DoD·Coverage, 09의 샘플 가이드와 실제 파일 metadata를 확인했습니다. 문서의 일부 과거 target 명칭 `ACCOUNTING_TRANSACTION` 대신 현재 API의 `TRANSACTION_CANONICAL` 계약을 유지합니다.

기존 업로드·파서·매핑·검증·Preview·Confirm과 Transaction을 재구현하지 않았습니다. 새 경계는 `intake/promotion`의 Domain/Application/Infrastructure입니다. 동기 승격은 정규 거래까지만 생성하며 Journal·Posting·Invoice·Bank/Card·Closing·Tax·Agent mutation은 제외합니다.

## 사용자 흐름과 API

파일 업로드 → 항목 연결 → 검증·미리보기 → 명시적 접수 → **파일 확인 완료** → **확인한 자료로 거래 생성** → 영수증 → 생성된 거래 보기입니다. 업로드·접수·거래 생성 모두 장부 반영과 다릅니다. 실패하면 파일을 다시 올리지 않고 같은 접수에서 재시도합니다.

`POST /imports/{id}/promote`는 `Idempotency-Key`, 인증, `X-Company-ID`, CSRF와 다음 엄격한 Pydantic body를 요구합니다. extra 입력은 거부합니다.

```json
{"expected_version": 3, "receipt_id": "영수증 UUID", "source_digest": "SHA-256 64자리"}
```

`expected_version`은 현재 화면의 임의 버전이 아니라 영수증의 `confirmed_version`입니다. `GET /imports/{id}/receipt`는 거래 수·review 수·failed 수·행 위치·source ID·거래 UUID·CREATED/REUSED·review code를 반환합니다. 전체 API 응답은 DB에 저장하지 않습니다.

`TRANSACTION_CANONICAL`은 `PREVIEW_READY → CONFIRMED → IMPORTING → COMPLETED`입니다. Confirm은 거래 0건인 CONFIRMED 영수증을 만듭니다. 승격의 IMPORTING과 COMPLETED는 같은 transaction에서 반영되므로 실패하면 CONFIRMED로 돌아갑니다. 기존 DOMAIN_MASTER/ONBOARDING_DRAFT 접수 계약은 유지합니다. 기초잔액·거래처 Master는 이 Transaction 승격의 지원 대상이 아닙니다.

## 결정론적 변환

지원 source는 BANK_TRANSACTION, CARD_TRANSACTION, SALES, PURCHASE, EXPENSE입니다. amount/tax_amount는 유한한 Decimal과 NUMERIC(19,4) 범위를 검사하며 현재 기능통화는 KRW만 허용합니다. accounting_date는 명시값 또는 transaction_date입니다. 매출 기본 방향은 INFLOW, 매입·비용은 OUTFLOW이고 은행 거래는 명시적 direction이 필요합니다. payment_method는 BANK/CARD/CASH/UNSPECIFIED입니다.

원천 ID는 제한된 안전 문자와 길이를 검사합니다. 경제적 fingerprint는 정규화 날짜·금액·세액·방향·통화·원천 유형·적요·지급방법·stable 거래처 코드로 구성하며 Import UUID나 행 위치는 넣지 않습니다. 영수증 digest는 검증 행의 결정론적 digest 집합을 바인딩합니다.

거래처는 회사 내 `counterparty_code` 정확 일치만 연결합니다. 이름만 있거나 코드가 미해결·비활성이면 자동 추측하지 않고 NULL 거래처, NEEDS_INFORMATION, COUNTERPARTY_UNRESOLVED review를 남깁니다. 세액은 입력 source fact이며 세법 판정이나 신고 정답이 아닙니다.

## 원자성·재시도·보안

Promotion은 기존 `TransactionService.save_in` Application command를 호출합니다. 호출자 UoW 한 개가 모든 Transaction·행별 참조·Receipt·멱등 요청을 함께 commit/rollback합니다. Repository는 독립 commit하지 않습니다. fatal conflict가 하나라도 있으면 거래·승격 이력이 일부 남지 않습니다. 검토 필요 행은 명시적으로 review와 거래 상태를 반환하며 성공으로 숨기지 않습니다.

멱등 scope는 company/actor/IMPORT_PROMOTE/key이고 fingerprint는 import/receipt/source digest/확정 version/target/version을 포함합니다. 동일 key·동일 fingerprint는 같은 영수증을 반환하고 다른 fingerprint는 IDEMPOTENCY_CONFLICT입니다. 다른 key로 같은 Import를 요청해도 완료 영수증을 재사용합니다.

요청 advisory lock, Import row lock, 회사·source_system·source_id의 transaction advisory lock을 사용합니다. 원천 잠금 순서는 source ID 정렬로 고정합니다. Transaction의 기존 UNIQUE(company_id, source_system, source_id)가 최종 중복 방어선입니다. 같은 원천·같은 경제적 fingerprint는 REUSED, 다른 내용은 IMPORT_SOURCE_CONFLICT이며 overwrite하지 않습니다.

현재 membership·업로더·import.confirm·transaction.create를 매번 검증합니다. 타 회사는 기존 RESOURCE_NOT_FOUND 정책을 유지합니다. 파일 SHA-256, 확정 매핑 digest, receipt/version, source digest를 재검증하며 Preview TTL 만료 후에도 원본 파일과 확정 매핑으로 검증합니다. DB 오류나 원본 cell 전체를 응답·로그에 노출하지 않습니다.

## Migration과 출처

`012_import_transaction_promotion`은 배포된 004/006/011을 변경하지 않는 forward revision입니다.

- `import_promotion_rows`: 회사/Import/Receipt/행 위치/source ID/row digest/거래 FK/CREATED·REUSED/review code/시각.
- `import_promotion_commands`: 회사/actor/command/key/fingerprint/Import/Receipt/시각.
- `import_receipts`: confirmed_version, promoted_at, count CHECK 변경, composite UNIQUE.

행 위치와 source ID UNIQUE, 회사·Receipt 및 회사·Transaction composite FK, RESTRICT, status/locator/command/version CHECK, FK 조회 indexes를 둡니다. 기존 거래 0건인 canonical COMPLETED 접수는 CONFIRMED로 정렬합니다. 승격 이력이 없는 격리 DB는 011↔012 왕복할 수 있습니다. 승격 이력이 있으면 downgrade가 명시적으로 차단되며 백업 복구나 후속 수정 migration을 사용합니다.

거래는 import_id와 원본 SOURCE Evidence FK를 보존합니다. 재사용 거래의 최초 출처는 변경하지 않고 새 Import의 promotion row가 해당 거래를 참조합니다. `Transaction ← promotion row → Receipt/Import → Evidence → Storage Object`로 추적하며 원본 행·파일 bytes를 DB에 복제하지 않습니다. typed command/row 이력은 별도 JSON 감사 문서를 저장하지 않고 재시도·추적 근거를 제공합니다.

## 참고 코드 판단

ServIQ `chaehun0i/fnb-voc-intelligence`의 실제 commit `1ccb790f1b8b79863fbd42e727287dee65aca866`에서 다음 파일을 읽었습니다. 직접 COPY와 다른 외부 저장소 이식은 없습니다.

| 기존 파일 | 판정 | 사용한 개념 / 제외한 의존성 |
| --- | --- | --- |
| backend/src/application/data_intake.py | PATTERN | digest binding·명시적 확인·UoW / tenant·store·VOC·Incident 제거 |
| backend/src/application/intake_schema.py | PATTERN | deterministic alias·행 검증·원천 식별 / 기존 관측 schema 제거 |
| backend/src/infrastructure/repositories/idempotency_repository.py | PATTERN | claim·fingerprint·replay / JSONB result 저장 DROP |
| backend/src/infrastructure/data_intake.py | DROP / PATTERN 일부 | 원천 충돌·transaction lock 개념만 / Jsonb document·tenant/store persistence DROP |
| backend/src/api/routes/data_intake.py | PATTERN | Preview/Confirm·오류 경계 / 기존 route/domain 복사 없음 |
| 현재 IntakeService·digest | ADAPT | 기존 파일·매핑·검증·순수 digest 재사용 |
| 현재 TransactionService·Repository | ADAPT | save_in으로 호출자 UoW 공유, source lock 보강 |
| 현재 Evidence·회사/RBAC | PATTERN/ADAPT | 회사 scope·원본 증빙·기존 권한 유지 |
| 현재 Jobs | DROP for current scope | 1,000행 동기 처리로 충분하여 새 Worker 미도입 |

## Fixture와 제한

기존 `native-2025-v1` snapshot과 모든 기존 Golden expected는 수정하지 않았습니다. 새 테스트 adapter v1이 Sales_Invoices 240행, Purchase_Invoices 74행을 CSV로 변환하여 실제 Upload→Confirm→Promote를 수행합니다. 314개 source identity, 유입 **781,044,000**, 유출 **195,277,500**, 모든 거래의 Import/Evidence FK와 replay를 exact 비교합니다. 모호한 거래처는 검토 상태로 보존합니다.

Drive 09 실제 파일은 native SERVICE, RETAIL, SAMPLE_COMPANY_2025 세 개와 가이드, 추가 legacy `_v1.xlsm`입니다. 공식 regression 정본은 native Sheet 세 개이며 macro-enabled artifact는 공식 업로드 fixture가 아닙니다. 파일 삭제·수정은 하지 않았고 Drive 문서/폴더 정리는 후속 항목입니다. 필요한 Sales/Purchase snapshot의 SHA-256은 기존 fixture README를 따릅니다.

현재 안전 한도 2MB·1,000행·40열·5시트와 15분 Preview를 유지합니다. 50,000행 지원을 주장하지 않습니다. 지원 한도에서의 승격 benchmark와 최종 검증 결과는 아래에 기록합니다. 더 큰 입력은 성능·lock 시간·원자성 검토 후 기존 Jobs 기반 Worker/chunk 정책이 필요합니다. 현재 사람 권한의 명시적 API만 제공하며 Agent mutation Tool은 추가하지 않았습니다.

## 검증 기록

2026-10-12 KST 검증입니다. 서로 다른 실행의 passed를 합산하지 않습니다.

| 실행 | 실제 결과 |
| --- | --- |
| CI `python -m pytest --ignore=tests/integration` | 230 passed, 1 warning, 6.52초 |
| CI `python -m pytest tests/integration --require-postgres` | 165 passed, 1 skipped, 1 warning, 352.29초 |
| 로컬 Docker 승격 집중 통합 3개 파일 | 17 passed, 1 warning, 117.64초 |
| Ruff check / format check / mypy / pip check | CI 모두 통과 |
| Alembic current / upgrade / check-heads / check | 012 단일 head, metadata diff 없음 |
| migration lifecycle | 빈 DB→head, base 왕복, 011↔012 포함 이전 revision 왕복 통과 |
| schema verifier | 업무 table 72, FK 176, orphan 0, JSON 0, JSONB 0 |
| framework schema verifier | 해당 검증 DB 정리 후 JSON/JSONB 0, 기존 checkpoint allowlist 유지 |
| Frontend npm ci / lint / typecheck / test / build | Linux CI 모두 통과, test 29 passed / 0 failed |
| Docker Compose config / build / up --wait / ps | 통과, backend/frontend/PostgreSQL/Redis 모두 healthy |
| Edge headless 실제 UI | 로그인→CSV 매핑·미리보기→Confirm 거래 0→Promote 거래 2→reload→동일 키 replay→거래 화면→회사 전환 격리 통과 |
| 정적 경계 | 신규 Promotion 금지 legacy 식별자·Repository commit·float 0, 기존 architecture guard 통과 |

위 CI evidence는 [Quality 38149424227](https://github.com/chaehun0i/ai-accounting-office/actions/runs/38149424227)입니다. 최종 문서 커밋 및 PR에서도 동일 CI를 재실행합니다. 기존 Accounting/Finance/Agent/Dimension/연간 Golden은 통합 실행에 포함되며 기존 expected를 변경하지 않았습니다. 동시 요청은 같은 키·다른 키·다른 Import의 같은 원천·충돌 원천 네 경우를 실제 독립 PostgreSQL transaction으로 검증했습니다. 파일 변조·매핑 변경·확정 버전·권한 회수·다른 업로더·CSRF·타 회사·미지원 통화·모호한 거래처·실패 후 재시도도 검증했습니다.

지원 한도 benchmark는 마지막 집중 실행에서 **1,000행 32.153초**였습니다. 비교용 직전 실행은 22.779초였으며 다른 회귀·브라우저·DB 부하가 동시에 실행된 로컬 Docker 환경입니다. 50,000행/120초 Gate를 달성했다고 해석하지 않습니다. 현재는 1,000행 동기 원자 승격을 지원합니다.

Windows 호스트 `npm ci`는 npm의 `Exit handler never called`로 실패했고 재시도도 중단했습니다. 그 상태의 호스트 lint/typecheck/build는 실행 파일 누락으로 실패했습니다. 이를 성공으로 기록하지 않았으며 Linux CI의 clean npm ci와 전체 검사, Docker production build를 별도로 통과했습니다. 호스트 Node 설치 환경 복구는 기능 변경과 구분되는 제한입니다. Gemini SDK의 Python 3.14 deprecation warning 1건은 기존 의존성 경고이며 실제 Gemini 네트워크 테스트는 opt-in 없이 실행하지 않았습니다.

브라우저·집중 검증 전용 임시 DB는 실행 종료 시 삭제합니다. 기존 사용자 DB나 원본 fixture를 삭제·변경하지 않습니다. 수동 접수는 브라우저 sessionStorage에 회사별 Import UUID만 남기며 원본 행·인증정보는 저장하지 않습니다. 여러 회사가 있는 사용자가 전체 새 페이지로 이동하면 기존 Company Context 정책에 따라 회사를 다시 선택해야 합니다.

다음 후보는 최신 로드맵의 Business Document — Invoice / Credit Note이며 이번 PR에서 선행 구현하지 않습니다.
