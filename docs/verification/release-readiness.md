# 제품 검증과 릴리즈 준비도

## 상태를 읽는 기준

기준 main: `34874eb23569da35f1010b178fc072dcee4ebfea`. 이 문서는 구현·자동 검증·실제 사용자 승인·운영 출시를 구분한다. 설계 복사 폴더는 로컬 전용으로 유지한다. 지원하지 않는 기능과 실행하지 않은 검증을 완료로 표시하지 않는다.

## 기능별 증거 지도

| 업무 | 현재 지원 | 집중 PostgreSQL 증거 | 남은 조건 |
|---|---|---|---|
| 전표·장부 | 독립 승인·Posting·기간잠금·동시성 | test_journal_flow.py, test_posting_concurrency.py | 실제 회사 회계 검토 |
| 마감 | 준비도·차단·독립 승인·마감·재개 | test_closing_workflow.py | 업종별 실제 월말 Pilot |
| SCE | 전기 BS·현재 IS·배당·자본 대사·불변성 | test_equity_statement.py | 물리적 손익 대체와 IS 충돌은 PROFIT_TRANSFER_IS_MISMATCH로 차단; #112 미종료 |
| Notes | 지원 Fact·원천·Narrative·독립 승인·Export | test_equity_statement.py의 정상 Notes 경로, test_disclosures.py의 원천 누락 차단 | 지원 DoD 재확인 후 #117 종료; Asset/Inventory/Tax 세부 주석·법정 제출 적합성 제외 |
| 비교 | 같은 taxonomy의 CLOSED BS/IS, 표시 재분류·독립 승인 | test_comparative_statements.py | CF/SCE/Notes 비교·taxonomy bridge·restatement 제외 |
| Agent | 조회·초안 제안·기간 공동 검토·비교 검토 | test_agent_reporting_tools.py, test_comparative_statements.py | 승인된 보고서 Export 외 변경성 Action·운영 worker 제외 |
| Export | 지원 제표 PDF/XLSX/CSV·권한·digest·다운로드 | test_report_center.py, test_equity_statement.py, test_comparative_statements.py | 로컬 파일 복구 검증 완료; 운영 일관 백업·장기 보존 미검증 |
| DB | migration lifecycle·FK·제약·불변 trigger | test_migrations.py 및 위 업무 테스트 | 실제 운영 용량·권한 role·복원 시간 목표 |

테스트 함수 수만으로 Coverage를 판단하지 않는다. 한 통합 테스트에 포함된 회계·권한·불변성 assertion과 실패 경로를 함께 확인한다. Notes 정상 경로가 SCE 통합 파일에 있다는 이유로 미구현으로 판단하지 않는다.

## 화면 상태 격리

비교 Workspace의 상세·원천·생성·승인·Export 요청은 scope epoch와 요청 lane을 사용한다. 회사·기간·revision 변경 및 unmount 뒤 늦은 응답은 표시하지 않는다. 같은 원천 조회의 이전 응답도 마지막 선택을 덮어쓰지 않는다. request-scope.test.ts의 지연 Promise 검증을 사용한다.

## 합성자료 Pilot과 운영 복원

실행 명령은 backend 개발 venv Python으로 다음 스크립트를 호출한다.

- `scripts/verify_accounting_pilot.py`: 컨테이너의 개발 DB와 분리된 *_test DB에서 전표·동시성·마감·SCE·Notes·비교·Agent·Report Center·migration 집중 검증. `.local/release-gate/`에 JUnit과 결과를 저장한다.
- `scripts/verify_storage_recovery.py`: 로컬 Object Storage를 새 archive와 새 경로로 복원하고 모든 파일 SHA-256을 비교한다. 원천 링크·빈 저장소를 거부하며 원본을 수정하지 않는다.
- `scripts/verify_postgres_recovery.py --database accounting_pilot_test`: 테스트 DB만 custom-format pg_dump 후 새 recovery_*_test DB에 pg_restore한다. 전체 사용자 table의 행 수·digest와 원천 안정성, dump SHA-256을 비교한다. 원천·복원 DB를 자동 삭제하지 않는다. 결과와 archive는 Git에서 제외된 `.local/release-gate/`에 보존한다.

복원 검증은 테스트 DB와 현재 데이터에 한정한다. rollback된 fixture의 전체 회계 자료가 dump에 남아 있다고 가정하지 않는다. production DB·외부 object storage·TLS·RPO/RTO·오프사이트 보존은 별도 운영 검증 대상이다. archive에는 개인정보가 포함될 수 있으므로 실제 운영에는 접근 제어·암호화·보존 정책이 먼저 필요하다.

