from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.accounting.settings.domain.entities import AccountingSettings
from app.accounting.settings.infrastructure.models import AccountingSettingsModel


class AccountingSettingsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, company_id: UUID) -> AccountingSettings | None:
        row = self.session.scalar(
            select(AccountingSettingsModel).where(AccountingSettingsModel.company_id == company_id)
        )
        return (
            None
            if row is None
            else AccountingSettings(
                **{k: getattr(row, k) for k in AccountingSettings.__dataclass_fields__}
            )
        )

    def add(self, value: AccountingSettings) -> None:
        self.session.add(AccountingSettingsModel(**asdict(value)))
        self.session.flush()

    def update(self, value: AccountingSettings, expected_version: int) -> bool:
        values = asdict(value)
        values.pop("id")
        values.pop("company_id")
        return (
            self.session.scalar(
                update(AccountingSettingsModel)
                .where(
                    AccountingSettingsModel.company_id == value.company_id,
                    AccountingSettingsModel.version == expected_version,
                )
                .values(**values)
                .returning(AccountingSettingsModel.id)
            )
            is not None
        )
