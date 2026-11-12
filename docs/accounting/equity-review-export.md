# 자본변동표 독립 검토와 승인본 내보내기

기준 main `5d6110ea95cb5e844ba1c1ee34de70f2d03ba8db`, 로컬 설계 정본 `docs/AI_Accounting_Office_v0.2.6_통합설계_정본/`를 사용했다. 정본은 Git 제외 상태다. 결산 설계는 ADJUSTED/POST_CLOSING을 구분하지만 현재 hard-close Journal identity와 IS 표시 정책이 없으므로 #112의 `PROFIT_TRANSFER_IS_MISMATCH`를 유지한다. 차이를 보정하거나 과거 IS·POSTED Journal을 수정하지 않는다.

## 사용자 경로

`/financial-statements`에서 CLOSED 기간 → BS/IS·SCE 대사 → Snapshot 생성 → 구성요소·Journal/Evidence 근거 확인 → 검토 의견과 독립 검토 요청 → 생성자·요청자와 다른 OWNER/REVIEWER 승인 → `/reports`의 PDF/XLSX/CSV 생성·다운로드 순서다. 반려 후 재요청은 새 이력 version이며 승인 후 변경은 허용하지 않는다.

SCE `RECONCILED`는 계산 대사 상태다. `035_equity_review`의 `equity_review_events`가 별도의 append-only 검토 이력을 보존한다. 기존 Snapshot/Line/Source와 digest는 변경하지 않는다. Notes 승인이나 전체 재무제표 세트 승인과도 다르다. 결과는 `INTERNAL_VALIDATION_ONLY`이며 법정 승인·감사 완료를 뜻하지 않는다.

## API·권한·동시성

- `GET /equity/statements/{id}/review`: 조회 권한, 현재 검토 상태/version, source_stale, 처리 이력.
- `POST /equity/statements/{id}/review/{request-review|approve|reject}`: expected_version, reason, Idempotency-Key, CSRF 및 회사 권한 필요.
- 요청에는 financial_statement.generate, 승인·반려에는 financial_statement.approve를 적용한다. 생성자·요청자 자기 승인은 서버와 DB에서 차단한다.
- 기간 행 잠금과 기존 command 잠금으로 직렬화한다. 동일 key·동일 payload는 같은 이력을 반환하고 다른 payload는 충돌한다. 오래된 version은 VERSION_CONFLICT다.
- 회사 복합 FK, Snapshot/version unique, 사용자/key unique, DB trigger가 원천 digest·상태전이·승인 분리·UPDATE/DELETE 금지를 강제한다.
- 승인 전 현재 SCE 대사를 다시 수행한다. 원천이 바뀐 승인본은 과거 승인 상태와 이력을 보존하되 stale로 표시한다.

## Export와 호환성

미승인 새 Export는 `EQUITY_APPROVAL_REQUIRED`로 차단한다. migration이 과거 SCE를 자동 승인하지 않는다. 기존 완료 파일은 다운로드 권한·SHA-256 검증으로 계속 조회한다. 신규 Run은 현재 원천과 일치하는 승인본만 사용하며 승인 ID·처리자·시각을 파일 메타데이터에 담는다. 승인 후 같은 Snapshot에 새 검토 이력을 추가할 수 없어 기존 Run의 Snapshot digest는 유일한 최종 승인 이력에 연결된다. 새 보고서 엔진이나 범용 승인 엔진은 만들지 않았다.

## 실제 검증

Migration lifecycle·SCE·Notes·Report Center PostgreSQL 8건 통과. 이후 반려/재요청·자가 승인 차단·독립 연결 경쟁·stale 이력을 추가한 SCE subset 4건 통과(117.04초). 경쟁은 같은 expected version의 승인 성공 1건/충돌 1건을 확인한다. 기존 Decimal 금액, 배당 부분/후속 지급, Journal 불변성, Notes, PDF/XLSX/CSV 및 SHA-256 assertion을 유지했다. 테스트 중 SCE 승인 변수를 Notes 승인 결과로 덮어쓴 오류는 변수 분리로 수정했으며 assertion은 유지했다.

Frontend 61건과 lint/typecheck, 변경 Python Ruff/format/mypy 통과. UI 검증은 상태/권한 모델 및 요청 격리이며 전체 브라우저 E2E는 미실행이다. 전체 Golden·전체 PostgreSQL regression·실제 고객 Pilot·운영 Release Gate는 미실행이다.

#112는 hard-close 원천/표시 계약이 남아 종료하지 않는다. Asset/Inventory/Tax와 전체 제표 세트 최종 승인은 이번 범위가 아니다.