## 실제 Shadow Accounting Pilot의 미충족 조건

실제 회사 자료와 독립 Reviewer가 제공되지 않았으므로 실제 고객 Pilot은 미실행이다. 합성자료 통과로 이를 대체하지 않는다. 다음 조건을 갖춘 뒤 사용자가 최종 승인한다.

1. 대상 업종·회계기준·한 달 기간·익명화/사용 허가가 확인된 원천과 기준 장부를 준비한다.
2. 작성자·Reviewer를 별도 계정으로 배정하고 입력→전표→대사→마감→제표→승인→다운로드를 수행한다.
3. 기준 장부와 원장/TB/BS/IS/CF/SCE/Notes의 숫자·출처·차단 결과를 비교하고 차이는 근거로 해결한다.
4. 재마감·실패 재시도·권한 회수·회사 전환·승인 후 원천 변경을 재현한다.
5. 담당자의 막힘, 작업시간, 정정 건수와 미지원 사례를 기록하고 별도 sign-off한다.

## 출시 판정

현재는 내부 검증 단계다. 핵심 지원 경로의 집중 테스트 통과는 전체 Release Gate 통과를 뜻하지 않는다. 실제 Pilot 승인, 운영 DB와 Artifact 복구 훈련, 최소권한·비밀관리·오프사이트 backup, 장애 관측/대응, 배포·롤백 절차와 책임자 확정 후 제한된 출시를 판단한다. Asset·Inventory·세무 전체 및 queue worker는 별도 Domain/운영 마일스톤이다.

## 이번 실행 결과

- 로컬 PostgreSQL 격리 DB `accounting_pilot_test`: 위 9개 파일 25건 통과, skip 0건, 227.77초. GenAI 의존성 deprecation 경고 1건. 이는 실제 고객 자료가 아닌 기존 합성 fixture 검증이다.
- 아키텍처·모듈 경계·Registry/승인 Export Tool: 33건 통과. 신규 COMMAND는 모델 adapter 목록에서 제외되고 사람 확인 문맥이 없으면 실행 전에 거부된다.
- Frontend: 지연 응답 검증 포함 58건 통과, lint/typecheck 통과. 실제 브라우저 전체 E2E는 미실행이다.
- PostgreSQL 복원: `agent_workflow_test` → `recovery_6ef6b23dd870_test`, 사용자 테이블 153개, 행 수·SHA-256 모두 일치, 원천 변화 없음, 8.02초. 테스트 DB의 보존된 데이터만 검증한 수치다.
- Object Storage: `.local/storage` 파일 3개를 새 archive와 새 경로로 복원, SHA-256 일치, 원천 변화 없음. DB와 같은 시점의 일관 백업 및 원격 저장소 재해복구를 검증한 것은 아니다.
- 사용자 확인: 실제 회사 자료 없음. 실제 Shadow Accounting Pilot은 BLOCKED로 유지한다. 설계 목표 RPO 15분 이하·RTO 4시간 이하의 운영 충족, 오프사이트 보관·독립 담당자 sign-off는 미검증이다.

원본 테스트 expected, skip/xfail 및 핵심 assertion은 변경하지 않았다. 신규 회계 규칙이나 물리적 손익 대체 지원을 추정하지 않았으며 기존 차단 계약을 유지한다.

최종 Report Center 멱등 fingerprint 호환성 보완 후 비교·Report Center 집중 PostgreSQL 4건을 추가 실행해 모두 통과했다(47.57초). Notes #117은 지원 범위의 검증 증거를 남기고 종료했으며, SCE #112는 물리적 손익 대체 표시 계약의 제한을 기록하고 유지했다. #83 로드맵도 실제 지원 범위에 맞춰 현행화했다. 각 Pilot 실행 결과는 고유한 하위 폴더에 기록해 이전 검증을 덮어쓰지 않는다.

[PR #123](https://github.com/chaehun0i/ai-accounting-office/pull/123)의 기능 HEAD `939b604`에서 [Quality CI](https://github.com/chaehun0i/ai-accounting-office/actions/runs/42770642875) backend/frontend/PostgreSQL/infrastructure/scope 5개 작업이 모두 통과했다. PR은 코드 리뷰 대상으로 준비하며 자동 merge·운영 배포·출시 승인으로 해석하지 않는다.

SCE의 진단금액·Journal/Evidence·차단 해결 작업함은 [자본변동 대사 계약](../accounting/equity-reconciliation-workflow.md)에 정리했다. #112의 POST_CLOSING·IS 표시 잔여 계약과 구분하며, 원천 누락/stale 진단을 0원으로 채우지 않는다.
