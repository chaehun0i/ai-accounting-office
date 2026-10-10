from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.accounting.application.service import AccountingMasterService
from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork
from app.accounting.templates.domain.defaults import DEFAULT_ACCOUNTS, DEFAULT_TEMPLATE
from app.accounting.templates.infrastructure.seed import seed_default_coa
from app.companies.application.service import CompanyService
from app.companies.infrastructure.unit_of_work import CompanySQLAlchemyUnitOfWork
from app.contracts.access_errors import ResourceNotFound, StateConflict, VersionConflict
from app.contracts.errors import IntegrityViolation
from app.identity.sessions.domain.entities import RequestFacts
from app.master_data.application.service import MasterDataService
from app.master_data.counterparties.domain.children import Address, BankReference, Contact, Role
from app.master_data.counterparties.domain.entities import Counterparty
from app.master_data.payment_terms.domain.entities import PaymentTerm


@pytest.fixture
def master(auth_service):
    auth, connection = auth_service
    factory = sessionmaker(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        autobegin=False,
        join_transaction_mode="create_savepoint",
    )
    result = auth.register(
        "master@example.com", "StrongPassword!2026", RequestFacts(uuid4(), "192.0.2.0/24", None)
    )
    principal = auth.authenticate(result.access_token)
    companies = CompanyService(lambda: CompanySQLAlchemyUnitOfWork(factory))
    company = companies.create(
        principal,
        company_name="GOLDEN_CORP_001",
        business_number="1234567890",
        taxpayer_type="CORPORATION",
        opening_date=date(2026, 1, 1),
        address="테스트 주소",
    ).company
    with MasterSQLAlchemyUnitOfWork(factory) as uow:
        seed_default_coa(uow.session)
        seed_default_coa(uow.session)
    return (
        principal,
        company,
        AccountingMasterService(lambda: MasterSQLAlchemyUnitOfWork(factory)),
        MasterDataService(lambda: MasterSQLAlchemyUnitOfWork(factory)),
        factory,
        companies,
    )


def test_initialize_repeatable_and_version(master):
    p, c, accounting, _, factory, _ = master
    value = accounting.initialize(p, c.id, fiscal_year=2026, template_id=DEFAULT_TEMPLATE.id)
    assert (
        accounting.initialize(p, c.id, fiscal_year=2026, template_id=DEFAULT_TEMPLATE.id) == value
    )
    assert len(accounting.accounts(p, c.id)) == len(DEFAULT_ACCOUNTS)
    periods = accounting.periods(p, c.id)
    assert len(periods) == 12 and periods[0].start_date == date(2026, 1, 1)
    changed = accounting.update_settings(p, c.id, 1, journal_number_prefix="JV")
    assert changed.version == 2
    with pytest.raises(VersionConflict):
        accounting.update_settings(p, c.id, 1, allow_manual_journal=False)
    with pytest.raises(StateConflict):
        accounting.initialize(p, c.id, fiscal_year=2027, template_id=DEFAULT_TEMPLATE.id)
    with MasterSQLAlchemyUnitOfWork(factory) as uow:
        assert uow.sequences.allocate(c.id, 2026, "JOURNAL") == 1
        assert uow.sequences.allocate(c.id, 2026, "JOURNAL") == 2
        assert uow.sequences.allocate(c.id, 2027, "JOURNAL") == 1
        assert uow.sequences.allocate(c.id, 2026, "OTHER") == 1


