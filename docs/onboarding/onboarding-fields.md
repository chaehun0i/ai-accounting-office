# 온보딩 필드 목록

Catalog v1의 코드 정의에서 생성한 문서입니다. 실행 계약은 API가 제공하며 화면에 별도 목록을 두지 않습니다.

## 회사 기본정보

| Field | 표시명 | 자료형 / 입력 모드 | 필수 규칙 |
| --- | --- | --- | --- |
| `Company.company_name` | 회사명 | TEXT / TEXT | ALWAYS |
| `Company.business_number` | 사업자등록번호 | TEXT / TEXT | ALWAYS |
| `Company.corporation_number` | 법인등록번호 | TEXT / TEXT | CORPORATION |
| `Company.taxpayer_type` | 사업자 유형 | TEXT / LOOKUP | ALWAYS |
| `Company.opening_date` | 개업일 | DATE / DATE | ALWAYS |
| `Company.timezone` | 시간대 | TEXT / LOOKUP | ALWAYS |
| `Company.no_opening_balance` | 기초잔액이 없는 신규 회사입니다 | BOOLEAN / BOOLEAN | NEVER |

## 회계설정

| Field | 표시명 | 자료형 / 입력 모드 | 필수 규칙 |
| --- | --- | --- | --- |
| `Accounting_Settings.functional_currency_code` | 기능통화 | TEXT / LOOKUP | ALWAYS |
| `Accounting_Settings.fiscal_year_start_month` | 회계연도 시작 월 | NUMERIC / NUMBER | ALWAYS |
| `Accounting_Settings.accounting_framework_code` | 회계기준 | TEXT / LOOKUP | ALWAYS |
| `Accounting_Settings.reporting_taxonomy_code` | 보고 분류 | TEXT / LOOKUP | ALWAYS |
| `Accounting_Settings.journal_number_prefix` | 전표번호 접두어 | TEXT / TEXT | ALWAYS |

## 계정과목

| Field | 표시명 | 자료형 / 입력 모드 | 필수 규칙 |
| --- | --- | --- | --- |
| `COA.account_code` | 계정 코드 | TEXT / TEXT | ALWAYS |
| `COA.account_name` | 계정명 | TEXT / TEXT | ALWAYS |
| `COA.account_type` | 계정 유형 | TEXT / LOOKUP | ALWAYS |
| `COA.normal_balance` | 정상 잔액 | TEXT / LOOKUP | ALWAYS |
| `COA.posting_allowed` | 전기 허용 | BOOLEAN / BOOLEAN | ALWAYS |

## 거래처

| Field | 표시명 | 자료형 / 입력 모드 | 필수 규칙 |
| --- | --- | --- | --- |
| `Counterparties.counterparty_code` | 거래처 코드 | TEXT / TEXT | ALWAYS |
| `Counterparties.legal_name` | 거래처 정식명 | TEXT / TEXT | ALWAYS |
| `Counterparties.business_number` | 사업자등록번호 | TEXT / TEXT | NEVER |
| `Counterparties.counterparty_type` | 거래처 유형 | TEXT / LOOKUP | ALWAYS |
| `Counterparties.payment_term_code` | 지급조건 코드 | TEXT / TEXT | NEVER |
| `Counterparties.role_code` | 거래처 역할 | TEXT / LOOKUP | NEVER |

## 은행

| Field | 표시명 | 자료형 / 입력 모드 | 필수 규칙 |
| --- | --- | --- | --- |
| `Bank_Accounts.bank_account_code` | 관리 코드 | TEXT / TEXT | ALWAYS |
| `Bank_Accounts.alias` | 별칭 | TEXT / TEXT | ALWAYS |
| `Bank_Accounts.provider_code` | 금융기관 코드 | TEXT / TEXT | ALWAYS |
| `Bank_Accounts.currency_code` | 통화 | TEXT / LOOKUP | ALWAYS |
| `Bank_Accounts.external_reference` | 외부 보관소 참조 | TEXT / TEXT | NEVER |

## 카드

| Field | 표시명 | 자료형 / 입력 모드 | 필수 규칙 |
| --- | --- | --- | --- |
| `Card_Accounts.card_account_code` | 관리 코드 | TEXT / TEXT | ALWAYS |
| `Card_Accounts.alias` | 별칭 | TEXT / TEXT | ALWAYS |
| `Card_Accounts.provider_code` | 금융기관 코드 | TEXT / TEXT | ALWAYS |
| `Card_Accounts.currency_code` | 통화 | TEXT / LOOKUP | ALWAYS |
| `Card_Accounts.external_reference` | 외부 보관소 참조 | TEXT / TEXT | NEVER |

