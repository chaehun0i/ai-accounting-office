# 약어와 용어

코드·설계의 표준 약어는 유지하되 사용자 화면에는 한국어 의미를 우선 표시합니다.

| 표기 | 원어 | 이 프로젝트의 의미 |
| --- | --- | --- |
| API | Application Programming Interface | 화면·자동화가 호출하는 서비스 계약 |
| AR / AP | Accounts Receivable / Accounts Payable | 매출채권 / 매입채무 |
| COA | Chart of Accounts | 회사별 계정과목 체계 |
| CSV | Comma-Separated Values | 쉼표 구분 표 파일 |
| XLSX | Excel Open XML Workbook | 매크로 없는 공식 Excel 파일 형식 |
| XLSM | Excel Macro-Enabled Workbook | 매크로 가능 파일, 업로드 지원 안 함 |
| OOXML | Office Open XML | XLSX의 ZIP/XML 기반 문서 형식 |
| XML | Extensible Markup Language | Workbook 내부 문서 표현 |
| ZIP | ZIP archive format | 압축 컨테이너, 압축 폭탄·경로 검증 대상 |
| MIME | Multipurpose Internet Mail Extensions | 업로드 파일의 콘텐츠 유형 표기 |
| VBA | Visual Basic for Applications | Excel 매크로 실행 언어, 차단 대상 |
| DB | Database | PostgreSQL 관계형 저장소 |
| DDL | Data Definition Language | 테이블·제약·인덱스 정의 |
| ORM | Object-Relational Mapping | SQLAlchemy 모델과 관계형 저장의 연결 |
| FK / PK | Foreign Key / Primary Key | 외래키 / 기본키 |
| UUID | Universally Unique Identifier | Python UUID와 PostgreSQL UUID 식별자 |
| UoW | Unit of Work | Application이 소유하는 원자적 트랜잭션 경계 |
| JSON / JSONB | JavaScript Object Notation / Binary JSON | API 직렬화는 허용, 업무 DB 컬럼은 금지 |
| SQL | Structured Query Language | 관계형 DB 질의 언어 |
| UTC | Coordinated Universal Time | timezone-aware 시간 기준 |
| TIMESTAMPTZ | Timestamp With Time Zone | PostgreSQL timezone-aware timestamp |
| RBAC | Role-Based Access Control | 회사 Membership과 Permission 기반 권한 |
| IDOR | Insecure Direct Object Reference | 다른 회사 ID로 접근하는 취약점, query scope로 차단 |
| CSRF | Cross-Site Request Forgery | 다른 사이트의 요청 위조, Origin/header 검증 |
| SHA-256 | Secure Hash Algorithm 256-bit | 원본 파일 무결성 해시 |
| TTL | Time To Live | 미리보기 유효기간 900초 |
| K_GAAP | Korean Generally Accepted Accounting Principles | 일반기업회계기준 코드 |
| K_IFRS | Korean International Financial Reporting Standards | 한국채택국제회계기준 코드 |
| KRW | Korean Won | 현재 활성 기능통화, 대한민국 원 |
| FIFO | First In, First Out | 선입선출법, 재고 초안의 typed 선택값 |
| GL / TB | General Ledger / Trial Balance | 총계정원장 / 시산표, 후속 범위 |
| OCR | Optical Character Recognition | 문서 문자 인식, 이번 범위에 자동 확정 없음 |
| LLM | Large Language Model | 대규모 언어모델, 현재 Mapping/계산에 사용 안 함 |
| ESG | Environmental, Social and Governance | 참고 프로젝트의 업무 영역, 신규 Domain 이식 없음 |
| KPI | Key Performance Indicator | 참고 프로젝트의 파생 지표 개념, 현재 코드에 이식 없음 |
| DMA | Double Materiality Assessment | 참고 ESG 프로젝트의 중요성 평가, DROP 대상 |
| UI / UX | User Interface / User Experience | 사용자 화면 / 사용 경험 |
| CI | Continuous Integration | 자동 품질·회귀 검증 |
| E2E | End-to-End | 실제 브라우저부터 백엔드/DB까지 흐름 검증 |
| DoD | Definition of Done | 구현 완료 검증 조건 |
| ADR | Architecture Decision Record | 아키텍처 판단 기록 |
| Draft / Promotion | 초안 / 정본 승격 | 완료 전 입력과 승인된 Application Command 반영의 경계 |
| Digest / Fingerprint | 무결성 요약 / 요청 지문 | 파일·미리보기 검증 / 멱등 요청 비교 값 |
| KEEP_CURRENT / APPLY_IMPORT | 현재 값 유지 / Excel 값 적용 | 명시적인 병합 충돌 해결 선택 |
