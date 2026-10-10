"""안정적인 거래처 코드로만 식별하며 이름 유사도로 덮어쓰지 않습니다."""

from dataclasses import replace

from app.accounting.application.contracts import MasterUnitOfWork
from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, StateConflict
from app.identity.users.domain.entities import Principal
from app.master_data.counterparties.domain.entities import Counterparty
from app.master_data.domain.rules import CounterpartyType, normalized_identifier, normalized_name


def promote_counterparties(
    uow: MasterUnitOfWork, actor: Principal, values: list[Counterparty]
) -> int:
    count = 0
    for value in values:
        require_company(uow, actor, value.company_id, "counterparty.create")
        if value.counterparty_type not in CounterpartyType or not value.counterparty_code:
            raise InvalidInput()
        value = replace(
            value,
            business_number=normalized_identifier(value.business_number, 10),
            normalized_legal_name=normalized_name(value.legal_name),
        )
        existing = next(
            (
                c
                for c in uow.counterparties.list(value.company_id)
                if c.counterparty_code == value.counterparty_code
            ),
            None,
        )
        if existing:
            if any(
                getattr(existing, key) != getattr(value, key)
                for key in ("legal_name", "business_number", "counterparty_type", "payment_term_id")
            ):
                raise StateConflict()
            continue
        if (
            value.payment_term_id
            and uow.payment_terms.get(
                company_id=value.company_id, resource_id=value.payment_term_id
            )
            is None
        ):
            raise InvalidInput()
        uow.counterparties.add(value)
        count += 1
    return count
