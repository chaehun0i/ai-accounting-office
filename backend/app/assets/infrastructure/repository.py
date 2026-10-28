from dataclasses import asdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounting.journals.domain.errors import AccountingError
from app.accounting.journals.infrastructure.models import JournalModel
from app.accounting.periods.infrastructure.models import PeriodModel
from app.assets.domain.entities import AssetPolicy, DepreciationLine, DepreciationRun, FixedAsset
from app.assets.infrastructure.models import (
    AssetPolicyModel,
    DepreciationLineModel,
    DepreciationRunModel,
    FixedAssetModel,
)


class AssetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def policies(self, company: UUID) -> list[AssetPolicy]:
        rows = self.session.scalars(select(AssetPolicyModel).where(
            AssetPolicyModel.company_id == company
        ).order_by(AssetPolicyModel.version))
        return [AssetPolicy(**{k: getattr(r, k) for k in AssetPolicy.__dataclass_fields__}) for r in rows]

    def list(self, company: UUID) -> list[FixedAsset]:
        rows = self.session.scalars(select(FixedAssetModel).where(
            FixedAssetModel.company_id == company
        ).order_by(FixedAssetModel.asset_code))
        return [FixedAsset(**{k: getattr(r, k) for k in FixedAsset.__dataclass_fields__}) for r in rows]

    def get(self, company: UUID, resource: UUID) -> FixedAsset | None:
        row = self.session.scalar(select(FixedAssetModel).where(
            FixedAssetModel.company_id == company, FixedAssetModel.id == resource
        ))
        return FixedAsset(**{k: getattr(row, k) for k in FixedAsset.__dataclass_fields__}) if row else None

    def add_policy(self, value: AssetPolicy) -> None:
        self.session.add(AssetPolicyModel(**asdict(value)))
        self.session.flush()

    def add_asset(self, value: FixedAsset) -> None:
        self.session.add(FixedAssetModel(**asdict(value)))
        self.session.flush()

    def run(self, company: UUID, period: UUID) -> DepreciationRun | None:
        row = self.session.scalar(select(DepreciationRunModel).where(
            DepreciationRunModel.company_id == company, DepreciationRunModel.period_id == period
        ))
        return self._run(row) if row else None

    def get_run(self, company: UUID, resource: UUID) -> DepreciationRun | None:
        row = self.session.scalar(select(DepreciationRunModel).where(
            DepreciationRunModel.company_id == company, DepreciationRunModel.id == resource
        ))
        return self._run(row) if row else None

    def _run(self, row: DepreciationRunModel) -> DepreciationRun:
        rows = self.session.scalars(select(DepreciationLineModel).where(
            DepreciationLineModel.company_id == row.company_id,
            DepreciationLineModel.depreciation_run_id == row.id,
        ).order_by(DepreciationLineModel.fixed_asset_id))
        return DepreciationRun(
            **{k: getattr(row, k) for k in DepreciationRun.__dataclass_fields__ if k != "lines"},
            lines=tuple(DepreciationLine(**{k: getattr(r, k) for k in DepreciationLine.__dataclass_fields__}) for r in rows),
        )

    def latest_run_date(self, company: UUID) -> date | None:
        return self.session.scalar(select(func.max(PeriodModel.end_date)).join(
            DepreciationRunModel, DepreciationRunModel.period_id == PeriodModel.id
        ).where(DepreciationRunModel.company_id == company))

    def is_reversed(self, company: UUID, journal: UUID) -> bool:
        return self.session.scalar(select(JournalModel.id).where(
            JournalModel.company_id == company, JournalModel.reversal_of_id == journal,
            JournalModel.status == "POSTED"
        )) is not None

    def opening(self, company: UUID, asset: UUID, before: date) -> Decimal:
        rows = self.session.execute(select(DepreciationLineModel, JournalModel.status).join(
            DepreciationRunModel, DepreciationRunModel.id == DepreciationLineModel.depreciation_run_id
        ).join(PeriodModel, PeriodModel.id == DepreciationRunModel.period_id).outerjoin(
            JournalModel, JournalModel.id == DepreciationLineModel.proposed_journal_id
        ).where(DepreciationLineModel.company_id == company,
                DepreciationLineModel.fixed_asset_id == asset, PeriodModel.end_date < before))
        total = Decimal(0)
        for line, status in rows:
            if line.proposed_journal_id and (
                status != "POSTED" or self.is_reversed(company, line.proposed_journal_id)
            ):
                raise AccountingError("ASSET_PRIOR_RUN_UNSETTLED", "이전 감가상각 전표를 확정·대사해 주세요.", 409)
            total += line.current_depreciation
        return total

    def add_run(self, value: DepreciationRun) -> None:
        data = asdict(value)
        data.pop("lines")
        self.session.add(DepreciationRunModel(**data))
        self.session.flush()
        self.session.add_all(DepreciationLineModel(**asdict(line)) for line in value.lines)
        self.session.flush()
