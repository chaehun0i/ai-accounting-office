# 파일·증빙·인테이크 검증 기록

검증일: 2026-10-10. 기준 main: `f56ac91b078c11aa7e14c324446fb365aaef2811`.
브랜치: `feat/storage-evidence-intake`. 설계 기준: v0.2.5 단일 정본, fallback 미사용.
환경: Windows PowerShell, Python 3.14.2, Node 24.12.0/npm 11.6.2, PostgreSQL 17, Redis 7.
최종 전용 DB는 `accounting_intake_final_test`이며 개발·운영 DB를 migration 테스트에 사용하지 않았습니다.

## 실제 실행 결과

| 명령 / 검사 | 결과 |
| --- | --- |
| `python -m pytest --require-postgres -q --tb=short` | **214 passed**, skip 0, warning 1 |
| PostgreSQL 설정 없는 `python -m pytest -q --tb=short` | **133 passed, 81 skipped**, warning 1 |
| `python -m ruff check .` | 통과 |
| `python -m ruff format --check .` | **218 files already formatted** |
| `python -m mypy app` | **174 source files**, 오류 없음 |
| `python -m pip check` | No broken requirements found |
| `python -m alembic current` | 004_storage_evidence_intake (head) |
| `python -m alembic upgrade head` | 통과, 현재 head 재실행 가능 |
| `python -m alembic current --check-heads` | 통과 |
| `python -m alembic check` | No new upgrade operations detected |
| 비어 있음을 확인한 테스트 DB에서 `alembic downgrade base` → `upgrade head` → `check` | 통과 |
| 자동 lifecycle: clean DB→head, 003→004→003→004 및 base round-trip | 통과 |
| PostgreSQL public 업무 테이블 | **33개**, 별도 alembic_version |
| public JSON / JSONB | **각 0개** |
| 신규 11개 테이블의 FK target·RESTRICT·회사 index·실제 orphan 검사 | 통과, **orphan 0** |
| public 미검증 FK | **0개** |
| `npm ci --no-audit --no-fund` | lock 기준 설치 성공 |
| `npm run lint` | 통과, warning 0 |
| `npm run typecheck` | 통과 |
| `npm test` | **3 passed** |
| `npm run build` | production build 통과 |
| `docker compose --env-file .env -f infra/docker-compose.yml config --quiet` | 통과 |
| 같은 Compose `up -d --wait` / `ps` | PostgreSQL·Redis 모두 **healthy** |
| 임시 Uvicorn 실제 HTTP `GET /health` | **200**, `{"status":"ok"}` |
| 실제 HTTP `/openapi.json` | 생성 성공, multipart file/source_type 및 Confirm 명령 확인 |
| `git diff --check` | 통과 |

warning 1은 기존 Starlette TestClient/httpx 사용에 대한 deprecation입니다. 테스트 실패가 아니며 이번 범위에서 HTTP client stack을 교체하지 않았습니다.
처음 추가한 테스트에서 Principal 필수 email과 테스트 보안 이벤트 정리 누락을 발견해 수정했습니다.
새 전용 DB에서 전체 테스트와 migration lifecycle을 재실행해 최종 통과했습니다.

## 자동 검증 범위

새 관련 테스트는 63개입니다. 기존 151개를 유지해 총 214개입니다.

