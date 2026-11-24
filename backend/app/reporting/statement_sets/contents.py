"""Read frozen members for both the approved-set viewer and report rendering."""

from sqlalchemy import select

from app.contracts.access_errors import StateConflict
from app.reporting.cash_flow.snapshot_models import CashFlowLineModel
from app.reporting.cash_flow.unit_of_work import CashFlowUnitOfWork
from app.reporting.disclosures.models import DisclosureNarrativeModel, DisclosureValueModel
from app.reporting.equity.models import EquityStatementLineModel
from app.reporting.statement_sets.models import StatementSetRevisionModel


def frozen_contents(
    uow: CashFlowUnitOfWork, revision: StatementSetRevisionModel
) -> tuple[list[tuple[str, ...]], tuple[tuple[str, ...], ...]]:
    rows: list[tuple[str, ...]] = []
    for kind, identifier in (
        ("BALANCE_SHEET", revision.balance_id),
        ("INCOME_STATEMENT", revision.income_id),
    ):
        view = uow.statements.statement(revision.company_id, revision.statement_set_id, kind)
        if view is None or view.id != identifier:
            raise StateConflict()
        rows.extend(
            (kind, line.line_code, str(line.current_amount), str(identifier)) for line in view.lines
        )
    cash_lines = uow.session.scalars(
        select(CashFlowLineModel)
        .where(
            CashFlowLineModel.company_id == revision.company_id,
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
            EquityStatementLineModel.company_id == revision.company_id,
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
            DisclosureValueModel.company_id == revision.company_id,
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
                DisclosureNarrativeModel.company_id == revision.company_id,
                DisclosureNarrativeModel.instance_id == revision.notes_id,
            )
            .order_by(DisclosureNarrativeModel.section_id)
        )
    )
    return rows, narratives
