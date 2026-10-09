from sqlalchemy import Connection, text

from app.identity.auth.application.service import AuthService


def test_identity_company_relational_constraints(
    auth_service: tuple[AuthService, Connection],
) -> None:
    _, connection = auth_service
    rows = connection.execute(
        text("""
        SELECT c.relname, con.contype
        FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
    """)
    ).all()
    constraints = {(name, kind) for name, kind in rows}
    for table in (
        "users",
        "refresh_sessions",
        "identity_security_events",
        "tenants",
        "companies",
        "roles",
        "permissions",
        "role_permissions",
        "company_memberships",
        "company_invitations",
    ):
        assert (table, "p") in constraints
    for table in (
        "refresh_sessions",
        "identity_security_events",
        "companies",
        "role_permissions",
        "company_memberships",
        "company_invitations",
    ):
        assert (table, "f") in constraints
    for table in (
        "users",
        "refresh_sessions",
        "companies",
        "company_memberships",
        "company_invitations",
    ):
        assert (table, "u") in constraints
        assert (table, "c") in constraints
    assert (
        connection.scalar(
            text("""
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema='public' AND data_type IN ('json', 'jsonb')
    """)
        )
        == 0
    )
    assert (
        connection.scalar(
            text("""
        SELECT count(*) FROM pg_constraint
        WHERE contype='f' AND NOT convalidated
          AND connamespace='public'::regnamespace
    """)
        )
        == 0
    )
    indexes = connection.scalars(
        text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
            "AND tablename='company_invitations'"
        )
    ).all()
    assert any("UNIQUE" in item and "PENDING" in item for item in indexes)
