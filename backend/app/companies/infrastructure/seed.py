"""스키마 변경과 분리한 반복 실행 가능한 초기 권한 seed입니다."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.companies.domain.permissions import PERMISSION_GRANTS, ROLES
from app.companies.infrastructure.models import PermissionModel, RoleModel, RolePermissionModel
from app.core.config import load_settings
from app.core.database.engine import create_database_engine
from app.core.database.session import create_session_factory
from app.core.database.unit_of_work import SQLAlchemyUnitOfWork


def seed_permissions(session: Session) -> None:
    for code, name in ROLES.items():
        session.execute(insert(RoleModel).values(code=code, name=name).on_conflict_do_nothing())
    for code, roles in PERMISSION_GRANTS.items():
        session.execute(
            insert(PermissionModel).values(code=code, name=code).on_conflict_do_nothing()
        )
        for role in roles:
            session.execute(
                insert(RolePermissionModel)
                .values(role_code=role, permission_code=code)
                .on_conflict_do_nothing()
            )


def main() -> None:
    engine = create_database_engine(load_settings())
    try:
        with SQLAlchemyUnitOfWork(create_session_factory(engine)) as uow:
            seed_permissions(uow.session)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
