"""Render only the exact five frozen members of an independently approved set."""

from sqlalchemy import select

from app.contracts.access_errors import StateConflict
from app.reporting.cash_flow.snapshot_models import CashFlowLineModel
from app.reporting.cash_flow.unit_of_work import CashFlowUnitOfWork
from app.reporting.center.render import ReportDocument
from app.reporting.center.repository import ReportRun
from app.reporting.disclosures.models import DisclosureNarrativeModel, DisclosureValueModel
from app.reporting.equity.models import EquityStatementLineModel
from app.reporting.statement_sets.models import StatementSetRevisionModel
from app.reporting.statement_sets.review import latest_review
from app.reporting.statement_sets.service import StatementSetService


def render_set(uow: CashFlowUnitOfWork, run: ReportRun, company_name: str) -> ReportDocument:
    revision = uow.session.scalar(
        select(StatementSetRevisionModel).where(
            StatementSetRevisionModel.company_id == run.company_id,
            StatementSetRevisionModel.snapshot_digest == run.source_digest,
            StatementSetRevisionModel.statement_set_id == run.statement_set_id,
            StatementSetRevisionModel.period_id == run.period_id,
        )
    )
    if revision is None:
        raise StateConflict()
    approval = latest_review(uow, run.company_id, revision.id)
    current = StatementSetService(lambda: uow).collect(uow, run.company_id, run.period_id)
    if (
        approval is None
        or approval.status != "APPROVED"
        or current["issues"]
        or current["source_digest"] != revision.snapshot_digest
    ):
        raise StateConflict()
    rows: list[tuple[str, ...]] = []
    for kind, identifier in (
        ("BALANCE_SHEET", revision.balance_id),
        ("INCOME_STATEMENT", revision.income_id),
    ):
        view = uow.statements.statement(run.company_id, revision.statement_set_id, kind)
        if view is None or view.id != identifier:
            raise StateConflict()
        rows.extend(
            (kind, line.line_code, str(line.current_amount), str(identifier)) for line in view.lines
        )
    cash_lines = uow.session.scalars(
        select(CashFlowLineModel)
        .where(
            CashFlowLineModel.company_id == run.company_id,
            CashFlowLineModel.statement_id == revision.cash_id,
        )
        .order_by(CashFlowLineModel.line_code, CashFlowLineModel.id)
    )
    rows.extend(
        ("CASH_FLOW", line.line_code, str(line.amount), str(revision.cash_id))
        for line in cash_lines
    )
    equity_lines = uow.session.scalars(
        select(EquityStatementLineModel)
        .where(
            EquityStatementLineModel.company_id == run.company_id,
            EquityStatementLineModel.statement_id == revision.equity_id,
        )
        .order_by(EquityStatementLineModel.display_order, EquityStatementLineModel.component_id)
    )
    rows.extend(
        (
            "CHANGES_IN_EQUITY",
            line.movement_type + ":" + str(line.component_id),
            str(line.amount),
            str(revision.equity_id),
        )
        for line in equity_lines
    )
    for value in uow.session.scalars(
        select(DisclosureValueModel)
        .where(
            DisclosureValueModel.company_id == run.company_id,
            DisclosureValueModel.instance_id == revision.notes_id,
        )
        .order_by(
            DisclosureValueModel.section_id,
            DisclosureValueModel.source_code,
            DisclosureValueModel.id,
        )
    ):
        rows.append(
            (
                "NOTES",
                value.source_code,
                str(
                    value.decimal_value
                    if value.decimal_value is not None
                    else value.text_value or ""
                ),
                str(revision.notes_id),
            )
        )
    narratives = tuple(
        (str(row.section_id), row.text_value, row.source_digest)
        for row in uow.session.scalars(
            select(DisclosureNarrativeModel)
            .where(
                DisclosureNarrativeModel.company_id == run.company_id,
                DisclosureNarrativeModel.instance_id == revision.notes_id,
            )
            .order_by(DisclosureNarrativeModel.section_id)
        )
    )
    return ReportDocument(
        metadata=(
            ("company", company_name),
            ("report", run.report_code),
            ("period", str(run.date_from) + "/" + str(run.date_to)),
            ("generated_at", run.requested_at.isoformat()),
            ("set_revision_id", str(revision.id)),
            ("close_version", str(run.close_version)),
            ("taxonomy_version", str(run.taxonomy_version)),
            ("statement_set_id", str(revision.statement_set_id)),
            ("source_digest", revision.snapshot_digest),
            ("approval_id", str(approval.id)),
            ("approved_by", str(approval.actor_id)),
            ("approved_at", approval.created_at.isoformat()),
            ("status", "APPROVED"),
            ("validation_scope", "INTERNAL_VALIDATION_ONLY"),
        ),
        columns=("statement", "line", "amount", "member_id"),
        rows=tuple(rows),
        sections=(("Notes narrative", ("section", "text", "source_digest"), narratives),),
    )
