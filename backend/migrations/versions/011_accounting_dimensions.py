"""회사 관리차원과 분개 연결 추가

리비전: 011_accounting_dimensions
이전 리비전: 010_agent_runtime_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011_accounting_dimensions"
down_revision: str | Sequence[str] | None = "010_agent_runtime_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        op.f("uq_journal_lines_company_id_id"), "journal_lines", ["company_id", "id"]
    )
    op.create_table(
        "accounting_dimensions",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("dimension_code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("dimension_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("required_policy", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "dimension_code ~ '^[A-Z0-9][A-Z0-9_-]{0,39}$'",
            name=op.f("ck_accounting_dimensions_code"),
        ),
        sa.CheckConstraint(
            "dimension_type IN ('BUSINESS_UNIT','DEPARTMENT','PROJECT','COST_CENTER')",
            name=op.f("ck_accounting_dimensions_type"),
        ),
        sa.CheckConstraint(
            "required_policy IN ('OPTIONAL','REQUIRED')",
            name=op.f("ck_accounting_dimensions_required_policy"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')", name=op.f("ck_accounting_dimensions_status")
        ),
        sa.CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 200", name=op.f("ck_accounting_dimensions_name")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_accounting_dimensions_version")),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_accounting_dimensions_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounting_dimensions")),
        sa.UniqueConstraint(
            "company_id",
            "dimension_code",
            name=op.f("uq_accounting_dimensions_company_id_dimension_code"),
        ),
        sa.UniqueConstraint(
            "company_id",
            "id",
            "dimension_type",
            name=op.f("uq_accounting_dimensions_company_id_id_dimension_type"),
        ),
        sa.UniqueConstraint(
            "company_id", "id", name=op.f("uq_accounting_dimensions_company_id_id")
        ),
    )
    op.create_index(
        op.f("ix_accounting_dimensions_company_id"),
        "accounting_dimensions",
        ["company_id"],
        unique=False,
    )
    op.create_table(
        "accounting_dimension_values",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("dimension_id", sa.Uuid(), nullable=False),
        sa.Column("value_code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("parent_value_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')", name=op.f("ck_accounting_dimension_values_status")
        ),
        sa.CheckConstraint(
            "value_code ~ '^[A-Z0-9][A-Z0-9_-]{0,39}$'",
            name=op.f("ck_accounting_dimension_values_code"),
        ),
        sa.CheckConstraint(
            "effective_from IS NULL OR effective_to IS NULL OR effective_from <= effective_to",
            name=op.f("ck_accounting_dimension_values_effective_dates"),
        ),
        sa.CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 200", name=op.f("ck_accounting_dimension_values_name")
        ),
        sa.CheckConstraint(
            "parent_value_id IS NULL OR parent_value_id <> id",
            name=op.f("ck_accounting_dimension_values_parent"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_accounting_dimension_values_version")),
        sa.ForeignKeyConstraint(
            ["company_id", "dimension_id", "parent_value_id"],
            [
                "accounting_dimension_values.company_id",
                "accounting_dimension_values.dimension_id",
                "accounting_dimension_values.id",
            ],
            name=op.f(
                "fk_accounting_dimension_values_company_id_dimension_id_parent_value_id_accounting_dimension_values"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "dimension_id"],
            ["accounting_dimensions.company_id", "accounting_dimensions.id"],
            name=op.f(
                "fk_accounting_dimension_values_company_id_dimension_id_accounting_dimensions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_accounting_dimension_values_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounting_dimension_values")),
        sa.UniqueConstraint(
            "company_id",
            "dimension_id",
            "id",
            name=op.f("uq_accounting_dimension_values_company_id_dimension_id_id"),
        ),
        sa.UniqueConstraint(
            "dimension_id",
            "value_code",
            name=op.f("uq_accounting_dimension_values_dimension_id_value_code"),
        ),
    )
    op.create_index(
        op.f("ix_accounting_dimension_values_company_id"),
        "accounting_dimension_values",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_accounting_dimension_values_dimension_id"),
        "accounting_dimension_values",
        ["dimension_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_accounting_dimension_values_parent_value_id"),
        "accounting_dimension_values",
        ["parent_value_id"],
        unique=False,
    )
    op.create_table(
        "journal_line_dimensions",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("journal_line_id", sa.Uuid(), nullable=False),
        sa.Column("dimension_id", sa.Uuid(), nullable=False),
        sa.Column("dimension_type", sa.String(length=30), nullable=False),
        sa.Column("dimension_value_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "dimension_id", "dimension_type"],
            [
                "accounting_dimensions.company_id",
                "accounting_dimensions.id",
                "accounting_dimensions.dimension_type",
            ],
            name=op.f(
                "fk_journal_line_dimensions_company_id_dimension_id_dimension_type_accounting_dimensions"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "dimension_id", "dimension_value_id"],
            [
                "accounting_dimension_values.company_id",
                "accounting_dimension_values.dimension_id",
                "accounting_dimension_values.id",
            ],
            name=op.f(
                "fk_journal_line_dimensions_company_id_dimension_id_dimension_value_id_accounting_dimension_values"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "journal_line_id"],
            ["journal_lines.company_id", "journal_lines.id"],
            name=op.f("fk_journal_line_dimensions_company_id_journal_line_id_journal_lines"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_line_dimensions")),
        sa.UniqueConstraint(
            "journal_line_id",
            "dimension_id",
            name=op.f("uq_journal_line_dimensions_journal_line_id_dimension_id"),
        ),
        sa.UniqueConstraint(
            "journal_line_id",
            "dimension_type",
            name=op.f("uq_journal_line_dimensions_journal_line_id_dimension_type"),
        ),
    )
    op.create_index(
        op.f("ix_journal_line_dimensions_company_id"),
        "journal_line_dimensions",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_journal_line_dimensions_dimension_value_id"),
        "journal_line_dimensions",
        ["dimension_value_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_journal_line_dimensions_journal_line_id"),
        "journal_line_dimensions",
        ["journal_line_id"],
        unique=False,
    )

    op.execute("""
    CREATE FUNCTION protect_posted_line_dimension() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE old_line uuid; new_line uuid; journal_status text;
    BEGIN
      IF TG_OP <> 'INSERT' THEN old_line := OLD.journal_line_id; END IF;
      IF TG_OP <> 'DELETE' THEN new_line := NEW.journal_line_id; END IF;
      FOR journal_status IN
        SELECT j.status FROM journal_entries j JOIN journal_lines l
          ON l.journal_entry_id=j.id AND l.company_id=j.company_id
        WHERE l.id=old_line OR l.id=new_line ORDER BY j.id FOR UPDATE OF j
      LOOP
        IF journal_status='POSTED' THEN
          RAISE EXCEPTION 'posted journal dimension is immutable' USING ERRCODE='23514';
        END IF;
      END LOOP;
      IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END $$;
    CREATE TRIGGER journal_line_dimension_immutable
      BEFORE INSERT OR UPDATE OR DELETE ON journal_line_dimensions
      FOR EACH ROW EXECUTE FUNCTION protect_posted_line_dimension();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER journal_line_dimension_immutable ON journal_line_dimensions")
    op.execute("DROP FUNCTION protect_posted_line_dimension()")
    op.drop_index(
        op.f("ix_journal_line_dimensions_journal_line_id"), table_name="journal_line_dimensions"
    )
    op.drop_index(
        op.f("ix_journal_line_dimensions_dimension_value_id"), table_name="journal_line_dimensions"
    )
    op.drop_index(
        op.f("ix_journal_line_dimensions_company_id"), table_name="journal_line_dimensions"
    )
    op.drop_table("journal_line_dimensions")
    op.drop_constraint(op.f("uq_journal_lines_company_id_id"), "journal_lines", type_="unique")
    op.drop_index(
        op.f("ix_accounting_dimension_values_parent_value_id"),
        table_name="accounting_dimension_values",
    )
    op.drop_index(
        op.f("ix_accounting_dimension_values_dimension_id"),
        table_name="accounting_dimension_values",
    )
    op.drop_index(
        op.f("ix_accounting_dimension_values_company_id"), table_name="accounting_dimension_values"
    )
    op.drop_table("accounting_dimension_values")
    op.drop_index(op.f("ix_accounting_dimensions_company_id"), table_name="accounting_dimensions")
    op.drop_table("accounting_dimensions")
