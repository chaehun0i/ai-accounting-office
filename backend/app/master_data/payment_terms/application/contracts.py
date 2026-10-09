from typing import Protocol
from uuid import UUID

from app.master_data.payment_terms.domain.entities import PaymentTerm


class PaymentTerms(Protocol):
    def get(self, *, company_id: UUID, resource_id: UUID) -> PaymentTerm | None: ...
    def list(self, company_id: UUID) -> list[PaymentTerm]: ...
    def add(self, value: PaymentTerm) -> None: ...