def test_counterparty_scope_children_and_version(master):
    p, c, _, data, factory, companies = master
    term = data.create_payment_term(
        p,
        PaymentTerm(
            company_id=c.id,
            term_code="NET30",
            name="30일 후 지급",
            due_rule_type="NET_DAYS",
            due_days=30,
        ),
    )
    initial = Counterparty(
        company_id=c.id,
        display_name="고객 A",
        legal_name="고객 A",
        normalized_legal_name="",
        business_number="123-45-67890",
        payment_term_id=term.id,
    )
    value = data.create_counterparty(
        p,
        initial,
        roles=(
            Role(counterparty_id=initial.id, role_code="CUSTOMER", effective_from=date(2026, 1, 1)),
        ),
        contacts=(
            Contact(
                counterparty_id=initial.id,
                contact_type="BILLING",
                contact_name="담당자",
                is_primary=True,
            ),
        ),
        addresses=(
            Address(
                counterparty_id=initial.id,
                address_type="BILLING",
                address_line1="테스트 주소",
                is_primary=True,
            ),
        ),
        bank_refs=(
            BankReference(
                counterparty_id=initial.id,
                bank_code="TEST",
                account_alias="테스트 참조",
                external_token=f"vault:{uuid4()}",
            ),
        ),
    )
    assert value.business_number == "1234567890"
    assert len(data.get_counterparty(p, c.id, value.id)[1]) == 1
    assert len(data.list_counterparties(p, c.id, role="CUSTOMER")) == 1
    with pytest.raises(IntegrityViolation):
        data.create_counterparty(p, replace(initial, id=uuid4()))
    updated = data.update_counterparty(p, c.id, value.id, 1, display_name="변경된 고객")
    assert updated.version == 2
    with pytest.raises(VersionConflict):
        data.update_counterparty(p, c.id, value.id, 1, display_name="오래된 수정")
    with pytest.raises(IntegrityViolation):
        data.add_role(
            p,
            c.id,
            Role(counterparty_id=value.id, role_code="CUSTOMER", effective_from=date(2026, 2, 1)),
            expected_version=2,
        )
    other = companies.create(
        p,
        company_name="다른 회사",
        business_number="9999999999",
        taxpayer_type="CORPORATION",
        opening_date=date(2026, 1, 1),
        address="테스트 주소",
    ).company
    with pytest.raises(ResourceNotFound):
        data.get_counterparty(p, other.id, value.id)
    with pytest.raises(ResourceNotFound):
        data.create_counterparty(p, replace(initial, id=uuid4(), company_id=other.id))
    assert (
        data.create_counterparty(
            p, replace(initial, id=uuid4(), company_id=other.id, payment_term_id=None)
        ).company_id
        == other.id
    )
    with MasterSQLAlchemyUnitOfWork(factory) as uow:
        assert uow.counterparties.match(c.id, "1234567890", "unknown")[0].id == value.id


@pytest.mark.parametrize("month", [1, 4, 7, 12])
def test_fiscal_month_generation(master, month):
    p, c, accounting, _, _, _ = master
    accounting.initialize(
        p, c.id, fiscal_year=2026, template_id=DEFAULT_TEMPLATE.id, fiscal_year_start_month=month
    )
    periods = accounting.periods(p, c.id)
    assert periods[0].start_date == date(2026, month, 1)
    assert len(periods) == 12
    assert all(
        (b.start_date - a.end_date).days == 1 for a, b in zip(periods, periods[1:], strict=False)
    )


def test_golden_counterparties(master):
    import csv
    from pathlib import Path

    p, c, _, data, _, _ = master
    fixture = Path(__file__).resolve().parents[1] / "golden" / "accounting_master.csv"
    with fixture.open(encoding="utf-8") as source:
        for row in csv.DictReader(source):
            value = Counterparty(
                company_id=c.id,
                display_name=row["display_name"],
                legal_name=row["legal_name"],
                normalized_legal_name="",
                business_number=row["business_number"],
            )
            saved = data.create_counterparty(
                p,
                value,
                roles=(
                    Role(
                        counterparty_id=value.id,
                        role_code=row["role_code"],
                        effective_from=date(2026, 1, 1),
                    ),
                ),
            )
            assert data.get_counterparty(p, c.id, saved.id)[1][0].role_code == row["role_code"]
    assert len(data.list_counterparties(p, c.id)) == 2


def test_period_overlap_and_account_constraints(master):
    from app.accounting.accounts.domain.entities import Account
    from app.accounting.periods.domain.entities import Period

    p, c, accounting, _, factory, _ = master
    accounting.initialize(p, c.id, fiscal_year=2026, template_id=DEFAULT_TEMPLATE.id)
    with pytest.raises(IntegrityViolation):
        with MasterSQLAlchemyUnitOfWork(factory) as uow:
            uow.periods.add(
                Period(
                    company_id=c.id,
                    fiscal_year=2027,
                    period_no=1,
                    start_date=date(2026, 1, 15),
                    end_date=date(2026, 2, 15),
                )
            )
    with pytest.raises(IntegrityViolation):
        with MasterSQLAlchemyUnitOfWork(factory) as uow:
            uow.accounts.add(
                Account(
                    company_id=c.id,
                    account_code="1010",
                    account_name="중복",
                    account_type="ASSET",
                    normal_balance="DEBIT",
                    posting_allowed=True,
                )
            )
    with pytest.raises(IntegrityViolation):
        with MasterSQLAlchemyUnitOfWork(factory) as uow:
            uow.accounts.add(
                Account(
                    company_id=c.id,
                    account_code="INVALID",
                    account_name="잘못된 방향",
                    account_type="ASSET",
                    normal_balance="CREDIT",
                    posting_allowed=True,
                )
            )


