"""Insert once and read frozen values without recalculating a historical snapshot."""

import json
from dataclasses import asdict, fields
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounting.journals.infrastructure.models import JournalEvidenceModel, JournalModel
from app.accounting.ledger.domain.entities import LedgerFact
from app.contracts.access_errors import ResourceNotFound
from app.core.digests import digest
from app.reporting.cash_flow.entities import CashEvent, CashPreflight
from app.reporting.cash_flow.indirect import IndirectBridge
from app.reporting.cash_flow.repository import CashFlowRepository
from app.reporting.cash_flow.snapshot import (
    CashBalanceSource,
    CashDrilldown,
    CashLine,
    CashSource,
    CashStatement,
    FrozenAdjustment,
    FrozenEvent,
    JournalTrace,
)
from app.reporting.cash_flow.snapshot_models import (
    CashFlowAdjustmentModel as AdjustmentModel,
)
from app.reporting.cash_flow.snapshot_models import (
    CashFlowAdjustmentSourceModel as SourceModel,
)
from app.reporting.cash_flow.snapshot_models import CashFlowBalanceSourceModel as BalanceModel
from app.reporting.cash_flow.snapshot_models import CashFlowCommandModel as CommandModel
from app.reporting.cash_flow.snapshot_models import (
    CashFlowEventModel as EventModel,
)
from app.reporting.cash_flow.snapshot_models import (
    CashFlowEvidenceTraceModel as EvidenceModel,
)
from app.reporting.cash_flow.snapshot_models import (
    CashFlowJournalTraceModel as TraceModel,
)
from app.reporting.cash_flow.snapshot_models import (
    CashFlowLineModel as LineModel,
)
from app.reporting.cash_flow.snapshot_models import (
    CashFlowStatementModel as SnapshotModel,
)
from app.reporting.financial_statements.domain.rules import ReportIdempotencyConflict


def view[T](kind: type[T], row: Any) -> T:
    return kind(**{f.name: getattr(row, f.name) for f in fields(kind)})  # type: ignore[arg-type]


class CashSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, company: UUID, statement_id: UUID) -> CashStatement:
        row = self.session.scalar(
            select(SnapshotModel).where(
                SnapshotModel.company_id == company, SnapshotModel.id == statement_id
            )
        )
        if row is None:
            raise ResourceNotFound()
        return view(CashStatement, row)

    def by_digest(self, company: UUID, period_id: UUID, snapshot_digest: str) -> CashStatement:
        row = self.session.scalar(
            select(SnapshotModel).where(
                SnapshotModel.company_id == company,
                SnapshotModel.period_id == period_id,
                SnapshotModel.snapshot_digest == snapshot_digest,
            )
        )
        if row is None:
            raise ResourceNotFound()
        return view(CashStatement, row)

    def replay(
        self, company: UUID, actor: UUID, key: str, fingerprint: str
    ) -> CashStatement | None:
        row = self.session.scalar(
            select(CommandModel).where(
                CommandModel.company_id == company,
                CommandModel.actor_id == actor,
                CommandModel.idempotency_key == key,
            )
        )
        if row is not None and row.fingerprint != fingerprint:
            raise ReportIdempotencyConflict()
        return self.get(company, row.statement_id) if row else None

    def record(
        self,
        company: UUID,
        actor: UUID,
        key: str,
        fingerprint: str,
        statement_id: UUID,
        now: datetime,
    ) -> None:
        self.session.add(
            CommandModel(
                id=uuid4(),
                company_id=company,
                actor_id=actor,
                idempotency_key=key,
                fingerprint=fingerprint,
                statement_id=statement_id,
                created_at=now,
            )
        )
        self.session.flush()

    def current(self, company: UUID, period_id: UUID) -> CashStatement:
        row = self.session.scalar(
            select(SnapshotModel)
            .where(SnapshotModel.company_id == company, SnapshotModel.period_id == period_id)
            .order_by(SnapshotModel.generated_at.desc(), SnapshotModel.id)
            .limit(1)
        )
        if row is None:
            raise ResourceNotFound()
        return view(CashStatement, row)

    def add(
        self,
        company: UUID,
        actor: UUID,
        now: datetime,
        preflight: CashPreflight,
        bridge: IndirectBridge,
        events: tuple[CashEvent, ...],
        statements: tuple[tuple[UUID, str], tuple[UUID, str]],
        facts: list[LedgerFact],
        period_start: date,
    ) -> CashStatement:
        existing = self.session.scalar(
            select(SnapshotModel).where(
                SnapshotModel.company_id == company,
                SnapshotModel.statement_set_id == bridge.statement_set_id,
                SnapshotModel.mapping_digest == bridge.mapping_digest,
            )
        )
        if existing is not None:
            return view(CashStatement, existing)
        # Digest covers values/provenance, never random row IDs or wall-clock time.
        repository = CashFlowRepository(self.session)
        scopes = {r.account_id: r for r in repository.scopes(company)}
        balances = tuple(
            CashBalanceSource(
                scopes[f.account_id].id,
                scopes[f.account_id].version,
                f.account_id,
                f.journal_id,
                f.line_id,
                f.entry_date,
                f.debit_amount - f.credit_amount,
                f.entry_date < period_start or f.source_type == "OPENING",
            )
            for f in sorted(facts, key=lambda f: (f.entry_date, str(f.line_id)))
            if f.account_id in scopes
        )
        classes = {row.id: row for row in repository.classifications(company)}
        allocations = {
            (row.journal_id, row.cash_line_id, row.counterpart_line_id): row
            for row in repository.allocations(company)
        }
        frozen_events = []
        for event in events:
            allocation = allocations.get(
                (event.journal_id, event.cash_line_id, event.counterpart_line_id)
            )
            frozen_events.append(
                FrozenEvent(
                    **asdict(event),
                    id=uuid4(),
                    classification_version=classes[event.classification_id].version,
                    allocation_id=allocation.id if allocation else None,
                    allocation_version=allocation.version if allocation else None,
                )
            )
        journal_ids = (
            {e.journal_id for e in events}
            | {source.journal_id for a in bridge.adjustments for source in a.sources}
            | {s.journal_id for s in balances}
        )
        traces = []
        for journal_id in sorted(journal_ids, key=str):
            journal = self.session.scalar(
                select(JournalModel).where(
                    JournalModel.company_id == company, JournalModel.id == journal_id
                )
            )
            if journal is None:
                raise ResourceNotFound()
            evidence = tuple(
                self.session.scalars(
                    select(JournalEvidenceModel.evidence_id)
                    .where(
                        JournalEvidenceModel.company_id == company,
                        JournalEvidenceModel.journal_entry_id == journal_id,
                    )
                    .order_by(JournalEvidenceModel.evidence_id)
                )
            )
            traces.append(JournalTrace(journal_id, journal.source_transaction_id, evidence))
        row = SnapshotModel(
            id=uuid4(),
            company_id=company,
            period_id=bridge.period_id,
            statement_set_id=bridge.statement_set_id,
            balance_sheet_id=statements[0][0],
            balance_sheet_digest=statements[0][1],
            income_statement_id=statements[1][0],
            income_statement_digest=statements[1][1],
            close_version=bridge.close_version,
            source_digest=bridge.source_digest,
            mapping_digest=bridge.mapping_digest,
            direct_mapping_digest=preflight.mapping_digest,
            snapshot_digest=digest(
                json.loads(
                    json.dumps(
                        (
                            asdict(preflight),
                            asdict(bridge),
                            statements,
                            [
                                {k: v for k, v in asdict(e).items() if k != "id"}
                                for e in frozen_events
                            ],
                            [asdict(t) for t in traces],
                            [asdict(s) for s in balances],
                        ),
                        default=str,
                    )
                )
            ),
            policy_code=bridge.policy_code,
            policy_version=bridge.policy_version,
            method="INDIRECT",
            status="RECONCILED",
            opening_cash=preflight.opening_cash,
            closing_cash=preflight.closing_cash,
            net_profit=bridge.net_profit,
            net_operating=bridge.net_operating,
            net_investing=preflight.net_investing,
            net_financing=preflight.net_financing,
            exchange_effect=preflight.exchange_effect,
            generated_by=actor,
            generated_at=now,
        )
        self.session.add(row)
        self.session.flush()
        self.session.add_all(
            [
                BalanceModel(id=uuid4(), company_id=company, statement_id=row.id, **asdict(source))
                for source in balances
            ]
        )
        lines: list[LineModel] = []

        def line(
            code: str,
            amount: Any,
            source_type: str = "TOTAL",
            *,
            event_id: UUID | None = None,
            adjustment_id: UUID | None = None,
        ) -> None:
            lines.append(
                LineModel(
                    id=uuid4(),
                    company_id=company,
                    statement_id=row.id,
                    line_code=code,
                    amount=amount,
                    source_type=source_type,
                    event_id=event_id,
                    adjustment_id=adjustment_id,
                    display_order=len(lines) + 1,
                )
            )

        line("OPENING_CASH", row.opening_cash)
        line("NET_PROFIT", row.net_profit, "NET_PROFIT")
        for adjustment in bridge.adjustments:
            adjusted = AdjustmentModel(
                id=uuid4(),
                company_id=company,
                statement_id=row.id,
                **{k: v for k, v in asdict(adjustment).items() if k != "sources"},
            )
            self.session.add(adjusted)
            self.session.flush()
            self.session.add_all(
                [
                    SourceModel(
                        id=uuid4(), company_id=company, adjustment_id=adjusted.id, **asdict(source)
                    )
                    for source in adjustment.sources
                ]
            )
            # Zero-valued operating-result/excluded rules retain provenance in drilldown.
            line(
                adjustment.adjustment_code,
                adjustment.amount,
                "ADJUSTMENT",
                adjustment_id=adjusted.id,
            )
        line("NET_OPERATING", row.net_operating)
        for event in frozen_events:
            self.session.add(EventModel(company_id=company, statement_id=row.id, **asdict(event)))
            if event.activity_type != "OPERATING":
                line(
                    event.line_code,
                    event.cash_inflow - event.cash_outflow,
                    "EVENT",
                    event_id=event.id,
                )
        self.session.flush()
        for code, amount in (
            ("NET_INVESTING", row.net_investing),
            ("NET_FINANCING", row.net_financing),
            ("EXCHANGE_EFFECT", row.exchange_effect),
            ("CLOSING_CASH", row.closing_cash),
        ):
            line(code, amount)
        self.session.add_all(lines)
        for trace in traces:
            trace_row = TraceModel(
                id=uuid4(),
                company_id=company,
                statement_id=row.id,
                journal_id=trace.journal_id,
                transaction_id=trace.transaction_id,
            )
            self.session.add(trace_row)
            self.session.flush()
            self.session.add_all(
                [
                    EvidenceModel(
                        id=uuid4(), company_id=company, journal_trace_id=trace_row.id, evidence_id=e
                    )
                    for e in trace.evidence_ids
                ]
            )
        self.session.flush()
        self.session.refresh(row)
        return view(CashStatement, row)

    def lines(self, company: UUID, statement_id: UUID) -> tuple[CashLine, ...]:
        statement = self.get(company, statement_id)
        return tuple(
            CashLine(
                r.id,
                r.line_code,
                r.amount,
                r.source_type,
                r.event_id
                or r.adjustment_id
                or (statement.income_statement_id if r.source_type == "NET_PROFIT" else None),
                r.display_order,
            )
            for r in self.session.scalars(
                select(LineModel)
                .where(LineModel.company_id == company, LineModel.statement_id == statement_id)
                .order_by(LineModel.display_order)
            )
        )

    def drilldown(self, company: UUID, statement_id: UUID, line_id: UUID | None) -> CashDrilldown:
        lines = self.lines(company, statement_id)
        if line_id is not None:
            lines = tuple(line for line in lines if line.id == line_id)
            if not lines:
                raise ResourceNotFound()
        events = tuple(
            view(FrozenEvent, r)
            for r in self.session.scalars(
                select(EventModel)
                .where(EventModel.company_id == company, EventModel.statement_id == statement_id)
                .order_by(
                    EventModel.journal_id, EventModel.cash_line_id, EventModel.counterpart_line_id
                )
            )
        )
        adjusted = tuple(
            view(FrozenAdjustment, r)
            for r in self.session.scalars(
                select(AdjustmentModel)
                .where(
                    AdjustmentModel.company_id == company,
                    AdjustmentModel.statement_id == statement_id,
                )
                .order_by(AdjustmentModel.account_id)
            )
        )
        if line_id is not None:
            selected = lines[0]
            activities = {
                "NET_OPERATING": "OPERATING",
                "NET_INVESTING": "INVESTING",
                "NET_FINANCING": "FINANCING",
                "EXCHANGE_EFFECT": "EXCHANGE_EFFECT",
            }
            events = tuple(
                e
                for e in events
                if e.id == selected.source_id
                or (
                    selected.source_type == "TOTAL"
                    and e.activity_type == activities.get(selected.line_code)
                )
            )
            adjusted = tuple(
                a
                for a in adjusted
                if a.id == selected.source_id
                or (selected.source_type == "TOTAL" and selected.line_code == "NET_OPERATING")
                or (
                    selected.source_type == "NET_PROFIT"
                    and a.adjustment_code in {"OPERATING_RESULT", "NONCASH_PAIR"}
                )
            )
        sources = tuple(
            view(CashSource, r)
            for r in self.session.scalars(
                select(SourceModel)
                .where(
                    SourceModel.company_id == company,
                    SourceModel.adjustment_id.in_([a.id for a in adjusted]),
                )
                .order_by(
                    SourceModel.adjustment_id, SourceModel.entry_date, SourceModel.journal_line_id
                )
            )
        )
        balances = tuple(
            view(CashBalanceSource, r)
            for r in self.session.scalars(
                select(BalanceModel)
                .where(
                    BalanceModel.company_id == company, BalanceModel.statement_id == statement_id
                )
                .order_by(BalanceModel.entry_date, BalanceModel.journal_line_id)
            )
        )
        if line_id is not None:
            balances = tuple(
                s
                for s in balances
                if lines[0].line_code == "CLOSING_CASH"
                or (lines[0].line_code == "OPENING_CASH" and s.is_opening)
            )
        journal_ids = (
            {e.journal_id for e in events}
            | {s.journal_id for s in sources}
            | {s.journal_id for s in balances}
        )
        traces = []
        for r in self.session.scalars(
            select(TraceModel)
            .where(
                TraceModel.company_id == company,
                TraceModel.statement_id == statement_id,
                TraceModel.journal_id.in_(journal_ids),
            )
            .order_by(TraceModel.journal_id)
        ):
            evidence = tuple(
                self.session.scalars(
                    select(EvidenceModel.evidence_id)
                    .where(
                        EvidenceModel.company_id == company, EvidenceModel.journal_trace_id == r.id
                    )
                    .order_by(EvidenceModel.evidence_id)
                )
            )
            traces.append(JournalTrace(r.journal_id, r.transaction_id, evidence))
        return CashDrilldown(
            statement_id, lines, events, adjusted, sources, balances, tuple(traces)
        )
