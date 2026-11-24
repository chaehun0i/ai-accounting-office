# 재무제표 전체 세트 구성과 독립 승인

구현 기준 main은 `df43289abf29dc922af26853838a6e1416a9a094`다. 로컬 `docs/AI_Accounting_Office_v0.2.6_통합설계_정본/`의 읽기안내, 재무제표 완전세트의 세트 identity·승인·Snapshot·Export 계약과 Closing의 ADJUSTED/POST_CLOSING 구분을 대조했다. 설계 복사 폴더는 Git 제외 대상이다. 관련 Issue는 #131, 상위 로드맵은 #83이다.

## 업무 경로

`/financial-statements`에서 CLOSED 기간을 선택한다. 현재 BS/IS·CF·SCE와 승인 Notes를 준비하고 SCE 개별 승인을 완료한다. 전체 세트 작업 영역에서 원천을 다시 확인하고 현재 revision으로 세트를 고정한다. 생성자·검토 요청자와 다른 OWNER/REVIEWER가 의견을 남겨 승인하거나 반려한다. 반려 후 재요청은 새 이력 version이다. Report Center의 `FINANCIAL_STATEMENT_SET`에서 PDF/XLSX/CSV를 생성하고 이력·다운로드를 조회한다.

BS/IS의 기존 `GENERATED`는 바꾸지 않는다. CF의 `RECONCILED`, SCE/Notes 개별 승인, 전체 세트 승인은 서로 다른 계약이다. 전체 세트 승인은 다섯 원천의 고정된 조합에 대한 내부 검토 승인이다. `INTERNAL_VALIDATION_ONLY`이며 법정 제출·외부감사 완료를 뜻하지 않는다.

## 원천 및 관계형 저장

기존 `financial_statement_sets`는 BS/IS 생성 원천을 나타내므로 덮어쓰지 않는다. `037_statement_set_approval`의 `statement_set_revisions`가 그 세트, 회사·기간, BS/IS/CF/SCE/Notes ID를 회사 복합 FK로 연결한다. Notes의 기존 결정론적 원천 검증·GL/본문 금액 대사·BS equation·IS/CF 순이익·BS/SCE 기말 대사를 재사용한다. 현재 승인 Notes의 revision/version 및 원천·대사 digest를 조합해 전체 세트 digest를 고정한다. 누락이나 충돌은 READY가 되지 않는다.

Snapshot 금액은 복사하거나 다시 계산하지 않는다. 참조된 원본 ID는 원본의 불변 line과 provenance를 가리킨다. BS/IS의 mapping/taxonomy/close version은 기존 원본 세트에서 보존한다. 전체 세트는 UPDATE/DELETE 금지 trigger로 보호되며 새 원천은 새 revision을 구성한다. DB의 멤버 검사 trigger는 다른 기간·종류·원본 세트의 혼합과 미승인 Notes 연결을 차단한다. 업무 JSON/JSONB는 추가하지 않는다.

## API·승인·동시성

- `GET /financial-statement-sets/readiness?period_id=...`: READY/BLOCKED, 원천 ID와 digest, 결정론적 차단 원인.
- `POST /financial-statement-sets/generate`: period_id와 Idempotency-Key로 원천 조합 고정.
- `GET /financial-statement-sets?period_id=...`, `GET /financial-statement-sets/{id}`: 불변 원천 연결과 현재 source_stale 조회.
- `GET /financial-statement-sets/{id}/review`: 검토 상태/version과 append-only 이력.
- `POST /financial-statement-sets/{id}/review/{request-review|approve|reject}`: expected_version, reason, Idempotency-Key, CSRF.

조회는 `financial_statement.read`, 생성·요청은 `financial_statement.generate`, 승인·반려는 `financial_statement.approve`를 요구한다. 생성자·요청자 자기 승인을 서버와 DB에서 차단한다. 상태는 기존 검토 계약의 NOT_REQUESTED → REVIEW_REQUESTED → APPROVED/REJECTED이며 반려 후 재요청을 지원한다. 세트 승인 이력은 별도 `statement_set_review_events`에 보존하며 원본 개별 승인 이력을 바꾸지 않는다.

