# 연간 재무 회귀 입력 v1

2026-10-11에 공식 native Google Sheet `AI_Accounting_Office_SAMPLE_COMPANY_2025`의 아래 탭을 연결 도구로 직접 읽은 CSV snapshot입니다. 원본 ID는 `1C_URD6dlROitLTmN6ZTAhBdebF0Dc3_bl3dzaIiXvA8`입니다. 회사는 SYN_MFG_001 / 가온푸드웍스 주식회사입니다. CSV의 원본 표기·값을 임의 수정하지 않습니다.

운영 importer가 아니라 테스트 전용 deterministic adapter가 확정 회계 전표를 만들고 배분·Aging·GL 대사를 검증합니다. native Sheet가 공식 정본이며, 같은 Drive 폴더의 `_v1.xlsm`은 legacy/raw artifact입니다. XLSM 허용 목록을 추가하지 않았습니다. 기존 macro 없는 Onboarding XLSX도 변경하지 않았습니다.

| 탭 | 행 수 | SHA-256 |
| --- | ---: | --- |
| Sales_Invoices | 240 | 126f97bc49bc23e2f188db84f327675d4e7fca873059cd69626bf062e0489d4e |
| Purchase_Invoices | 74 | 9c9b1613bf206c4f6166eb68c2bc004188dd655adf038ba1cebe5a7587f48570 |
| Sales_Lines | 486 | 2ce22ba8145bdf8a407fb09bcbfee2518c54a7a46443d7c3c3729d9fa3da2921 |
| Purchase_Lines | 148 | 1df382b6f1fb1159901358da95626970b3ba34fa11f5b462dd2df3227244d8da |
| AR_Collections | 180 | f16c504f59800dbe40026d5c7f18d41a0ec917b63fdc665367bfc3a2f1478407 |
| AP_Payments | 60 | 19a7d101bf5ba07065340dd98b03daf8e0a76fdf0a58f302e95f801cffb6f610 |
| Counterparties | 20 | 56c436f5a0e60f7bff3231db140e7fe0a8e21e45ef1c54c1f7e64f6336cafcaf |
| Expected_Checks | 13 | a15967f58822e72e22fb171e8ba422007ab241d37ab4ca665b923c4e871dc429 |
| Test_Scenarios | 8 | a93451873a2369b3fe70d4c971c4ad93856474eaac774493e653d1cd9dd39c47 |

COLL_MULTI_001의 SINV0179/SINV0180, PAY_MULTI_001의 PINV0060은 발생일보다 정산일이 앞섭니다. 테스트가 두 batch 전체를 거부함을 명시적으로 단언합니다. 원본이나 expected를 조용히 고치지 않습니다.

2025-12-31 기준, 위 두 오류 batch를 제외하고 유효한 정산만 반영한 deterministic 기대값은 AR 원금 781,044,000 − 수금 335,934,060 = **445,109,940**, AP 원금 195,277,500 − 지급 101,098,690 = **94,178,810**입니다. 이는 원본의 모든 batch를 무조건 반영한 expected와 구분됩니다. 세무 데이터는 신고 정답으로 사용하지 않습니다.

기존 XLSX SHA-256: `c4df64f12fc517b73f1ef0c164bdeb541c1039a6c43d8ee3971310b414761d02`.
