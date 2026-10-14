# CLOSED 기간 BS/IS

재무제표 메뉴는 CLOSED 회계기간의 최신 완료된 Closing Run과 조정 시산표를 읽어 재무상태표(BS)와 손익계산서(IS)를 생성합니다. 생성 결과는 `GENERATED` 상태의 관계형 스냅샷이며 승인된 공식 보고서가 아닙니다. Journal과 GL은 변경하지 않습니다.

`KR_INTERNAL` taxonomy v1의 계정 매핑은 기본 KR 계정 템플릿 ID와 안정된 계정 코드로 명시적으로 등록합니다. 회사가 추가한 계정은 재무제표 화면에서 계정 유형에 맞는 표시 항목에 먼저 연결해야 합니다. POSTED 장부에서 사용된 계정에 매핑이 없거나 중복되면 생성을 차단합니다. 이 버전에서는 최초 매핑만 등록할 수 있으며 기존 매핑 재분류와 taxonomy 개정은 후속 범위입니다.

BS는 마감일 누적 잔액을, IS는 선택 기간의 수익·비용 movement를 사용합니다. 월별 soft close는 손익 계정을 물리적으로 자본으로 대체하지 않으므로 BS에는 누적 손익을 `미대체 누적손익`으로 명시해 자산 = 부채 + 자본을 검증합니다. 이는 새 분개가 아닙니다. 비용과 차감계정의 부호는 Decimal 차대 잔액과 taxonomy의 normal sign으로 계산하며 임의 `abs()` 보정은 하지 않습니다.

`POST /financial-statements/generate`에는 회사 헤더와 Idempotency-Key가 필요합니다. 동일 마감 버전·시산표 digest·taxonomy·매핑 digest의 재요청은 기존 세트를 반환합니다. 마감 장부가 바뀌면 생성은 실패합니다. 세트, BS/IS, 항목별 계정·전표 라인 출처는 각각 조회 API로 확인할 수 있습니다. 다른 회사의 세트는 조회되지 않습니다.

이 단계는 BS/IS 생성과 읽기만 제공합니다. 승인, 비교재무제표, CF/SCE, 주석, Export는 포함하지 않습니다. 전체 회귀와 브라우저 E2E는 Fast Development Mode의 후속 Release Gate로 남깁니다.
