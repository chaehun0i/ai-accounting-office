import inspect
from uuid import UUID

from app.contracts.repository import CompanyScopedRepository
from app.contracts.unit_of_work import UnitOfWork


def test_repository_requires_explicit_company_scope() -> None:
    signature = inspect.signature(CompanyScopedRepository.get)
    for name in ("company_id", "resource_id"):
        parameter = signature.parameters[name]
        assert parameter.kind == inspect.Parameter.KEYWORD_ONLY
        assert parameter.default == inspect.Parameter.empty
        assert parameter.annotation is UUID
    assert not hasattr(CompanyScopedRepository, "commit")
    assert not hasattr(CompanyScopedRepository, "get_by_id")


def test_application_uow_does_not_expose_session() -> None:
    assert not hasattr(UnitOfWork, "session")
