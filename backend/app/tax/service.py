from collections.abc import Callable
from datetime import date
from typing import TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel

from app.companies.application.service import require_company
from app.contracts.access_errors import InvalidInput, ResourceNotFound, StateConflict
from app.core.digests import digest
from app.identity.users.domain.entities import Principal
from app.tax.contracts import (
    Period,
    PeriodCreate,
    Preparation,
    Profile,
    ProfileCreate,
    Vat,
    VatCreate,
    Withholding,
    WithholdingCreate,
)
from app.tax.models import (
    TaxCommandModel,
    TaxPeriodModel,
    TaxProfileModel,
    VatModel,
    WithholdingModel,
)
from app.tax.rules import prepare, source_digest
from app.tax.unit_of_work import TaxUnitOfWork

R = TypeVar("R", bound=BaseModel)


class TaxService:
    def __init__(self, factory: Callable[[], TaxUnitOfWork]) -> None:
        self.factory = factory

    def profiles(self, actor: Principal, company: UUID) -> tuple[Profile, ...]:
        with self.factory() as uow:
            require_company(uow, actor, company, "tax.read")
            return uow.tax.profiles(company)

    def periods(self, actor: Principal, company: UUID) -> tuple[Period, ...]:
        with self.factory() as uow:
            require_company(uow, actor, company, "tax.read")
            return uow.tax.periods(company)

    def _command(
        self,
        actor: Principal,
        company: UUID,
        key: str,
        code: str,
        permission: str,
        payload: BaseModel,
        result_type: type[R],
        create: Callable[[TaxUnitOfWork], R],
    ) -> R:
        if not key.strip() or len(key) > 100:
            raise InvalidInput()
        fingerprint = digest(payload.model_dump(mode="json"))
        with self.factory() as uow:
            require_company(uow, actor, company, permission)
            uow.tax.lock(company)
            old = uow.tax.command(company, actor.user_id, code, key)
            models = {
                "profile": TaxProfileModel,
                "period": TaxPeriodModel,
                "vat": VatModel,
                "withholding": WithholdingModel,
            }
            if old:
                if old.fingerprint != fingerprint:
                    raise StateConflict()
                identifier = getattr(old, f"{code}_id")
                return result_type.model_validate(uow.tax.get(models[code], company, identifier))
            result = create(uow)
            uow.tax.add(
                TaxCommandModel(
                    id=uuid4(),
                    company_id=company,
                    actor_id=actor.user_id,
                    command_code=code,
                    idempotency_key=key,
                    fingerprint=fingerprint,
                    occurred_at=uow.now(),
                    **{f"{code}_id": result.id},  # type: ignore[attr-defined]
                )
            )
            return result

    def create_profile(
        self,
        actor: Principal,
        company: UUID,
        payload: ProfileCreate,
        key: str,
    ) -> Profile:
        def create(uow: TaxUnitOfWork) -> Profile:
            profiles = uow.tax.profiles(company)
            if any(
                p.effective_from <= (payload.effective_to or date.max)
                and payload.effective_from <= (p.effective_to or date.max)
                for p in profiles
            ):
                raise StateConflict()
            return Profile.model_validate(
                uow.tax.add(
                    TaxProfileModel(
                        id=uuid4(),
                        company_id=company,
                        version=len(profiles) + 1,
                        created_by=actor.user_id,
                        created_at=uow.now(),
                        **payload.model_dump(),
                    )
                )
            )

        return self._command(
            actor, company, key, "profile", "company.tax_profile.update", payload, Profile, create
        )

    def create_period(
        self,
        actor: Principal,
        company: UUID,
        payload: PeriodCreate,
        key: str,
    ) -> Period:
        def create(uow: TaxUnitOfWork) -> Period:
            if any(
                p.tax_type == payload.tax_type
                and p.period_start <= payload.period_end
                and payload.period_start <= p.period_end
                for p in uow.tax.periods(company)
            ):
                raise StateConflict()
            return Period.model_validate(
                uow.tax.add(
                    TaxPeriodModel(
                        id=uuid4(),
                        company_id=company,
                        created_by=actor.user_id,
                        created_at=uow.now(),
                        **payload.model_dump(),
                    )
                )
            )

        return self._command(
            actor, company, key, "period", "tax.filing.calculate", payload, Period, create
        )

    def record_vat(
        self,
        actor: Principal,
        company: UUID,
        period_id: UUID,
        payload: VatCreate,
        key: str,
    ) -> Vat:
        def create(uow: TaxUnitOfWork) -> Vat:
            transaction, revision = self._source(uow, company, period_id, payload, "VAT")
            if payload.supply_amount + payload.tax_amount != transaction.amount:
                raise InvalidInput()
            if transaction.direction == "INFLOW" and payload.deductible_status != "NOT_APPLICABLE":
                raise InvalidInput()
            return Vat.model_validate(
                uow.tax.add(
                    VatModel(
                        id=uuid4(),
                        company_id=company,
                        period_id=period_id,
                        revision=revision,
                        transaction_version=transaction.version,
                        source_digest=source_digest(transaction),
                        direction=transaction.direction,
                        created_by=actor.user_id,
                        created_at=uow.now(),
                        **payload.model_dump(),
                    )
                )
            )

        return self._command(
            actor,
            company,
            key,
            "vat",
            "tax.treatment.propose",
            _VatCommand(period_id=period_id, **payload.model_dump()),
            Vat,
            create,
        )

    def record_withholding(
        self,
        actor: Principal,
        company: UUID,
        period_id: UUID,
        payload: WithholdingCreate,
        key: str,
    ) -> Withholding:
        def create(uow: TaxUnitOfWork) -> Withholding:
            transaction, revision = self._source(uow, company, period_id, payload, "WITHHOLDING")
            net = payload.gross_amount - payload.withholding_tax - payload.local_tax
            if transaction.direction != "OUTFLOW" or net != transaction.amount:
                raise InvalidInput()
            if transaction.counterparty_id != payload.payee_id:
                raise InvalidInput()
            return Withholding.model_validate(
                uow.tax.add(
                    WithholdingModel(
                        id=uuid4(),
                        company_id=company,
                        period_id=period_id,
                        revision=revision,
                        transaction_version=transaction.version,
                        source_digest=source_digest(transaction),
                        payment_date=transaction.transaction_date,
                        net_amount=net,
                        created_by=actor.user_id,
                        created_at=uow.now(),
                        **payload.model_dump(),
                    )
                )
            )

        return self._command(
            actor,
            company,
            key,
            "withholding",
            "tax.treatment.propose",
            _WithholdingCommand(period_id=period_id, **payload.model_dump()),
            Withholding,
            create,
        )

    @staticmethod
    def _source(
        uow: TaxUnitOfWork,
        company: UUID,
        period_id: UUID,
        payload: VatCreate | WithholdingCreate,
        tax_type: str,
    ) -> tuple["Transaction", int]:
        period = uow.tax.get(TaxPeriodModel, company, period_id)
        transaction = uow.transactions.get(company, payload.transaction_id, lock=True)
        if period is None or transaction is None:
            raise ResourceNotFound()
        if (
            period.tax_type != tax_type
            or not period.period_start <= transaction.transaction_date <= period.period_end
            or transaction.status in ("EXCLUDED", "DUPLICATE_REVIEW")
        ):
            raise InvalidInput()
        if payload.evidence_id and not uow.reference_exists(
            company, "evidence", payload.evidence_id
        ):
            raise ResourceNotFound()
        vat, withholding = uow.tax.facts(company)
        old = next(
            (
                r
                for r in (vat if tax_type == "VAT" else withholding)
                if r.transaction_id == transaction.id
            ),
            None,
        )
        return transaction, old.revision + 1 if old else 1

    def preparation(self, actor: Principal, company: UUID, period_id: UUID) -> Preparation:
        with self.factory() as uow:
            require_company(uow, actor, company, "tax.read")
            uow.tax.lock(company)
            period = uow.tax.get(TaxPeriodModel, company, period_id)
            if period is None:
                raise ResourceNotFound()
            vat, withholding = uow.tax.facts(company)
            return prepare(
                Period.model_validate(period),
                uow.tax.profiles(company),
                vat,
                withholding,
                uow.tax.transactions(company, period.period_start, period.period_end),
            )


from app.accounting.transactions.domain.entities import Transaction  # noqa: E402


class _VatCommand(VatCreate):
    period_id: UUID


class _WithholdingCommand(WithholdingCreate):
    period_id: UUID
