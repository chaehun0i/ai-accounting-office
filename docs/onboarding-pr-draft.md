# PR 초안

제목: **feat: 회계 온보딩 워크스페이스와 데이터 병합 기반 구축**

## 목적과 결과

PR #5의 Storage/Evidence/Intake 위에 직접입력 중심의 회계 시작 준비 화면을 추가합니다.
수동 저장과 복구, 공식 Excel → 병합 Preview → 명시적 충돌 선택 → Draft Apply → 수동 수정 → 검증/재계산 → 지원 Domain 승격을 연결합니다.
Excel 업로드는 현재 초안을 채우는 보조 입력이며 Preview/Apply는 회계 정본을 생성하지 않습니다.

## 기준선과 구조

- 시작 main `85e23b1bd2e94c7d4d22bd5447222964bf5f863c`.
- AI_Accounting_Office_v0.2.5_통합설계_정본, 활성 문서 직접 확인, fallback 없음.
- `005_onboarding_data_exchange`: 관계형 초안/field/row/value/history/validation/import/apply/promotion receipt 10개 table.
- 단일 Field Catalog 68개, typed values, Decimal/NUMERIC, conditional required와 서버 진행률.
- 기존 parser/storage/evidence/mapping/digest/UoW composition. 파서 복제·ServIQ 재이식 없음.
- 안정적인 business key, KEEP_CURRENT/APPLY_IMPORT, expected_version/row lock/900초 digest expiry.
- 회사·요청자·RBAC 검증, typed idempotency receipt, Repository 독립 commit 없음.
- Company/Accounting/Master Data Application Command를 하나의 UoW에서 승격. 실패 시 전체 rollback.

## 데이터와 보안

업무 43개 table에서 JSON 0, JSONB 0, 전체 77 FK의 orphan row 0을 실제 PostgreSQL에서 확인했습니다.
금지 generic blob, 원본 file bytes, raw credential/card/account storage를 추가하지 않았습니다.
기존 malicious spreadsheet guard, stale Apply, IDOR, revoked membership, 요청자 격리를 유지했습니다.
공식 native Sheet의 macro-free export를 immutable v1 snapshot으로 보관하고 별도 derived v1의 425 typed cell을 회귀 비교했습니다.
`.xlsm`은 공식 fixture가 아니며 거부 테스트 대상입니다. 세무 sample fact를 신고 정답으로 사용하지 않습니다.

## Reference와 충돌 해결

WITH ESG pinned commit `720e33c7923a679c2cff694ca12c9f92646ed06b`:
OnBoard.jsx ADAPT, onboardingUtils.js ADAPT, backend onboarding.py PATTERN,
onboardinginputrepository.py ADAPT/PATTERN. COPY 없음.
회사 context/입력 모드/진행률/typed persistence/파생 무효화 개념만 신규 구조로 재작성했습니다.
React Router/Redux, ESG metric/rollup/DMA, MariaDB/int PK/repository commit/float는 DROP했습니다.
실제 source → 신규 file mapping과 충돌 해결은 [구조 문서](onboarding-data-exchange.md)에 있습니다.

## 검증

최종 backend 240 pass/skip 0, Ruff·format·mypy·pip check 통과.
Alembic clean upgrade, base 왕복, 004↔005 왕복, head/metadata check 통과.
Frontend 6 test와 lint/typecheck/production build 통과, 같은 lockfile의 offline npm ci 완료.
실제 브라우저 smoke 및 PostgreSQL/Redis healthy 확인.
기존 TestClient의 deprecation warning 1건은 [검증 기록](onboarding-verification.md)에 명시했습니다.
원격 Actions 결과를 로컬 결과로 대체 주장하지 않습니다.

## 제외·알려진 제한

Transaction/Journal/Posting/GL/TB, Asset/Inventory/AR/AP 전체, Tax/Agent/LLM은 구현하지 않았습니다.
미지원 데이터는 Draft에 보존하며 PENDING_DOMAIN_SUPPORT로 Complete를 차단합니다.
Opening Balance balance UPDATE나 즉시 POSTED 생성은 없습니다.
자유 매핑 Draft 연결은 현재 COUNTERPARTY만 지원합니다. 기존 지급조건 참조만 지원하며 지급조건 생성은 별도 Master 명령입니다.
전체 2025 샘플의 미지원 Domain 및 차감 계정은 후속 capability/회계정책 검토가 필요합니다.
파일 업로드 이후 초안 연결 실패로 남은 원본 Import의 운영 정리 정책은 후속 사항입니다.

Commit 목록은 종료 보고의 실제 순서 목록을 붙입니다. 이 파일은 초안이며 PR을 생성하거나 merge하지 않았습니다.

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
