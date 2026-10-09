from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select

from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork
from app.accounting.sequences.infrastructure.models import JournalSequenceModel
from app.companies.infrastructure.models import CompanyModel, TenantModel
from app.core.database.session import create_session_factory


def test_sequence_concurrency_isolation_and_rollback(identity_database):
    engine = identity_database
    factory = create_session_factory(engine)
    tenant = uuid4()
    companies = [uuid4(), uuid4()]
    with engine.begin() as connection:
        connection.execute(insert(TenantModel).values(id=tenant, name="번호 동시성 테스트"))
        for index, company in enumerate(companies):
            connection.execute(
                insert(CompanyModel).values(
                    id=company,
                    tenant_id=tenant,
                    company_name=f"번호 테스트 {index}",
                    business_number=f"900000000{index}",
                    taxpayer_type="CORPORATION",
                    opening_date=date(2026, 1, 1),
                    address="테스트 주소",
                )
            )
    try:
        barrier = Barrier(8)

        def allocate(index):
            barrier.wait(timeout=20)
            with MasterSQLAlchemyUnitOfWork(factory) as uow:
                return uow.sequences.allocate(companies[0], 2026, "JOURNAL")

        with ThreadPoolExecutor(max_workers=8) as executor:
            values = list(executor.map(allocate, range(8)))
        assert sorted(values) == list(range(1, 9))
        with pytest.raises(RuntimeError):
            with MasterSQLAlchemyUnitOfWork(factory) as uow:
                assert uow.sequences.allocate(companies[0], 2026, "JOURNAL") == 9
                raise RuntimeError("테스트 롤백")
        with MasterSQLAlchemyUnitOfWork(factory) as uow:
            assert uow.sequences.allocate(companies[0], 2026, "JOURNAL") == 9
            assert uow.sequences.allocate(companies[1], 2026, "JOURNAL") == 1
            assert uow.sequences.allocate(companies[0], 2027, "JOURNAL") == 1
            assert uow.sequences.allocate(companies[0], 2026, "OTHER") == 1
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    select(JournalSequenceModel.last_number).where(
                        JournalSequenceModel.company_id == companies[0],
                        JournalSequenceModel.fiscal_year == 2026,
                        JournalSequenceModel.sequence_key == "JOURNAL",
                    )
                )
                == 9
            )
    finally:
        # 이 테스트가 만든 UUID 범위만 정리하며 다른 회사 데이터는 건드리지 않습니다.
        with engine.begin() as connection:
            connection.execute(
                delete(JournalSequenceModel).where(JournalSequenceModel.company_id.in_(companies))
            )
            connection.execute(delete(CompanyModel).where(CompanyModel.id.in_(companies)))
            connection.execute(delete(TenantModel).where(TenantModel.id == tenant))
