from app.main import create_app


def test_report_period_resolution_is_company_scoped(settings):
    paths = create_app(settings).openapi()["paths"]
    get = paths["/report-periods/resolve"]["get"]
    assert any(p["name"] == "X-Company-ID" and p["required"] for p in get["parameters"])
    assert {p["name"] for p in get["parameters"]} >= {"period_preset", "period_mode"}
