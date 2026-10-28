# 세무 신고자료 준비 V1

`028_tax_preparation`은 회사별 세무 프로필, VAT·원천세 준비기간, 거래에 연결된 VAT/원천세 판정 이력과 명령 멱등성 영수증을 관계형 테이블로 저장한다. 세무 Fact의 정정은 기존 행을 바꾸지 않고 revision을 추가하며, 조회·합계는 거래별 최신 revision만 사용한다. 회사 범위 FK와 인덱스가 다른 회사 참조를 차단한다.

`/tax/profiles`, `/tax/periods`, `/tax/periods/{period_id}/vat`, `/tax/periods/{period_id}/withholding`, `/tax/periods/{period_id}/preparation`을 사용한다. 변경 요청은 기존 회사 권한·CSRF·Idempotency-Key를 적용한다. 준비 조회는 Decimal 합계와 원천 digest, 누락된 Profile·증빙·분류·원천 변경을 차단 코드로 보여준다.

이 기능은 **신고자료 준비**까지만 제공한다. 사용자가 입력한 Rule reference를 검증된 법규로 취급하지 않는다. 검증된 세율·규칙·서식·회계 승인·사람 검토가 없어 `ready_to_file`은 항상 `false`이며 전자신고 Command는 없다. Tax Profile의 기존 유효기간을 종료하고 후속 버전으로 전환하는 경로도 아직 없다.

검증: 빈 PostgreSQL의 028 upgrade·downgrade lifecycle, 관계형 스키마 정책, Profile/기간 멱등 재시도와 회사 격리, VAT 정정의 최신 revision 합계, Ruff, format, mypy, migration head 단위 검사를 통과했다. 전체 세무 Golden·법규 검증·동시성 테스트는 이 범위의 완료 증거가 아니다.
