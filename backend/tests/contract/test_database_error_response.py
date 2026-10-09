from fastapi.testclient import TestClient

from app.contracts.errors import DatabaseUnavailable, UniqueConflict
from app.core.config import Settings
from app.main import create_app


def test_persistence_errors_use_existing_safe_envelope(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/test-unavailable")
    def unavailable() -> None:
        raise DatabaseUnavailable()

    @app.get("/test-unique")
    def duplicate() -> None:
        raise UniqueConflict()

    with TestClient(app) as client:
        for path, status, code in [
            ("/test-unavailable", 503, "UPSTREAM_UNAVAILABLE"),
            ("/test-unique", 422, "BUSINESS_RULE_VIOLATION"),
        ]:
            response = client.get(path)
            assert response.status_code == status
            assert response.json()["code"] == code
            assert response.json()["request_id"] == response.headers["x-request-id"]
            assert response.json()["field_errors"] == []
