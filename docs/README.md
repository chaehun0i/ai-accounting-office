# 문서 읽기 안내

현재 구현 상태는 [루트 README](../README.md)와 [아키텍처](architecture.md)를 기준으로 확인합니다. 설계 SSOT는 Google Drive의 `AI_Accounting_Office_v0.2.6_통합설계_정본`이며, GitHub main은 구현 사실의 기준입니다. 과거 PR의 SHA·테스트 수치가 적힌 검증 문서는 당시 실행 기록이므로 최신 구현 범위로 읽지 않습니다.

현재 사용자 경로: [업무 메뉴](page-navigation.md), [AI Agent Runtime](agent-runtime.md), [월마감](period-closing.md), [재무제표](financial-statements.md). `AI 회계팀`은 기간 선택 → 질문 → 읽기 전용 Closing/BS·IS Tool → 답변·금액·근거 확인을 제공합니다.

회계·재무 계약: [회계 마스터](accounting-master.md), [관리차원](accounting-dimensions.md), [거래·전표·원장](transaction-journal-ledger.md), [채권·채무](finance-subledger.md), [업무문서](business-documents.md), [은행·카드 대사](bank-card-reconciliation.md).

데이터와 기반: [인증·회사](identity-company.md), [증빙·가져오기](storage-evidence-intake.md), [확정 가져오기 거래 승격](import-transaction-promotion.md), [온보딩](onboarding-data-exchange.md), [DB 기반](database-foundation.md), [환경 설정](environment.md), [약어](abbreviations.md).

`*-verification.md`, `verification*.md`, 초기 시연·구현 초안 문서는 재현 가능한 **당시 검증 이력**입니다. 해당 파일의 과거 head·기능 제외 문구는 지금 main의 기능 부재를 뜻하지 않습니다. 이력을 덮어써 성공 수치나 기준선을 소급 변경하지 않습니다.

PR #18 이후의 오류·코드 정리 결과는 [검증 기록](post-merge-quality.md)에 있습니다.
저장소 전반의 정적·테스트 점검과 보수적 정리 범위는 [코드·테스트 정리 기록](codebase-audit.md)에 있습니다.
