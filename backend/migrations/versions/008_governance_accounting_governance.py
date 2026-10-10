"""회계 승인 감사 멱등성 기반

리비전: 008_governance
이전 리비전: 007_journal_core
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa


revision: str = '008_governance'
down_revision: str | Sequence[str] | None = '007_journal_core'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 회계 명령의 승인·감사·멱등성 참조를 생성합니다.
    op.create_table('approvals',
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('journal_id', sa.Uuid(), nullable=False),
    sa.Column('target_version', sa.Integer(), nullable=False),
    sa.Column('target_digest', sa.String(length=64), nullable=False),
    sa.Column('action_code', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('requester_id', sa.Uuid(), nullable=False),
    sa.Column('reviewer_id', sa.Uuid(), nullable=True),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED','CONSUMED','EXPIRED')", name=op.f('ck_approvals_status')),
    sa.CheckConstraint('reviewer_id IS NULL OR reviewer_id<>requester_id', name=op.f('ck_approvals_separation')),
    sa.CheckConstraint('target_version>=1', name=op.f('ck_approvals_version')),
    sa.ForeignKeyConstraint(['company_id', 'journal_id'], ['journal_entries.company_id', 'journal_entries.id'], name=op.f('fk_approvals_company_id_journal_id_journal_entries'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_approvals_company_id_companies'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['requester_id'], ['users.id'], name=op.f('fk_approvals_requester_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], name=op.f('fk_approvals_reviewer_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_approvals')),
    sa.UniqueConstraint('company_id', 'id', name=op.f('uq_approvals_company_id_id'))
    )
    op.create_index(op.f('ix_approvals_company_id'), 'approvals', ['company_id'], unique=False)
    op.create_index(op.f('ix_approvals_journal_id'), 'approvals', ['journal_id'], unique=False)
    op.create_index(op.f('ix_approvals_requester_id'), 'approvals', ['requester_id'], unique=False)
    op.create_index(op.f('ix_approvals_reviewer_id'), 'approvals', ['reviewer_id'], unique=False)
    op.create_table('audit_events',
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=False),
    sa.Column('journal_id', sa.Uuid(), nullable=False),
    sa.Column('action_code', sa.String(length=40), nullable=False),
    sa.Column('result_code', sa.String(length=20), nullable=False),
    sa.Column('request_id', sa.String(length=100), nullable=False),
    sa.Column('before_digest', sa.String(length=64), nullable=False),
    sa.Column('after_digest', sa.String(length=64), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_audit_events_actor_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['company_id', 'journal_id'], ['journal_entries.company_id', 'journal_entries.id'], name=op.f('fk_audit_events_company_id_journal_id_journal_entries'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_audit_events_company_id_companies'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events'))
    )
    op.create_index(op.f('ix_audit_events_actor_id'), 'audit_events', ['actor_id'], unique=False)
    op.create_index(op.f('ix_audit_events_company_id'), 'audit_events', ['company_id'], unique=False)
    op.create_index(op.f('ix_audit_events_journal_id'), 'audit_events', ['journal_id'], unique=False)
    op.create_table('idempotency_records',
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=False),
    sa.Column('command_code', sa.String(length=40), nullable=False),
    sa.Column('idempotency_key', sa.String(length=100), nullable=False),
    sa.Column('request_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('journal_id', sa.Uuid(), nullable=False),
    sa.Column('result_version', sa.Integer(), nullable=False),
    sa.Column('http_status', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("status='SUCCEEDED'", name=op.f('ck_idempotency_records_status')),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_idempotency_records_actor_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['company_id', 'journal_id'], ['journal_entries.company_id', 'journal_entries.id'], name=op.f('fk_idempotency_records_company_id_journal_id_journal_entries'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_idempotency_records_company_id_companies'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_idempotency_records')),
    sa.UniqueConstraint('company_id', 'actor_id', 'command_code', 'idempotency_key', name=op.f('uq_idempotency_records_company_id_actor_id_command_code_idempotency_key'))
    )
    op.create_index(op.f('ix_idempotency_records_actor_id'), 'idempotency_records', ['actor_id'], unique=False)
    op.create_index(op.f('ix_idempotency_records_company_id'), 'idempotency_records', ['company_id'], unique=False)
    op.create_index(op.f('ix_idempotency_records_journal_id'), 'idempotency_records', ['journal_id'], unique=False)
    op.create_foreign_key('fk_journal_approval', 'journal_entries', 'approvals', ['company_id', 'approval_id'], ['company_id', 'id'], ondelete='RESTRICT', use_alter=True)



def downgrade() -> None:
    # 회계 명령의 승인·감사·멱등성 참조를 생성합니다.
    op.drop_constraint('fk_journal_approval', 'journal_entries', type_='foreignkey')
    op.drop_index(op.f('ix_idempotency_records_journal_id'), table_name='idempotency_records')
    op.drop_index(op.f('ix_idempotency_records_company_id'), table_name='idempotency_records')
    op.drop_index(op.f('ix_idempotency_records_actor_id'), table_name='idempotency_records')
    op.drop_table('idempotency_records')
    op.drop_index(op.f('ix_audit_events_journal_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_company_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_actor_id'), table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index(op.f('ix_approvals_reviewer_id'), table_name='approvals')
    op.drop_index(op.f('ix_approvals_requester_id'), table_name='approvals')
    op.drop_index(op.f('ix_approvals_journal_id'), table_name='approvals')
    op.drop_index(op.f('ix_approvals_company_id'), table_name='approvals')
    op.drop_table('approvals')

