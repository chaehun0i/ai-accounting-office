"""스키마 변경과 분리된 재실행 가능한 시드입니다. 호출자가 트랜잭션을 소유합니다."""

from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.accounting.domain.rules import validate_account, validate_hierarchy
from app.accounting.templates.domain.defaults import DEFAULT_ACCOUNTS, DEFAULT_TEMPLATE
from app.accounting.templates.infrastructure.models import COATemplateAccountModel, COATemplateModel
from app.contracts.access_errors import StateConflict


def seed_default_coa(session: Session) -> None:
    validate_hierarchy({row.account_code: row.parent_code for row in DEFAULT_ACCOUNTS})
    session.execute(
        insert(COATemplateModel)
        .values(**asdict(DEFAULT_TEMPLATE))
        .on_conflict_do_nothing(index_elements=["template_code", "version"])
    )
    actual = session.scalar(
        select(COATemplateModel).where(
            COATemplateModel.template_code == DEFAULT_TEMPLATE.template_code,
            COATemplateModel.version == DEFAULT_TEMPLATE.version,
        )
    )
    if actual is None or any(getattr(actual, k) != v for k, v in asdict(DEFAULT_TEMPLATE).items()):
        raise StateConflict()
    for row in DEFAULT_ACCOUNTS:
        validate_account(row.account_type, row.normal_balance, row.is_contra)
        session.execute(
            insert(COATemplateAccountModel)
            .values(**asdict(row))
            .on_conflict_do_nothing(index_elements=["coa_template_id", "account_code"])
        )
        saved = session.scalar(
            select(COATemplateAccountModel).where(
                COATemplateAccountModel.coa_template_id == row.coa_template_id,
                COATemplateAccountModel.account_code == row.account_code,
            )
        )
        if saved is None or any(getattr(saved, k) != v for k, v in asdict(row).items()):
            raise StateConflict()


def main() -> None:
    from app.accounting.application.catalog import prepare_accounts
    from app.accounting.infrastructure.unit_of_work import MasterSQLAlchemyUnitOfWork
    from app.companies.infrastructure.models import CompanyModel
    from app.core.config import load_settings
    from app.core.database.engine import create_database_engine
    from app.core.database.session import create_session_factory

    engine = create_database_engine(load_settings())
    try:
        with MasterSQLAlchemyUnitOfWork(create_session_factory(engine)) as uow:
            seed_default_coa(uow.session)
            # 회사 행 잠금으로 초기 생성·보충 작업의 중복 삽입을 방지합니다.
            for company in uow.session.scalars(select(CompanyModel).with_for_update()):
                prepare_accounts(uow, company.id)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
