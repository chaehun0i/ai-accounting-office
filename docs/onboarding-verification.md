# 온보딩 검증 기록

시작 main은 `85e23b1bd2e94c7d4d22bd5447222964bf5f863c`이며 최종 확인 시에도 원격 main은 같았습니다.
작업은 `feat/onboarding-data-exchange`에서만 수행했습니다. main 수정·push·PR 생성·merge는 하지 않았습니다.
단일 설계 기준선은 v0.2.5 정본이며 fallback은 없습니다.

## 실행 결과

| 실제 명령 | 결과 |
| --- | --- |
| python -m pytest --require-postgres -q --tb=short | 239 pass, skip 0, warning 1. 마지막 회사 전환 테스트 추가 전 전체 실행 |
| python -m pytest -q --tb=short | 최종 240 pass, skip 0, warning 1. TEST_POSTGRES_URL 설정 상태로 모든 PostgreSQL 테스트 포함 |
| 온보딩·Golden 통합 재검증 --require-postgres | 최종 안내 문구 변경 후 12 pass, skip 0, 기존 warning 1 |
| python -m ruff check . | 통과 |
| python -m ruff format --check . | 251 파일 통과 |
| python -m mypy app | 200 source 파일 통과 |
| python -m pip check | broken requirement 없음 |
| python -m alembic current | 005_onboarding_data_exchange |
| python -m alembic upgrade head | 성공, 재실행 성공 |
| python -m alembic current --check-heads | head 일치 |
| python -m alembic check | 신규 upgrade operation 없음 |
| migration integration lifecycle | clean base → head, head → base → head, 004 ↔ 005 왕복 성공, metadata diff 없음 |
| npm ci --offline --no-audit --no-fund | 동일 package-lock의 캐시 재설치 성공, 123 package |
| npm run lint | 통과, warning 0 |
| npm run typecheck | Next route type 생성 및 TypeScript 통과 |
| npm test | 최종 6 pass, fail/skip 0 |
| npm run build | production build 성공, 정적 페이지 생성 성공 |
| docker compose --env-file .env -f infra/docker-compose.yml config --quiet | 통과 |
| docker compose --env-file .env -f infra/docker-compose.yml up -d --wait | 성공 |
| docker compose --env-file .env -f infra/docker-compose.yml ps | PostgreSQL 17 / Redis 7 모두 healthy |

일반 `npm ci`는 오래 지속되는 설치를 중단한 뒤 동일 lockfile의 오프라인 캐시 설치로 재시도했습니다.
네트워크나 audit 결과를 성공으로 추정하지 않았습니다. 위 offline 명령이 실제 완료한 재설치입니다.
유일한 backend warning은 기존 FastAPI TestClient/Starlette의 httpx → httpx2 전환 deprecation입니다.
업무 검증 실패나 skip은 없습니다. 해당 의존성 전환은 별도 호환성 검토 대상입니다.

## 실제 PostgreSQL 스키마

전용 `accounting_onboarding_final_test`를 사용했습니다. 이름이 `_test`로 끝나지 않으면 테스트가 중단됩니다.
개발·운영 DB를 lifecycle 테스트에 재사용하지 않았습니다.

| 검사 | 결과 |
| --- | --- |
| 전체 업무 table | 43 |
| 신규 onboarding table | 10 |
| public JSON column | 0 |
| public JSONB column | 0 |
| 금지 JSON domain/ARRAY guard | 위반 0 |
| 전체 77 FK의 실제 orphan row | 0 |
| 신규 table index | 40 |
| 신규 table CHECK | 9 |
| 신규 table UNIQUE constraint | 13 |

FK/index/check/unique 검사와 신규 table의 회사 scope, generic payload/metadata/context/extra/options 부재 검사를 자동화했습니다.
NUMERIC(19,4), UUID, timezone-aware timestamp 및 기존 identity/master persistence 회귀가 통과했습니다.

## 검증된 기능 경계

