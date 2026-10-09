import builtins
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounting.templates.domain.entities import Template, TemplateAccount
from app.accounting.templates.infrastructure.models import COATemplateAccountModel, COATemplateModel


class TemplateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> builtins.list[Template]:
        return [
            Template(**{k: getattr(row, k) for k in Template.__dataclass_fields__})
            for row in self.session.scalars(
                select(COATemplateModel)
                .where(COATemplateModel.status == "ACTIVE")
                .order_by(COATemplateModel.template_code, COATemplateModel.version)
            )
        ]

    def accounts(self, template_id: UUID) -> builtins.list[TemplateAccount]:
        return [
            TemplateAccount(**{k: getattr(row, k) for k in TemplateAccount.__dataclass_fields__})
            for row in self.session.scalars(
                select(COATemplateAccountModel)
                .where(COATemplateAccountModel.coa_template_id == template_id)
                .order_by(
                    COATemplateAccountModel.display_order, COATemplateAccountModel.account_code
                )
            )
        ]
