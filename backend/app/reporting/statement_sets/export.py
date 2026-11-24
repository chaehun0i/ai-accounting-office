"""Render only the exact five frozen members of an independently approved set."""

from sqlalchemy import select

from app.contracts.access_errors import StateConflict
from app.reporting.cash_flow.unit_of_work import CashFlowUnitOfWork
from app.reporting.center.render import ReportDocument
from app.reporting.center.repository import ReportRun
from app.reporting.statement_sets.contents import frozen_contents
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
    rows, narratives = frozen_contents(uow, revision)
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
