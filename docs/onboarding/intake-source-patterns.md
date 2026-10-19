# 인테이크 참고 코드와 설계 충돌

실제 확인한 저장소는 [chaehun0i/fnb-voc-intelligence](https://github.com/chaehun0i/fnb-voc-intelligence), 고정 커밋은 `1ccb790f1b8b79863fbd42e727287dee65aca866`입니다.
파일별 내용을 읽어 아래 패턴만 반영했습니다. 원본 history의 merge/subtree나 런타임 의존은 없으며 COPY 대상은 없습니다.

| 실제 source file | 판정 | 신규 file / 참고·제거·변경 |
| --- | --- | --- |
| [application/data_intake.py](https://github.com/chaehun0i/fnb-voc-intelligence/blob/1ccb790f1b8b79863fbd42e727287dee65aca866/backend/src/application/data_intake.py) | ADAPT | intake/application/service.py: requester binding, Preview/Confirm, atomic idempotency. 조직/매장·분석·샘플·기존 persistence를 제거하고 company/UoW/Receipt로 재작성 |
| [application/intake_schema.py](https://github.com/chaehun0i/fnb-voc-intelligence/blob/1ccb790f1b8b79863fbd42e727287dee65aca866/backend/src/application/intake_schema.py) | ADAPT | intake/domain/canonical_fields.py, validation.py: 단일 Registry와 alias/type/required 공유. 기존 관측 schema를 은행/카드/회계 입력 필드로 대체 |
| [infrastructure/intake_workbook.py](https://github.com/chaehun0i/fnb-voc-intelligence/blob/1ccb790f1b8b79863fbd42e727287dee65aca866/backend/src/infrastructure/intake_workbook.py) | ADAPT | intake/infrastructure/parser.py: ZIP·macro·link·formula·크기 방어. 한계값과 오류를 새 계약으로 정하고 float 변환 없는 제한적 OOXML parser로 재작성. 원본은 별도 Storage에 보존 |
| [api/routes/data_intake.py](https://github.com/chaehun0i/fnb-voc-intelligence/blob/1ccb790f1b8b79863fbd42e727287dee65aca866/backend/src/api/routes/data_intake.py) | PATTERN | intake/api/router.py, schemas.py: bounded multipart와 explicit Confirm. 기존 URL·분석·샘플 API를 제거하고 /imports resource와 기존 인증/CSRF를 사용 |
| [repositories/idempotency_repository.py](https://github.com/chaehun0i/fnb-voc-intelligence/blob/1ccb790f1b8b79863fbd42e727287dee65aca866/backend/src/infrastructure/repositories/idempotency_repository.py) | PATTERN / 물리 저장 DROP | import_confirmations/import_source_records/import_receipts: fingerprint conflict와 replay 개념만 참고. Jsonb(result_document(result))와 전체 응답 저장 제거, typed FK로 재조회 |
| [tests/test_data_intake.py](https://github.com/chaehun0i/fnb-voc-intelligence/blob/1ccb790f1b8b79863fbd42e727287dee65aca866/backend/tests/test_data_intake.py) | PATTERN | tests/unit/test_intake_*.py, tests/integration/test_intake_*.py: Preview 비정본, atomic/idempotent Confirm, stale·파일 보안·scope 테스트. 기존 Domain fixture는 제거 |
| [serviq_onboarding_import_smoke.py](https://github.com/chaehun0i/fnb-voc-intelligence/blob/1ccb790f1b8b79863fbd42e727287dee65aca866/scripts/serviq_onboarding_import_smoke.py) | PATTERN | 실제 PostgreSQL API 통합·동시성 테스트: 업로드→접수→영속 조회 패턴. Worker/Agent/분석 검증을 제거하고 Storage/Evidence/Receipt를 검증 |
| [features/data/DataImport.tsx](https://github.com/chaehun0i/fnb-voc-intelligence/blob/1ccb790f1b8b79863fbd42e727287dee65aca866/frontend/src/features/data/DataImport.tsx) | PATTERN | frontend/src/features/imports/data-import.tsx: mapping 수정 시 Preview/동의 무효화, 명시적 접수와 key 유지. 기존 store·routing·브랜드·공통 컴포넌트 의존 제거 |
| [features/data/Onboarding.tsx](https://github.com/chaehun0i/fnb-voc-intelligence/blob/1ccb790f1b8b79863fbd42e727287dee65aca866/frontend/src/features/data/Onboarding.tsx) | DROP for current scope | 시작 방법 선택·샘플·runtime 초기화·분석 동선을 구현하지 않음. Onboarding Workspace는 후속 v0.2.5 gate에서 직접입력 Form + Excel 버튼 정책으로 별도 작성 |

## 실제 충돌과 처리

- 원본의 결과 document JSONB 저장은 Relational-First와 충돌하므로 제거했습니다. 회사·actor·key·fingerprint·Receipt FK만 저장합니다.
- 원본 Preview의 persistence row document는 채택하지 않았습니다. Preview rows는 요청 메모리에서만 생성하고 900초 유효한 digest/expiry를 기록하며 Confirm이 원본을 다시 파싱합니다.
- 조직+매장 scope는 company_id와 서버 membership/permission 검사로 대체했습니다. 기존 resource 이름과 sample/demo 의미는 runtime에 남기지 않았습니다.
- 원본 schema는 회계 정본 필드로 새로 정의했습니다. Receipt가 있다고 Transaction/Journal을 먼저 생성하지 않습니다.
- 원본 Excel library의 value 변환을 그대로 가져오지 않고 숫자 문자열을 유지했습니다. Decimal 검증과 1900/1904 date epoch를 deterministic code가 처리합니다.
- 원본 Onboarding의 경쟁하는 시작 선택 화면은 v0.2.5 UX 보강과 충돌하므로 사용하지 않았습니다. 현재 화면은 독립적인 Import 기능이며 Onboarding Draft merge가 아닙니다.

새 Storage·Evidence·관계형 Import 모델/복합 FK·회사 UoW wiring은 NEW입니다. 다른 프로젝트의 Finance/Auth/Agent 코드는 이번 범위에서 가져오지 않았습니다.
