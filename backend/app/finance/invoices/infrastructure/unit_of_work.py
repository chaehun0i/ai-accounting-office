from typing import Self

from app.finance.invoices.infrastructure.repository import DocumentRepository
from app.finance.settlements.infrastructure.unit_of_work import FinanceSQLAlchemyUnitOfWork


class DocumentSQLAlchemyUnitOfWork(FinanceSQLAlchemyUnitOfWork):
    documents: DocumentRepository

    def __enter__(self) -> Self:
        super().__enter__()
        self.documents = DocumentRepository(self.session)
        return self
