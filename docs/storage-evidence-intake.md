# 파일·증빙·데이터 인테이크

시작 main은 `f56ac91b078c11aa7e14c324446fb365aaef2811`, 작업 브랜치는 `feat/storage-evidence-intake`입니다.
원격 main을 fetch하고 fast-forward pull한 후 기존 head `003_master_accounting_settings`를 확인했습니다.
단일 기준선은 [AI_Accounting_Office_v0.2.5_통합설계_정본](https://drive.google.com/drive/folders/14f9qJtr7eKzC12n8GpdHcNc3Ff2nyYpf)이며 fallback은 사용하지 않았습니다.

## 직접 확인한 설계

| 문서 | 반영 |
| --- | --- |
| [구현순서·개발게이트](https://docs.google.com/document/d/1Bq48BGoGW7A8hRHMoA2kb1j3NU26Qb-X-8o3VnjvAVQ/edit) | Storage/Evidence/Intake만 구현, Onboarding·Transaction 분리 |
| [기존프로젝트 재사용](https://docs.google.com/document/d/1Oh9_oaR9S_Xb5u9YLrff43AfLP1K2zEOaJsy1DBsBi8/edit) | 파일별 ADAPT/PATTERN/DROP |
| [Complete DDL Map](https://docs.google.com/document/d/11Ll8SNDw1yYWDq-QhDcpx2NErfhU3lLrEyG_0GMNTeU/edit) | 기존 chain 위에 004 추가 |
| [Physical ERD](https://docs.google.com/document/d/1betNB4Kps9TaUpZc9avGdeKIPsJtxwApXzKlvtaDCgc/edit) | UUID·typed columns·RESTRICT FK |
| [Relational-First](https://docs.google.com/document/d/1Kavf5RnRrk-i3TFqGfHrBY5tgfqTw1qdL4z9GTUeBHc/edit) | JSON/JSONB/ARRAY 및 row blob 없음 |
| [Repository Architecture](https://docs.google.com/document/d/19YI_AEJxAiBnv6LSFP-uwNklluRWe1DHfnwtqIHSmDs/edit) | API → Application → Domain, UoW 계약 |
| [API/Pydantic](https://docs.google.com/document/d/1seqmSKIwjyWP5mKQYJt-RTG-e2XKbqAoIXxuGzUOWBw/edit) | typed resource, PUT mapping, explicit Confirm |
| [Error/Idempotency/Concurrency](https://docs.google.com/document/d/13t98aKXmUqESBXfHDgjgYn1sy2DGB2rOHEH6Cgp_p3g/edit) | expected_version·요청자 binding·안전한 오류 |
| [Excel/CSV Mapping](https://docs.google.com/document/d/1dHi_Wko-Wr6xty678EfMhTIXltfpqXMWS3MjqHmdkyE/edit) | 결정적 alias·validation·Preview/Confirm 분리 |
| [Intake Physical Schema](https://docs.google.com/document/d/1ahlOXEs70gdDcjqMTaCdy6kUEavYek-Lhm1TmA0TWZ8/edit) | sheet/column/mapping/error/receipt 관계형 모델 |
| [Evidence Provenance](https://docs.google.com/document/d/13zclSW1AQ0KXs64vKxcwVinO2cvLVO4JD0K3KoiUUbE/edit) | 불변 원본·hash·actor·parent evidence |
| [UI/UX](https://docs.google.com/document/d/16Zw882T8RQa7PvgmyU-fsz1Ksy8KhU2kmhKsmI1Q0iU/edit) | 항목 연결, 검증, 명시적 접수, 회사 전환 격리 |
| [Onboarding Adaptation](https://docs.google.com/document/d/1vXjyj63HfhUEmgQwWZPvK5_ZR9Bw89ONdKPBUNIDBRY/edit) | Onboarding Workspace·Draft merge는 후속 |
| [Permission Matrix](https://docs.google.com/document/d/1ErPSu4ouGwZKLzjSV_yYDTT5cWy-uyTMCPVJG4mYP4k/edit) | ACCOUNTANT/TAX_ACCOUNTANT의 Intake permission |

## 관계형 구조와 소유권

`004_storage_evidence_intake`는 003 뒤에 이어집니다. 다음 11개 테이블을 추가하며 전체 업무 테이블은 33개입니다.

| 테이블 | 책임 |
| --- | --- |
| storage_objects | 회사·서버 생성 키·filename·MIME·size·SHA-256·업로더·보존 상태 |
| evidences | FILE 등 명시적 유형, source/system/id, hash, 관찰·수집 시각, actor, parent |
| imports | 회사·requester·source/target·파일 참조·상태·version·mapping_version·Preview 유효기간 |
| import_sheets | logical CSV sheet 또는 Excel sheet의 순서·이름·크기 |
| import_columns | header·normalized header·위치·안전한 요약; 셀 값 없음 |
| import_mappings | 원본 열 하나의 정본 필드 연결과 확인 상태·확인자 |
| import_validation_errors | 행/열 위치·stable code·severity·안전한 안내; 원본 값 없음 |
| import_evidences | 현재 존재하는 Import와 Evidence의 명시적 SOURCE 관계 |
| import_receipts | Import당 한 Receipt, 정규화 source digest와 처리 수 |
| import_confirmations | 회사·actor·key 유일성, fingerprint와 Receipt FK |
| import_source_records | 회사·source type·target·system·source ID 유일성, 내용 hash와 Receipt FK |

모든 FK는 RESTRICT입니다. Storage/Evidence/Import의 회사·hash 일치는 복합 FK로 제약합니다.
Mapping은 Import/Sheet/Column 복합 FK와 원본 열 unique, sheet별 canonical field unique를 가집니다.
회사 FK index, count/version/hash/check, UUID·TIMESTAMPTZ, confidence NUMERIC(5,4)를 사용합니다.
금액은 정본 필드 검증에서 기존 Decimal/NUMERIC(19,4) 규칙을 적용하며 이번 migration에는 금액 행 자체를 저장하지 않습니다.

Global Governance의 idempotency_records를 선행 구현하지 않습니다. 현재 Confirm 전용 typed 참조 테이블이 replay를 담당합니다.
전체 API 응답, serialized rows, JSON/JSONB, generic payload/metadata/context/options 컬럼은 없습니다.
Transaction/Journal/Tax 정본 및 Counterparty 정본을 생성하거나 수정하지 않습니다. Receipt의 transaction_count와 counterparty_count는 항상 0입니다.

## Storage와 Evidence

`ObjectStorage` Protocol은 put/read/delete/exists를 제공합니다. `LocalObjectStorage`는 `STORAGE_ROOT` 아래
`<company UUID hex>/<새 UUID hex>`에 exclusive write합니다. 같은 filename이어도 충돌하지 않으며 원본 filename을 경로로 사용하지 않습니다.
키 형식·회사 prefix·resolve 결과를 확인합니다. 저장소 디렉터리는 애플리케이션 운영 계정만 쓸 수 있도록 배포해야 합니다.

기본 위치는 backend 실행 기준 `../.local/storage`이며 Git에서 제외됩니다. 생성자와 import는 디렉터리 생성이나 DB 연결을 수행하지 않습니다.
파일은 최대 크기까지 읽고 Preview/Confirm마다 SHA-256을 검증합니다. DB 저장 실패 시 새 파일을 보상 삭제합니다.
프로세스 강제 종료까지 파일시스템과 PostgreSQL을 원자적으로 묶지는 않습니다. 미참조 파일의 보존·정리 운영 작업은 후속 사항입니다.
사용자에게 원본 다운로드/삭제 API는 열지 않습니다. 향후 provider를 교체하더라도 동일 회사·불변 키·hash 계약을 유지해야 합니다.

Upload는 원본 FILE Evidence와 Import SOURCE link를 함께 생성합니다. source_type/source_system/source_id,
observed_at/ingested_at/created_by 및 storage_object_id/sha256으로 출처를 추적합니다.
같은 파일 재업로드는 동일 hash로 확인할 수 있고 각각의 수집 이벤트와 Evidence identity는 보존합니다.
`EvidenceService.derive`는 새 identity와 기존 parent 참조를 만들며 원본을 덮어쓰지 않습니다.
현재 API에 OCR 자동확정이나 파생 업무 Fact 생성은 없습니다. 향후 Transaction/Journal 등은 각 실제 FK target이 생길 때 전용 join을 추가합니다.

## 지원 파일과 제한

| 항목 | MVP 제한 |
| --- | --- |
| 형식 | UTF-8/UTF-8 BOM CSV, UTF-8 OOXML XLSX |
| 파일 | 2,000,000 bytes; multipart 전체 2,020,000 bytes |
| 데이터 | 파일 합계 1,000행, sheet당 40열, 최대 5 sheets |
| 셀 / header / filename | 4,000자 / 100자 / 200자 |
| ZIP | 100 entries, 합계 해제 크기 20,000,000 bytes |
| XML | 전체 XML의 `<` 표식 500,000개 이하; DTD/ENTITY·UTF-16 거부 |

빈 파일, 빈/중복 normalized header, 불일치 행 너비, 지원하지 않는 encoding/MIME/signature,
손상·암호화 ZIP, 경로 traversal, macro/VBA, external relationship, OLE/embedded object/ActiveX,
connection/query table/drawing/media, 수식을 거부합니다. 제한은 Drive에 구체적 숫자가 없는 부분에 선택한 보수적인 MVP 값입니다.

CSV의 공백 뒤 `=`, `+`, `@`, 숫자 전체가 아닌 `-` 시작 값도 거부합니다. 엄격한 음수 decimal 문자열은 허용합니다.
XLSX는 제한된 OOXML cell/shared string/inline string을 읽으며 수식 계산 엔진을 사용하지 않습니다.
숫자 문자열을 float로 바꾸지 않습니다. 날짜는 ISO date와 1900/1904 기준의 정수 date serial을 지원하며 가상의 1900-02-29와 시간 소수는 거부합니다.
MVP는 연속된 row 번호와 일반 worksheet를 지원합니다. 차트·이미지·수식이 있는 일반 보고서는 먼저 값만 포함한 입력 파일로 정리해야 합니다.

## 정본 필드·매핑·검증

코드 Registry `intake/domain/canonical_fields.py`가 alias, 필수 여부, type, API 필드 안내를 공유합니다.
지원 source: BANK_TRANSACTION, CARD_TRANSACTION, SALES, PURCHASE, EXPENSE, OPENING_BALANCE, COUNTERPARTY.
대부분의 입력은 source_id/transaction_date/amount/currency가 필수이며 OPENING_BALANCE는 account_code도 필요합니다.
COUNTERPARTY는 source_id/display_name/role_code가 필수입니다. COUNTERPARTY도 현재는 접수만 하며 Master를 생성하지 않습니다.
통화 MVP allowlist는 KRW/USD/EUR/JPY/CNY/GBP입니다. date, Decimal scale/range, 식별자와 명시적 enum을 검증합니다.

Header는 NFKC, casefold, 공백·underscore·hyphen 제거로 정규화합니다. 등록한 alias만 사용합니다.
EXACT/ALIAS_MATCH/AMBIGUOUS/UNMAPPED/USER_CONFIRMED를 구분하고 중복 후보는 자동으로 선택하지 않습니다.
Mapping PUT는 모든 원본 열의 명시적 연결/무시를 받고 중복 canonical field, 임의 code·열, stale version을 거부합니다.
필수 누락·모호함·중복 source ID·날짜/금액/enum 오류가 있으면 Confirm할 수 없습니다. 선택하지 않은 optional column은 가져오지 않습니다.

## Preview와 Confirm

Preview rows는 요청 처리 메모리에서만 생성하고 응답 후 보관하지 않습니다. 최대 5개의 대표 행을 반환하며 민감한 텍스트는 가립니다.
Redis 또는 DB에 행을 cache하지 않습니다. **Preview 유효기간은 900초**이며 digest/expiry/version만 관계형 DB에 기록합니다.
따라서 서버 재시작이나 다른 worker에서도 원본 파일과 확정 Mapping을 다시 읽어 검증할 수 있습니다.

digest는 SHA-256이며 definition `accounting-intake-1`, company, requester, file SHA-256, mapping_version,
정렬된 mapping(sheet/column/field/status), source_type, target_context, source_system을 포함합니다.
해시 입력의 결정적 직렬화는 메모리 안에서만 사용하며 DB document 저장이 아닙니다.
Mapping 변경은 digest/expiry를 무효화하고 aggregate version과 mapping_version을 증가시킵니다.

Confirm은 엄격한 `confirmed: true`, expected_version, preview_digest, Idempotency-Key가 필요합니다.
인증 세션·회원 상태·현재 membership·permission·requester를 재검증합니다.
파일 I/O는 DB 잠금 밖에서 수행하고, 최종 UoW에서 다시 회사·Import를 잠그고 현재 version/digest/expiry/state를 확인합니다.
최신 파일을 다시 해시·파싱·검증한 뒤 source conflict를 모두 검사하고 Receipt/claim/confirmation/Import 완료 상태를 하나의 transaction으로 기록합니다.
Repository는 commit하지 않습니다. 실패하면 Receipt·source claim도 함께 rollback됩니다.

동일 company+actor+key와 같은 fingerprint(import ID/digest/expected version/consent)는 저장한 Receipt를 다시 조회합니다.
같은 key에 다른 fingerprint는 IDEMPOTENCY_CONFLICT입니다. 성공한 replay는 Preview 만료 후에도 반환하되 현재 권한을 검사합니다.
서로 다른 Upload의 같은 source identity+동일 정규화 내용은 기존 claim을 재사용하며 파일 수집별 Receipt를 남깁니다.
다른 금액/날짜/핵심값이면 IMPORT_SOURCE_CONFLICT로 전체 Confirm을 거부하고 덮어쓰지 않습니다.
현재 Receipt는 파일 접수의 완료이고 향후 Transaction promotion 완료를 뜻하지 않습니다.

## API와 권한

기존 convention대로 backend에는 prefix가 없고 frontend의 `/api` proxy를 사용합니다.
모든 요청에는 Bearer와 `X-Company-ID`, 변경 요청에는 `X-CSRF-Protection: 1`이 필요합니다.

| API | 입력 / 의미 |
| --- | --- |
| POST /imports | multipart file, source_type, optional target_context/source_system |
| GET /imports/{id} | 내부 physical path를 제외한 typed 상태 |
| GET /imports/{id}/columns | 위치별 Mapping과 source별 canonical metadata |
| PUT /imports/{id}/mapping | expected_version, mappings[] |
| POST /imports/{id}/preview | expected_version |
| POST /imports/{id}/confirm | expected_version, preview_digest, confirmed=true + Idempotency-Key |
| GET /imports/{id}/errors | 안전한 validation 위치/코드 |
| GET /imports/{id}/receipt | 확정 Receipt |

import.create/preview/confirm/mapping.update 및 evidence.upload는 기존 Permission Matrix의 ACCOUNTANT/TAX_ACCOUNTANT 정책을 유지합니다.
OWNER라고 Intake 권한을 자동 추가하지 않습니다. Upload에는 evidence.upload도 필요합니다.
같은 회사의 다른 requester는 403, 다른 회사·접근 불가능한 resource는 404입니다.
Repository query 단계부터 회사 범위를 적용하고 child는 scoped Import의 명시적 FK로 조회합니다.
Application/Domain에는 ORM·FastAPI 의존이 없고 기존 Agent/LLM guard 및 repository transaction guard를 유지합니다.

Frontend는 회사별 key로 업로드·항목 연결·검증·대표 행·명시적 접수·Receipt를 제공합니다.
파일·source·mapping을 바꾸면 이전 Preview와 동의를 버립니다. 실패한 Confirm 재시도는 같은 idempotency key를 유지합니다.
Onboarding Wizard, 시작 방식 선택 카드, 샘플·Template 선택 화면은 만들지 않았습니다.

## 보안과 다음 계약

원본 bytes, 전체 행, token, credential, OCR text, 민감한 cell, SQL parameter는 로그나 오류에 복제하지 않습니다.
오류는 기존 공통 ErrorResponse를 따릅니다. 저장소 장애는 STORAGE_UNAVAILABLE, stale은 PREVIEW_STALE,
source conflict는 IMPORT_SOURCE_CONFLICT이며 원문 OS/DB 예외를 반환하지 않습니다.

후속 **005_onboarding_data_exchange**는 ONBOARDING_DRAFT target과 원본 Import/Evidence 참조,
공유 Registry·parser·mapping·digest 계약을 사용하여 typed Draft 병합·conflict choice·template metadata를 추가합니다.
현재 Confirm을 Domain write 권한으로 사용해서는 안 됩니다. 최종 Domain promotion은 별도 Application Command입니다.
그 다음 **006_transactions**가 imports FK와 정규화 row provenance를 연결합니다.
Journal/Opening Balance Posting·Tax·Agent·OCR 자동확정·전체 Governance·S3 provider·공식 Excel Template 생성은 이번 범위 밖입니다.