기간 잠금과 기존 command 잠금을 사용한다. 회사/기간/digest unique로 같은 원천의 중복 revision을 막고 `statement_set_commands`에 사용자/key/fingerprint/결과를 남긴다. 같은 key·같은 요청은 같은 결과, 다른 요청은 충돌한다. 검토 이력 version unique와 expected_version으로 동시 승인 중 하나만 성공한다. 승인 시 같은 UoW에서 원천을 다시 검증하고 stale이면 REPORT_SOURCE_STALE로 차단한다. 오래된 version은 VERSION_CONFLICT다.

## Report Center와 호환성

기존 Run/Artifact/Storage/History/Download와 SHA-256 검증을 사용한다. 신규 Run은 현재 승인된 전체 세트 digest를 고정한다. 렌더링에서도 그 digest의 세트를 다시 찾아 승인·현재성을 확인하고 고정된 다섯 member ID에서만 읽는다. 원천이 바뀌어도 기존 완료 파일은 보존하고 권한 있는 사용자가 다운로드할 수 있다. 새 Export는 차단한다.

파일은 회사·보고기간·생성시각·세트 revision ID·close/taxonomy version·원천 digest·승인 ID/검토자/시각 및 내부 검증 상태를 표시한다. 고정 세트 내용 조회와 Export는 같은 읽기 함수를 사용하며, 과거 승인본도 고정된 금액·주석 본문을 조회할 수 있다. 기존 개별 보고서 카탈로그는 유지한다. 화면은 회사·기간·revision별 상태를 격리하며 기존 독립 검토 UI를 재사용한다.

## 검증과 제한

기존 실제 CLOSED SCE/Notes 통합 fixture를 재사용한다. 다섯 제표 수집, 미승인 원천 차단, 세트 멱등 생성, 반려·재요청·독립 승인, 회사 격리, 동시 생성·승인, DB 멤버 검사/불변성/자기 승인 차단, 원본 BS/IS GENERATED 유지, 세 형식 Export·다운로드 digest와 stale 이후 과거 파일 보존을 검증한다. migration lifecycle은 빈 DB/기존 head upgrade·downgrade·metadata/FK·업무 JSON 부재를 검사한다. 실제 명령과 최종 4건 통과(109.09초)이며 같은 금액·본문 읽기와 경쟁 경로를 확인했다.

물리적 손익마감·ADJUSTED/POST_CLOSING·PROFIT_TRANSFER_IS_MISMATCH의 미지원 계약은 #112에 남는다. 해당 차단을 전체 세트 승인으로 우회하지 않는다. CF/SCE/Notes 비교·restatement·자산·재고·세무 확장·실고객 Pilot·운영 복구·최종 Release Gate는 이번 범위가 아니다. 전체 회귀/Golden/브라우저 E2E는 실행하지 않는다.

### 실제 실행 결과

- PostgreSQL 초기 세트 통합 4건 통과. API 생성 요청의 새 report code 누락을 발견해 보완했다.
- 최종 migration/SCE/독립 연결/Notes/Report Center subset은 8건 통과·카탈로그 기대 목록 1건 실패였다. 새 카탈로그 항목을 기대 목록에 명시 추가하고 Report Center 3건 재실행 통과. 금액·권한·불변성 assertion은 유지했다.
- 고정된 내용 조회와 Export의 공통 읽기 경계 추가 후 SCE 정상·차단·독립 연결 subset을 재검증했다. 최종 4건 통과(109.09초)이며 같은 금액·본문 읽기와 경쟁 경로를 확인했다.
- frontend 64건, lint/typecheck, 변경 Python Ruff/format/mypy 통과. 외부 LLM 호출 없이 합성 회계 원천을 사용했으며 실고객 검증으로 표현하지 않는다.