- 직접입력 저장·서버 복구·stale expected_version·추가 필드/float 거부.
- 공식 XLSX Template round trip, version 거부, 기존 parser profile 제한 유지.
- KEEP_CURRENT와 APPLY_IMPORT, 동일 Apply replay, 다른 요청 지문 conflict, 변경 후 stale Apply 거부.
- Excel 이후 MANUAL 전환과 이전 EXCEL_IMPORT 관계형 이력 보존.
- 원천 금액 변경 → 파생 STALE → Decimal 재계산, 미지원 Domain의 완료 차단.
- 정상 완료·동일 receipt 재시도·회사 변경 이후 강제 중간 실패의 전체 rollback.
- VIEWER write 거부, revoked membership 거부, 실제 Company A/B 전환 IDOR 차단.
- 같은 회사의 권한 있는 다른 사용자에게도 업로드 요청자 전용 resource 조회 거부.
- 기존 거래처 자유 매핑 Import 연결, 일반 confirm 우회 거부, Apply 후 원본 Import 변경 금지.
- `.xlsm`, 매크로/VBA, 외부 링크, embedded object, formula, ZIP bomb, traversal 등 기존 파일 보안 회귀 통과.
- Agent/LLM, Domain/Application의 DB/framework 직접 의존 금지 architecture guard 유지.
- 신규 runtime의 legacy 식별자, get_by_id, repository session.commit, float 금액 정적 검색 결과 0건.

## Golden과 실제 브라우저

native Sheet export 원본 SHA-256을 검증하고 별도 파생 v1의 425 typed cell을 비교했습니다.
Company/19 COA/20 Counterparty/8 Opening Balance 및 future Draft를 비교하며 원본과 세무 sample fact를 수정하거나 신고 정답으로 간주하지 않았습니다.
Golden integration 1건이 전체 240개 실행에 포함되어 통과했습니다.

`scripts/onboarding-browser-smoke.cjs`는 별도 `accounting_onboarding_browser_test`와 Edge headless/Playwright를 사용합니다.
로그인·회사 선택·수동 저장/새로고침 복구·상단 Excel 버튼 하나·공식 XLSX 업로드·충돌 해결·Apply·수동 수정·검증·미지원 승격 차단을 실제 API/DB와 연결하여 검증합니다.
브라우저 검증에서 발견한 중복 React key와 Uvicorn access formatter 인자 손상을 수정하고 회귀를 추가했습니다.
현재의 미지원 승격 차단은 의도한 capability 정책이며 샘플 전체를 억지로 완료시키지 않았습니다.

## CI와 후속 사항

이 브랜치 push/PR 시 기존 backend unit/contract/architecture, PostgreSQL migration/integration/golden/schema,
frontend unit/lint/type/build gate가 실행되도록 연결했습니다. 이 작업에서는 push하지 않았으므로 원격 Actions 실행 결과를 주장하지 않습니다.
브라우저 smoke는 전용 테스트 환경에서 별도로 실행합니다.

현존 제한은 [구조 문서](onboarding-data-exchange.md#알려진-제한과-후속-계약)에 기록했습니다.
전체 commit의 실제 SHA와 최종 branch HEAD는 작업 종료 보고의 commit 목록을 기준으로 합니다.

## 문서 정리 직전 커밋

```text
bfd25f0 feat: 회계 온보딩 필드 카탈로그와 필수 병합 규칙 구현
2fb0fe6 feat: 온보딩 초안과 접수증 관계형 마이그레이션 구성
453d3be feat: 공식 온보딩 Excel 양식과 기존 안전 파서 연결
0467bc1 feat: 온보딩 직접 입력 저장과 출처 이력 진행률 구성
7bd22c4 feat: Excel 초안 병합과 충돌 선택 멱등 적용 구현
2688c38 feat: 온보딩 완료와 기존 정본 명령의 원자적 승격 구현
be68554 feat: 온보딩 API와 회사 권한 및 공통 업로드 수신 연결
7082f17 feat: 직접 입력 중심 온보딩 화면과 Excel 병합 검토 연결
951e652 feat: 자유 매핑 입력과 온보딩 확정 보안 경계 보강
231ec7a fix: 인증 경로 마스킹 시 서버 접근 로그 형식 보존
76ed042 test: 온보딩 입력 충돌과 원자적 승격 회귀 검증 추가
3b0b9d7 test: 공식 샘플회사 Excel 초안 병합 회귀 추가
3f61e38 test: 온보딩 마이그레이션 왕복과 관계형 정책 검증 강화
5d095f2 fix: 온보딩 조건부 입력과 회사별 화면 상태 안정화
15e7c84 ci: 온보딩 관계형 스키마와 병합 회귀 검증 연결
e906c67 test: 실제 브라우저 온보딩 입력과 Excel 병합 흐름 검증 추가
55e5a7a fix: 온보딩 사용자 안내를 쉬운 회계 표현으로 정리
```

마지막 문서 커밋은 `docs: 온보딩 데이터 병합 구조와 검증 결과 문서화`이며 최종 SHA는 종료 보고에서 제공합니다.