@pytest.mark.parametrize("kind", ["contact", "address", "bank", "version", "role"])
def test_counterparty_child_constraints(master, kind):
    p, c, _, data, factory, _ = master
    value = data.create_counterparty(
        p,
        Counterparty(
            company_id=c.id,
            display_name="제약 테스트",
            legal_name="제약 테스트",
            normalized_legal_name="",
        ),
    )
    with pytest.raises(IntegrityViolation):
        with MasterSQLAlchemyUnitOfWork(factory) as uow:
            if kind == "contact":
                for _ in range(2):
                    uow.counterparties.add_contact(
                        c.id,
                        Contact(
                            counterparty_id=value.id,
                            contact_type="BILLING",
                            contact_name="주 담당자",
                            is_primary=True,
                        ),
                    )
            elif kind == "address":
                for _ in range(2):
                    uow.counterparties.add_address(
                        c.id,
                        Address(
                            counterparty_id=value.id,
                            address_type="BILLING",
                            address_line1="주소",
                            is_primary=True,
                        ),
                    )
            elif kind == "bank":
                uow.counterparties.add_bank(
                    c.id,
                    BankReference(
                        counterparty_id=value.id,
                        bank_code="TEST",
                        account_alias="잘못된 원계좌",
                        external_token="1234567890",
                    ),
                )
            elif kind == "version":
                uow.counterparties.update(replace(value, version=0), 1)
            else:
                uow.counterparties.add_role(
                    c.id,
                    Role(
                        counterparty_id=value.id,
                        role_code="CUSTOMER",
                        effective_from=date(2026, 2, 1),
                        effective_to=date(2026, 1, 1),
                    ),
                )


def test_master_schema_policy_and_foreign_keys(master):
    from sqlalchemy import inspect, text

    from app.core.database.schema import assert_relational_schema

    p, c, accounting, _, factory, _ = master
    accounting.initialize(p, c.id, fiscal_year=2026, template_id=DEFAULT_TEMPLATE.id)
    with MasterSQLAlchemyUnitOfWork(factory) as uow:
        connection = uow.session.connection()
        assert_relational_schema(connection)
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema='public' AND data_type IN ('json','jsonb')"
                )
            )
            == 0
        )
        inspector = inspect(connection)
        for name in inspector.get_table_names(schema="public"):
            assert not (
                {"metadata", "extra", "options", "payload", "context"}
                & {column["name"] for column in inspector.get_columns(name)}
            )
            for fk in inspector.get_foreign_keys(name):
                assert fk["referred_table"] in inspector.get_table_names(schema="public")
                if "company_id" in fk["constrained_columns"]:
                    indexes = inspector.get_indexes(name)
                    assert any(index["column_names"][0] == "company_id" for index in indexes)
                local = fk["constrained_columns"]
                remote = fk["referred_columns"]
                clauses = " AND ".join(
                    f'a."{a}"=b."{b}"' for a, b in zip(local, remote, strict=True)
                )
                nonnull = " AND ".join(f'a."{column}" IS NOT NULL' for column in local)
                sql = (
                    f'SELECT count(*) FROM "{name}" a WHERE {nonnull} AND NOT EXISTS '
                    f'(SELECT 1 FROM "{fk["referred_table"]}" b WHERE {clauses})'
                )
                assert connection.scalar(text(sql)) == 0, (name, local)


@pytest.mark.parametrize(
    "changes",
    [
        {"functional_currency_code": "INVALID"},
        {"fiscal_year_start_month": 0},
        {"fiscal_year_start_month": 13},
        {"numbering_reset_policy": "INVALID"},
    ],
)
def test_invalid_initialization(master, changes):
    from app.contracts.access_errors import InvalidInput

    p, c, accounting, _, _, _ = master
    with pytest.raises(InvalidInput):
        accounting.initialize(p, c.id, fiscal_year=2026, template_id=DEFAULT_TEMPLATE.id, **changes)
    with pytest.raises(ResourceNotFound):
        accounting.settings(p, c.id)


def test_never_reset_and_company_accounts_isolation(master):
    p, c, accounting, _, factory, companies = master
    value = accounting.initialize(
        p, c.id, fiscal_year=2026, template_id=DEFAULT_TEMPLATE.id, numbering_reset_policy="NEVER"
    )
    assert value.numbering_reset_policy == "NEVER"
    with MasterSQLAlchemyUnitOfWork(factory) as uow:
        assert uow.sequences.allocate(c.id, 0, "JOURNAL") == 1
    other = companies.create(
        p,
        company_name="다른 회사",
        business_number="9999999999",
        taxpayer_type="CORPORATION",
        opening_date=date(2026, 1, 1),
        address="주소",
    ).company
    accounting.initialize(p, other.id, fiscal_year=2026, template_id=DEFAULT_TEMPLATE.id)
    first = accounting.accounts(p, c.id)
    second = accounting.accounts(p, other.id)
    assert {row.account_code for row in first} == {row.account_code for row in second}
    assert not ({row.id for row in first} & {row.id for row in second})
    period_id = accounting.periods(p, c.id)[0].id
    with MasterSQLAlchemyUnitOfWork(factory) as uow:
        assert uow.accounts.get(company_id=other.id, resource_id=first[0].id) is None
        assert uow.periods.get(company_id=other.id, resource_id=period_id) is None
