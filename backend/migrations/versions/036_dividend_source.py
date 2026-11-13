"""One declaration per posted dividend resolution; never discard existing duplicates."""

from alembic import op

revision = "036_dividend_source"
down_revision = "035_equity_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_dividend_declaration_source",
        "dividend_declarations",
        ["company_id", "source_journal_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_dividend_declaration_source", "dividend_declarations", type_="unique")
