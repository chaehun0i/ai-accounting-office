# 금융 원천 regression snapshot v1

`fixture_schema_version=1`, `expected_result_version=1`입니다. 2026-10-12에 최신 활성 설계의 native Google Sheet를 범위 지정하여 읽은 CSV 스냅샷입니다. 원본 Sheet와 기존 Golden expected는 수정하지 않았습니다. `adapter.py`는 날짜·금액·입출금·원천 참조를 기존 Intake canonical column으로 결정적으로 투영합니다. 세액은 원천 test fact이며 세법 판정 결과가 아닙니다.

| 원천 | Google Sheet ID | 읽은 탭과 행 수 | 원본 수정 시각(UTC) |
| --- | --- | --- | --- |
| SYN_SERVICE_001 | 11wKJw18wJTDvvSFGmzSGv9xWRJNPR7bDD71DeOsh27Y | Bank_Transactions 3 | 2026-10-11T01:33:59.468Z |
| SYN_RETAIL_001 | 1kFdhOKBbZmMdXBgHP7rp8R4sP2SEsG4FM774TC0Blk8 | Bank_Transactions 2, Card_Transactions 2 | 2026-10-11T01:34:00.914Z |
| SAMPLE_COMPANY_2025 / SYN_MFG_001 | 1C_URD6dlROitLTmN6ZTAhBdebF0Dc3_bl3dzaIiXvA8 | Bank_Transactions 346, Card_Transactions 88 | 2026-10-09T22:26:23.495Z |

세 파일 모두 metadata의 MIME이 `application/vnd.google-apps.spreadsheet`입니다. 같은 폴더의 `AI_Accounting_Office_SAMPLE_COMPANY_2025_v1.xlsm`(ID `1YB9VcCJl9JgORHMf6X8w29vrgwsf-rd3`)은 MIME `application/vnd.ms-excel.sheet.macroenabled.12`인 legacy/raw artifact입니다. 공식 Onboarding/Import fixture로 사용하지 않았고 삭제하지 않았습니다. 문서의 native 3개 설명과 실제 추가 파일의 차이는 Drive 정리 후속 항목입니다.

서비스업 입금 3,300,000, 출금 1,100,000/2,000,000을 보존합니다. 소매업 은행 1,067,000 PG 순정산과 2,200,000 입금, 카드매출 1,100,000 및 환불 110,000을 보존합니다. 소매 카드매출은 MERCHANT 정산채권이며 제조업 법인카드 CORPORATE 미지급금과 구분합니다. PG 수수료 차이는 자동 비용 분개로 상쇄하지 않습니다.

| 스냅샷 | SHA-256 |
| --- | --- |
| native-service-v1/Bank_Transactions.csv | 9ad3248f998029ec31d73650b86d36dee9fa8ad290d73d5c43a97c80aaa1dd81 |
| native-retail-v1/Bank_Transactions.csv | e143195ddfb612b930ae57ddb4e43e636b4dab6e46fc07e68bbd50f90ba16254 |
| native-retail-v1/Card_Transactions.csv | c7dae6f6b076a80bf5f0cb114b30fde3b53391093729f1a9bd77dc157fce4931 |
| native-mfg-v1/Bank_Transactions.csv | 9da155df90a47d1cb5a1a174f5e93a6ade8c900054464f120b456c98d1c0e0b3 |
| native-mfg-v1/Card_Transactions.csv | d76745e8a5612104da0a82e76a69df6b49a6894badd50434b3a08d6b6db026b8 |

서비스/소매는 Intake→원천→거래 후보→사람 확정과 GL 차이 보존을 검증합니다. 제조업은 연간 원천 수·합계·identity·Import provenance·retry 중복 0을 검증합니다. 연간 모든 원천을 자동 확정하거나 기존 회계 장부를 다시 생성하는 테스트는 아닙니다.
