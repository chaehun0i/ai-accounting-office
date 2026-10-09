from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Column, Connection, MetaData, Table, select
from sqlalchemy.schema import CreateTable

from app.contracts.errors import InvalidPersistenceValue
from app.core.database.session import create_session_factory
from app.core.database.types import MoneyNumeric, ResourceUUID, UTCDateTime
from app.core.database.unit_of_work import SQLAlchemyUnitOfWork
from app.core.values import new_uuid


@pytest.mark.parametrize(
    "amount",
    [Decimal("0"), Decimal("0.0001"), Decimal("-12.3400"), Decimal("999999999999999.9999")],
)
def test_uuid_decimal_and_timestamp_round_trip(db_connection: Connection, amount: Decimal) -> None:
    table = Table(
        "typed_probe",
        MetaData(),
        Column("id", ResourceUUID(), primary_key=True),
        Column("amount", MoneyNumeric(), nullable=False),
        Column("occurred_at", UTCDateTime(), nullable=False),
        prefixes=["TEMPORARY"],
    )
    db_connection.execute(CreateTable(table))
    db_connection.commit()
    identity = new_uuid()
    occurred_at = datetime(2026, 10, 9, 22, 0, tzinfo=timezone(timedelta(hours=9)))
    with SQLAlchemyUnitOfWork(create_session_factory(db_connection)) as uow:
        uow.session.execute(
            table.insert().values(id=identity, amount=amount, occurred_at=occurred_at)
        )
    row = db_connection.execute(select(table)).one()
    assert row.id == identity
    assert type(row.id) is type(identity)
    assert row.amount == amount
    assert isinstance(row.amount, Decimal)
    assert row.occurred_at == occurred_at.astimezone(UTC)
    assert row.occurred_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("value", [0.1, Decimal("0.00001"), Decimal("NaN")])
def test_invalid_money_cannot_cross_persistence_boundary(
    db_connection: Connection,
    value: object,
) -> None:
    table = Table(
        "invalid_probe", MetaData(), Column("amount", MoneyNumeric()), prefixes=["TEMPORARY"]
    )
    db_connection.execute(CreateTable(table))
    db_connection.commit()
    with pytest.raises(InvalidPersistenceValue):
        with SQLAlchemyUnitOfWork(create_session_factory(db_connection)) as uow:
            uow.session.execute(table.insert().values(amount=value))
