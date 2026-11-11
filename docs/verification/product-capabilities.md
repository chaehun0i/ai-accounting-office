# 제품 지원 범위와 잔여 완료 조건

2026-11-12 구현 기준 main `763744213cfaaa2ea05bbf82c677ce393277b7cd`. 로컬 설계 정본은 `docs/AI_Accounting_Office_v0.2.6_통합설계_정본/`이며 Git 제외 상태를 유지한다. 이 문서는 전체 줄의 수동 감사나 전체 Release Gate 통과 기록이 아니다. 당시 검증 문서를 현재 기능 부재의 증거로 사용하지 않는다.

| 업무 | 현재 지원 | 남은 완료 조건과 코드 근거 |
| --- | --- | --- |
| 전표·원장·마감 | 독립 승인·POSTED·기간잠금·GL/TB·월마감 | 연말 hard-close 원천 identity와 ADJUSTED/POST_CLOSING 계약. `closing/application/service.py`, `accounting/journals/infrastructure/models.py` |
| BS/IS/CF/SCE | 관계형 Snapshot·원천 대사·조회·Export | SCE 물리적 손익 대체의 IS 충돌은 차단 유지. [#112](https://github.com/chaehun0i/ai-accounting-office/issues/112). `reporting/equity/service.py` |
| Notes | 구조화 Fact·Narrative·독립 승인·불변 revision·Export | 미지원 Asset/Inventory/Tax 세부 공시를 추정하지 않음. `reporting/disclosures/` |
| 비교 재무제표 | 같은 taxonomy BS/IS·표시 재분류·독립 승인·Export | CF/SCE/Notes 비교, taxonomy bridge와 restatement 미지원. `reporting/comparatives/` |
| 전체 제표 세트 승인 | Notes·비교 승인과 구분 | BS/IS/CF/SCE/Notes의 정확한 revision을 한 승인 대상에 고정하는 전체 세트 승인 필요. BS/IS GENERATED를 APPROVED로 해석하지 않음 |
| 고정자산 | 정액법 Decimal 계산과 Domain entity | `assets/domain/`의 계산 규칙만 존재. 정책·대장 영속화, POSTED 취득 원천, 감가상각 제안→독립 승인→Posting, 처분/손상·GL 대사·화면 필요 |
| 재고·선택 원가 | 기존 전표로 회계 표현 가능 | 품목·창고·수불·평가·실사·GL 대사 Subledger 미구현. 업종별 선택 Capability와 기본 회계 분리 |
| 세무 | Profile·VAT/원천세 준비 V1 | `tax/rules.py`의 Rule/Form 미검증 차단 유지. 검증된 규칙·효력일·승인·후속 Profile·사용자 화면 필요. 제출 가능으로 표시하지 않음 |
| AR/AP 실무 예외 | 부분정산·대사 | 정산 취소·역분개 연계, 대손 및 후속 미배분금 적용 계약 보완. `finance/settlements/` |
| Agent | Registry→Application 조회·초안·공동 검토·비교 검토·사람 확인 승인본 Export | 다른 변경성 Action, 상시 worker·취소·장애 복구 운영 필요. 기존 Tool 지원 범위와 구분 |
| 계정·팀 | 인증·회사 격리·초대·RBAC | 계정 복구·이메일 검증·팀 권한 변경 lifecycle 필요. `identity/`, `companies/` |
| 배포 준비 | liveness; PR #126에서 DB/migration readiness | production Storage·보존·관측/alert·capacity·배포/롤백 훈련 필요 |
| 복구·출시 | 합성 Pilot·로컬 DB 및 파일 개별 복원 | DB+파일 일관 백업·PITR·오프사이트·운영 RPO≤15분/RTO≤4시간·월간 훈련·최종 Release Gate 필요 |
| 실제 고객 Pilot | 미실행 | 사용자가 실제 자료가 없음을 확인함. 허가된 원천·기준 장부·독립 Reviewer와 sign-off 필요 |

실행 순서는 #112의 원천/표시 계약 확정, 전체 제표 세트 승인, 고정자산 장부 연결을 핵심 회계 트랙으로 삼는다. 재고/원가·세무는 검증된 정책과 대상 업종의 범위를 정해 별도 수직 기능으로 완성한다. 운영 트랙은 readiness 이후 일관 복구·관측·Release Gate를 진행한다. 고객 자료나 외부 자격증명이 필요한 검증을 합성자료 통과로 대체하지 않는다.

지원 기능의 최신 계약은 [Report Center](../accounting/report-periods.md), [SCE 대사](../accounting/equity-reconciliation-workflow.md), [비교 재무제표](../accounting/comparative-financial-statements.md), [서비스 readiness](../platform/service-readiness.md)를 참고한다. 범위별 PR은 merge 전까지 main 완료로 표시하지 않는다.
