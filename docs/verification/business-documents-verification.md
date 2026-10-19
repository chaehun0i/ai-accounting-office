# 업무문서 검증 기록

검증일: 2026-10-12 KST. 시작 main: `c4f983fa9ba04a49037f676512c2f6f74e111324`(PR #12). 브랜치: `feat/business-documents`. 구현 계약은 [업무문서 설계](../accounting/business-documents.md)를 참고합니다.

## 실행 결과

| 검사 | 실제 결과 |
| --- | --- |
| 전체 PostgreSQL 회귀 `pytest --require-postgres` | **429 passed, 1 skipped**, 3 warnings, 1318.06초. 한 번의 전체 실행이며 개별 실행 횟수를 합산하지 않음 |
| 업무문서 집중 PostgreSQL 실행 | 별도 **37 passed**, 409.42초 |
| Ruff check / format | 통과 / 458개 파일 형식 통과 |
| mypy / pip check | 356개 소스 오류 없음 / 의존성 충돌 없음 |
| Linux frontend clean install | `npm ci --offline --no-audit --no-fund` 통과 |
| frontend lint/typecheck/test/build | 통과, 32개 테스트. 최종 화면 변경도 Linux에서 재검증 |
| 실제 Edge 브라우저 | 로그인, 매출 작성, 승인 요청, 별도 사용자 승인, Transaction 조회, Credit Note, 잔액 8,800,000원, 새로고침, 회사 전환 격리 통과 |
| Migration | 빈 DB base→head, 012→013, 013→012→013, 전체 downgrade/re-upgrade 통과 |
| Alembic metadata | 새 upgrade operation 없음 |
| DB 실측 | 업무 테이블 80, FK 215, orphan 0, 업무 JSON 0, JSONB 0 |

전체 실행에는 기존 Identity/Company/COA/Dimension/Intake/Promotion/Accounting/Finance/Agent 회귀가 포함됩니다. 새 테스트는 독립 PostgreSQL 연결의 동시 승인, 원천·문서번호 충돌, 동시 정정 한도, 자기승인 차단, 비활성 거래처, 권한·회사 경계, stale version, 멱등성, rollback 및 DB 확정 문서 불변성을 검증합니다. 실제 브라우저는 매출/Credit Note 경로이며 매입/Debit Note는 PostgreSQL/API 검증입니다.

## Golden 및 연간 source

기존 직접 거래 Golden 진입점과 새 업무문서 Golden 진입점을 분리했습니다. 기존 expected를 수정하지 않았습니다. 두 경로에서 AR 5,500,000원, AP 1,650,000원, TB 차변/대변 각각 62,650,000원을 검증합니다. 문서 승인 뒤 기존 Journal 사람 승인·Posting 경로로 연결하며 Invoice가 자동 Posting하지 않습니다.

- SYN_SERVICE_001: 매출 2건 8,800,000원, 매입 1건 1,100,000원.
- SYN_MFG_001: 매출 240건 781,044,000원, 매입 74건 195,277,500원.
- 각 문서의 exact source facts, Transaction·AR/AP 원천 유일성, provenance, 재시도 중복 0을 검증했습니다.
- 집중 실행의 제조 314건 작성·제출·승인 측정: 113.507초, command p95 0.233초. 서비스 3건 1.793초, p95 0.208초. 로컬 Docker 수치이며 운영 성능 보장은 아닙니다.

원본 native Sheet 및 기존 snapshot은 수정하지 않았습니다. 새 서비스 CSV adapter v1은 원본 값을 정규화합니다. 제조 adapter는 반올림된 상세 단가를 재계산하지 않고 기존 헤더 금액을 집계 항목으로 전달합니다. VAT는 source fact이며 세법 검증 결과가 아닙니다.

## Drive 확인과 동기화

최신 유효 SSOT: `AI_Accounting_Office_v0.2.6_통합설계_정본`, fallback 없음. 문서지도/로드맵/전체업무흐름/재무운영/DDL/Migration/API/State/Error/RBAC/Repository/Relational-First/Coverage/DoD/Golden/샘플 가이드를 직접 확인했습니다.

문서지도, 로드맵, Coverage의 오래된 PR #11 구현 기준을 실제 merged PR #12/main으로 제한적으로 갱신하고 readback했습니다. 이번 PR이 merge되기 전에 Business Document를 main 구현 완료라고 표시하지 않았습니다.

실제 샘플 폴더는 native Sheet `AI_Accounting_Office_SYN_SERVICE_001`, `AI_Accounting_Office_SYN_RETAIL_001`, `AI_Accounting_Office_SAMPLE_COMPANY_2025`, legacy `AI_Accounting_Office_SAMPLE_COMPANY_2025_v1.xlsm`, 가이드 문서입니다. MIME으로 native Sheet 3개와 macro-enabled workbook을 구별했습니다. 공식 regression source는 native Sheet 3개이며 .xlsm은 공식 fixture가 아닙니다. legacy 파일 정리는 후속 문서 운영 항목으로 남기고 삭제하지 않았습니다.

## 한계와 후속 계약

KRW만 지원합니다. 활성 외상매출금/외상매입금 계정 하나를 사용하며 사용자 정의 control account 역할 매핑은 후속입니다. 완납 후 환불/반대채권은 구현하지 않았고 Credit Note는 현재 outstanding 이내로 제한합니다. 문서 승인으로 생긴 보조부와 아직 Posting되지 않은 GL 사이 MISMATCH는 숨기거나 자동 보정하지 않습니다. 문서 목록은 배치 조회하지만 기존 AR/AP 일부 조회에는 항목별 조회가 남아 있습니다. 대량 사용자 Invoice import는 이번 범위가 아닙니다.

Bank/Card Reconciliation이 다음 후보입니다. 이번 변경은 Closing/재무제표/Tax/Asset/Inventory/외부 결제/새 Agent Tool을 선행 구현하지 않습니다. 상세 재사용 판정과 API/상태/잠금/증빙 계약은 업무문서 설계 문서에 기록했습니다.