- Storage put/read/exists/delete, UUID key, 동일 filename 충돌 방지, 회사 prefix 및 traversal, missing object.
- UTF-8/BOM CSV와 XLSX, 숫자 문자열 정밀도, 1900/1904 날짜 기준.
- 빈/큰/잘못된 MIME·확장자·ZIP, duplicate/empty header, formula injection, row/column/cell/ZIP/XML 한도.
- macro/VBA, external link/relationship, embedded OLE/ActiveX, DTD/ENTITY와 UTF-16 우회 거부.
- 명시적 alias와 ambiguity, required/enum/date/Decimal, 사용자 수정 Mapping, optional 열 무시.
- Preview가 Receipt/업무 정본을 생성하지 않음, stale mapping/version/expiry와 파일 hash 변조 거부.
- CSV/XLSX 실제 API Upload→Mapping→Validation→Preview→Confirm→Receipt.
- 같은 key replay, 다른 fingerprint conflict, 같은 source/동일 내용 재사용, 다른 금액 conflict 및 overwrite 없음.
- 실제 독립 PostgreSQL connection의 동시 Confirm: 한 Receipt, 동일 결과.
- Storage 실패 시 DB row 0, DB 실패 시 미참조 파일 보상 제거, Confirm 중간 실패 시 Receipt/claim/confirmation rollback.
- Evidence hash/storage 일치, parent 파생과 원본 불변, 회사 격리, 다른 requester, VIEWER, revoked membership.
- FK/index/check/unique 및 schema guard, Domain/Application/Agent/LLM/Repository transaction architecture guard.

runtime 신규 Storage/Evidence/Intake에서 legacy 식별자, get_by_id, repository commit, LargeBinary/JSONB/ARRAY 저장 타입 검색 결과는 0건입니다.
JSON은 메모리 안의 digest 직렬화와 API 표현에만 사용합니다. 정책·source migration을 설명하는 문서의 프로젝트 이름은 의도적인 참조입니다.
실제 `.env`와 원본 파일 디렉터리는 ignored이며 커밋하지 않았습니다. raw password/token/credential·원본 rows/bytes를 새 로그에 출력하지 않습니다.

## CI와 재현

기존 PostgreSQL CI job은 head migration, metadata check, `tests/integration --require-postgres`를 수행합니다.
이번 브랜치를 push trigger에 추가하고 dependency consistency 검사도 추가했습니다. 신규 테스트는 이 기존 gate에 자동 포함됩니다.
로컬 성공 결과이며 원격 Actions 실행 결과를 대신하지 않습니다. 이번 요청에서는 PR를 생성하거나 main에 merge하지 않았습니다.

통합 테스트에는 비어 있는 `_test` DB와 `TEST_POSTGRES_URL`이 필요합니다. 개발 `.env` credential을 출력하지 말고 환경에 맞는 URL을 사용하세요.
테스트는 알려진 테이블이라도 데이터가 있으면 migration 초기화를 중단합니다. 별도 seed를 영구 적용하지 말고 fixture의 transaction seed를 사용하세요.

초기 실패 검사의 전용 DB(`accounting_intake_test`, `accounting_intake_clean_test`)는 그대로 두었습니다.
권한 seed 전체 삭제는 자동 승인 검토가 공유 테스트 데이터 손실 위험으로 거부하여 실행하지 않았습니다.
최종 검증은 새 격리 DB에서 수행했으며 해당 DB는 전체 테스트 종료 후 모든 업무 테이블이 비어 있음을 확인했습니다.
임시 HTTP 서버는 검사 후 종료했습니다. PostgreSQL/Redis의 기존 named volume과 실행 상태는 유지했습니다.

## 알려진 제한과 후속 계약

로컬 파일 provider만 구현했습니다. 운영 S3, 용량 quota, 보존 작업, crash 후 orphan object 정리는 후속 운영 범위입니다.
Parser는 입력용 단순 workbook만 지원하며 CSV는 UTF-8, 날짜는 ISO date/정수 Excel date, 통화는 명시한 6개 코드로 제한합니다.
Preview 행 cache는 없고 Confirm 시 파일을 다시 파싱합니다. 유효기간은 900초입니다.
같은 source의 같은 내용은 claim을 재사용하되 새 업로드의 provenance/Receipt는 각각 보존합니다.
Receipt는 접수 완료이며 Accounting/Tax/Counterparty 정본 반영은 없습니다.
다음 005 Onboarding/Data Exchange는 typed Draft merge·template metadata·충돌 선택·별도 Domain promotion을 연결해야 합니다.
