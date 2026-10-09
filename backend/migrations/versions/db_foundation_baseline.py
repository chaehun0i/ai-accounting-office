"""업무 테이블 없이 마이그레이션 실행 이력의 기준점을 만듭니다."""

revision: str = "db_foundation"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 실제 업무 DDL은 후속 Identity/Company 범위에서 시작합니다.
    pass


def downgrade() -> None:
    # 이 기준점은 업무 테이블을 생성하지 않았으므로 되돌릴 DDL이 없습니다.
    pass
