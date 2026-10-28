import calendar
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from app.accounting.journals.application.service import validate_journal
from app.accounting.journals.domain.entities import Journal, JournalLine
from app.accounting.journals.domain.errors import AccountingError
from app.assets.application.contracts import AssetUnitOfWork
from app.assets.domain.entities import AssetPolicy, DepreciationLine, DepreciationRun, FixedAsset
from app.assets.domain.rules import cumulative_depreciation, money, validate_asset
from app.companies.application.service import require_company
from app.contracts.access_errors import ResourceNotFound, StateConflict
from app.identity.users.domain.entities import Principal


class AssetService:
    def __init__(self, factory: Callable[[], AssetUnitOfWork]) -> None:
        self.factory = factory

    def policies(self, actor: Principal, company: UUID) -> list[AssetPolicy]:
        with self.factory() as uow:
            require_company(uow, actor, company, "asset.read")
            return uow.assets.policies(company)

    def create_policy(
        self, actor: Principal, company: UUID, *, effective_from: date,
        proration: str, acquisition_month: str,
    ) -> AssetPolicy:
        if effective_from.day != 1 or proration not in ("MONTHLY", "DAILY") or acquisition_month not in (
            "FULL", "NEXT_MONTH"
        ):
            raise AccountingError("ASSET_POLICY_INVALID", "월초부터 적용할 상각정책을 확인해 주세요.")
        with self.factory() as uow:
            require_company(uow, actor, company, "asset.policy.manage")
            uow.dimensions.lock_scope(company)
            policies = uow.assets.policies(company)
            latest = uow.assets.latest_run_date(company)
            if (policies and effective_from <= policies[-1].effective_from) or (
                latest and effective_from <= latest
            ):
                raise StateConflict()
            value = AssetPolicy(
                id=uuid4(), company_id=company, version=len(policies) + 1,
                effective_from=effective_from, proration=proration,
                acquisition_month=acquisition_month, created_by=actor.user_id,
                created_at=uow.now(),
            )
            uow.assets.add_policy(value)
            return value

    def list_assets(self, actor: Principal, company: UUID) -> list[FixedAsset]:
        with self.factory() as uow:
            require_company(uow, actor, company, "asset.read")
            return uow.assets.list(company)

    def register(self, actor: Principal, value: FixedAsset) -> FixedAsset:
        validate_asset(value)
        with self.factory() as uow:
            require_company(uow, actor, value.company_id, "asset.register")
            # Period -> accounts -> company uses the same order as Journal posting.
            acquisition = uow.journals.get(value.company_id, value.acquisition_journal_id)
            if acquisition is None:
                raise ResourceNotFound()
            uow.lock_period(value.company_id, acquisition.accounting_period_id)
            uow.lock_accounts(value.company_id, (
                value.asset_account_id, value.accumulated_account_id, value.expense_account_id
            ))
            uow.dimensions.lock_scope(value.company_id)
            latest = uow.assets.latest_run_date(value.company_id)
            if latest and value.in_service_date <= latest:
                raise AccountingError("ASSET_HISTORY_LOCKED", "이미 계산한 상각기간 이후의 자산만 등록할 수 있습니다.", 409)
            if acquisition.status != "POSTED" or uow.assets.is_reversed(
                value.company_id, acquisition.id
            ):
                raise AccountingError("ASSET_ACQUISITION_NOT_POSTED", "확정된 취득 전표가 필요합니다.", 409)
            asset_amount = sum((
                line.debit_amount - line.credit_amount for line in acquisition.lines
                if line.account_id == value.asset_account_id
            ), Decimal(0))
            if acquisition.entry_date != value.acquisition_date or asset_amount != value.acquisition_cost:
                raise AccountingError("ASSET_ACQUISITION_MISMATCH", "취득일과 자산계정 금액이 전표와 다릅니다.")
            for resource, kind in (
                (value.asset_account_id, "ASSET"), (value.accumulated_account_id, "ASSET"),
                (value.expense_account_id, "EXPENSE"),
            ):
                account = uow.accounts.get(company_id=value.company_id, resource_id=resource)
                if account is None:
                    raise ResourceNotFound()
                if account.account_type != kind or account.status != "ACTIVE" or not account.posting_allowed:
                    raise AccountingError("ASSET_ACCOUNT_INVALID", "자산·누계액·비용 계정 구분을 확인해 주세요.")
            uow.assets.add_asset(value)
            return value

    def get_run(self, actor: Principal, company: UUID, resource: UUID) -> DepreciationRun:
        with self.factory() as uow:
            require_company(uow, actor, company, "asset.read")
            value = uow.assets.get_run(company, resource)
            if value is None:
                raise ResourceNotFound()
            return value

    def calculate(self, actor: Principal, company: UUID, period_id: UUID) -> DepreciationRun:
        with self.factory() as uow:
            require_company(uow, actor, company, "asset.depreciation.calculate")
            require_company(uow, actor, company, "journal.propose")
            uow.lock_period(company, period_id)
            period = uow.periods.get(company_id=company, resource_id=period_id)
            if period is None:
                raise ResourceNotFound()
            # Lock all posting accounts before company scope, including on a replay.
            assets = uow.assets.list(company)
            uow.lock_accounts(company, tuple(
                account for asset in assets
                for account in (asset.expense_account_id, asset.accumulated_account_id)
            ))
            uow.dimensions.lock_scope(company)
            replay = uow.assets.run(company, period_id)
            if replay:
                return replay
            if period.status != "OPEN":
                raise AccountingError("PERIOD_NOT_OPEN", "열린 회계기간에만 상각을 계산할 수 있습니다.", 409)
            if period.start_date != date(period.end_date.year, period.end_date.month, 1) or (
                period.end_date.day != calendar.monthrange(period.end_date.year, period.end_date.month)[1]
            ):
                raise AccountingError("ASSET_PERIOD_INVALID", "감가상각은 완전한 달력 월 단위로 계산합니다.")
            latest = uow.assets.latest_run_date(company)
            if latest and latest >= period.start_date:
                raise StateConflict()
            policies = [p for p in uow.assets.policies(company) if p.effective_from <= period.start_date]
            if not policies:
                raise AccountingError("ASSET_POLICY_REQUIRED", "기간에 적용되는 상각정책을 먼저 등록해 주세요.")
            policy = policies[-1]
            run_id = uuid4()
            lines = []
            now = uow.now()
            # Re-read after scope lock so concurrent registrations cannot be omitted.
            assets = uow.assets.list(company)
            for asset in assets:
                if asset.status != "IN_SERVICE" or asset.in_service_date > period.end_date:
                    continue
                if uow.assets.is_reversed(company, asset.acquisition_journal_id):
                    raise AccountingError("ASSET_SOURCE_REVERSED", "취득 전표의 역분개를 먼저 대사해 주세요.", 409)
                opening = uow.assets.opening(company, asset.id, period.start_date)
                target = cumulative_depreciation(asset, policy, period.end_date)
                amount = max(Decimal(0), target - opening)
                journal_id = uuid4() if amount else None
                line = DepreciationLine(
                    id=uuid4(), company_id=company, depreciation_run_id=run_id,
                    fixed_asset_id=asset.id, opening_accumulated=opening,
                    current_depreciation=amount, closing_accumulated=opening + amount,
                    carrying_amount=asset.acquisition_cost - opening - amount,
                    proposed_journal_id=journal_id,
                )
                if journal_id:
                    journal = Journal(
                        id=journal_id, company_id=company, accounting_period_id=period_id,
                        entry_date=period.end_date, description=f"감가상각 {asset.asset_code}",
                        source_type="ASSET", proposal_origin="DETERMINISTIC", status="DRAFT",
                        version=1, created_by=actor.user_id, created_at=now, updated_at=now,
                        lines=(
                            JournalLine(id=uuid4(), line_no=1, account_id=asset.expense_account_id,
                                        debit_amount=amount, credit_amount=Decimal(0)),
                            JournalLine(id=uuid4(), line_no=2, account_id=asset.accumulated_account_id,
                                        debit_amount=Decimal(0), credit_amount=amount),
                        ),
                    )
                    validate_journal(uow, journal, balanced=False)
                    uow.journals.add(journal)
                lines.append(line)
            total = money(sum((line.current_depreciation for line in lines), Decimal(0)))
            value = DepreciationRun(
                id=run_id, company_id=company, period_id=period_id, policy_id=policy.id,
                policy_version=policy.version, status="CALCULATED", total_amount=total,
                created_by=actor.user_id, created_at=now, lines=tuple(lines),
            )
            uow.assets.add_run(value)
            return value
