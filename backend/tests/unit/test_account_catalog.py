"""확장 계정체계와 이전 버전 불변성을 검증합니다."""

from app.accounting.domain.rules import validate_account, validate_hierarchy
from app.accounting.templates.domain.defaults import (
    DEFAULT_ACCOUNTS,
    DEFAULT_TEMPLATE,
    LEGACY_ACCOUNTS,
    LEGACY_TEMPLATE,
)


def test_extended_catalog_keeps_legacy_meaning_and_valid_balances():
    assert LEGACY_TEMPLATE.version == 1
    assert DEFAULT_TEMPLATE.version == 2
    assert len(LEGACY_ACCOUNTS) == 25
    assert len(DEFAULT_ACCOUNTS) >= 120
    accounts = {row.account_code: row for row in DEFAULT_ACCOUNTS}
    assert len(accounts) == len(DEFAULT_ACCOUNTS)
    for old in LEGACY_ACCOUNTS:
        current = accounts[old.account_code]
        assert current.id != old.id
        for key in (
            "account_name",
            "account_type",
            "normal_balance",
            "posting_allowed",
            "is_contra",
        ):
            assert getattr(current, key) == getattr(old, key)
    for account in DEFAULT_ACCOUNTS:
        validate_account(account.account_type, account.normal_balance, account.is_contra)
    validate_hierarchy({row.account_code: row.parent_code for row in DEFAULT_ACCOUNTS})
    assert accounts["3040"].normal_balance == "DEBIT"
    assert accounts["1150"].normal_balance == "CREDIT"
    assert {"1210", "1640", "2070", "3060", "4030", "5300", "5400"} <= accounts.keys()