## 기초잔액

| Field | 표시명 | 자료형 / 입력 모드 | 필수 규칙 |
| --- | --- | --- | --- |
| `Opening_Balances.as_of_date` | 기준일 | DATE / DATE | ALWAYS |
| `Opening_Balances.account_code` | 계정 코드 | TEXT / TEXT | ALWAYS |
| `Opening_Balances.debit_amount` | 차변 금액 | NUMERIC / NUMBER | ALWAYS |
| `Opening_Balances.credit_amount` | 대변 금액 | NUMERIC / NUMBER | ALWAYS |
| `Opening_Balances.counterparty_code` | 거래처 코드 | TEXT / TEXT | NEVER |
| `Opening_Balances.currency_code` | 통화 | TEXT / LOOKUP | NEVER |
| `Opening_Balances.debit_total` | 차변 합계 | NUMERIC / DERIVED_READONLY | NEVER |
| `Opening_Balances.credit_total` | 대변 합계 | NUMERIC / DERIVED_READONLY | NEVER |
| `Opening_Balances.balance_difference` | 차대 차이 | NUMERIC / DERIVED_READONLY | NEVER |

## 고정자산

| Field | 표시명 | 자료형 / 입력 모드 | 필수 규칙 |
| --- | --- | --- | --- |
| `Fixed_Assets.asset_code` | 자산 코드 | TEXT / TEXT | ALWAYS |
| `Fixed_Assets.asset_name` | 자산명 | TEXT / TEXT | ALWAYS |
| `Fixed_Assets.acquisition_date` | 취득일 | DATE / DATE | ALWAYS |
| `Fixed_Assets.acquisition_cost` | 취득원가 | NUMERIC / NUMBER | ALWAYS |
| `Fixed_Assets.useful_life_months` | 내용연수 개월 | NUMERIC / NUMBER | ALWAYS |
| `Fixed_Assets.depreciation_method` | 감가상각 방법 | TEXT / LOOKUP | ALWAYS |

## 재고 품목

| Field | 표시명 | 자료형 / 입력 모드 | 필수 규칙 |
| --- | --- | --- | --- |
| `Inventory_Items.item_code` | 품목 코드 | TEXT / TEXT | ALWAYS |
| `Inventory_Items.item_name` | 품목명 | TEXT / TEXT | ALWAYS |
| `Inventory_Items.unit_of_measure` | 단위 | TEXT / TEXT | ALWAYS |
| `Inventory_Items.cost_method` | 원가 방법 | TEXT / LOOKUP | ALWAYS |
| `Inventory_Items.opening_quantity` | 기초 수량 | NUMERIC / NUMBER | NEVER |
| `Inventory_Items.opening_unit_cost` | 기초 단가 | NUMERIC / NUMBER | NEVER |

## 기초 재고

| Field | 표시명 | 자료형 / 입력 모드 | 필수 규칙 |
| --- | --- | --- | --- |
| `Opening_Inventory.as_of_date` | 기준일 | DATE / DATE | ALWAYS |
| `Opening_Inventory.item_code` | 품목 코드 | TEXT / TEXT | ALWAYS |
| `Opening_Inventory.opening_quantity` | 기초 수량 | NUMERIC / NUMBER | ALWAYS |
| `Opening_Inventory.opening_unit_cost` | 기초 단가 | NUMERIC / NUMBER | ALWAYS |

## 기초 매출채권

| Field | 표시명 | 자료형 / 입력 모드 | 필수 규칙 |
| --- | --- | --- | --- |
| `AR_Opening.counterparty_code` | 거래처 코드 | TEXT / TEXT | ALWAYS |
| `AR_Opening.reference_code` | 원천 참조 | TEXT / TEXT | ALWAYS |
| `AR_Opening.original_amount` | 원금 | NUMERIC / NUMBER | ALWAYS |
| `AR_Opening.due_date` | 만기일 | DATE / DATE | ALWAYS |
| `AR_Opening.account_code` | 계정 코드 | TEXT / TEXT | ALWAYS |

## 기초 매입채무

| Field | 표시명 | 자료형 / 입력 모드 | 필수 규칙 |
| --- | --- | --- | --- |
| `AP_Opening.counterparty_code` | 거래처 코드 | TEXT / TEXT | ALWAYS |
| `AP_Opening.reference_code` | 원천 참조 | TEXT / TEXT | ALWAYS |
| `AP_Opening.original_amount` | 원금 | NUMERIC / NUMBER | ALWAYS |
| `AP_Opening.due_date` | 만기일 | DATE / DATE | ALWAYS |
| `AP_Opening.account_code` | 계정 코드 | TEXT / TEXT | ALWAYS |
