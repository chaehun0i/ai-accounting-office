"""Report date resolution uses persisted company settings and authorization."""

from datetime import date

from tests.integration.test_journal_flow import prepare


def test_report_period_policy_api_and_company_permission(api_client, auth_service):
    owner, writer, _, _ = prepare(api_client, auth_service)
    path = "/report-periods/resolve"
    params = {"period_preset": "THIS_WEEK", "period_mode": "RANGE"}
    assert api_client.get(path, params=params).status_code == 401
    foreign = api_client.post(
        "/auth/register",
        json={"email": "foreign-report-period@example.com", "password": "StrongPassword!2026"},
    )
    assert foreign.status_code == 201, foreign.text
    foreign_headers = {
        **owner,
        "Authorization": "Bearer " + foreign.json()["access_token"],
    }
    assert api_client.get(path, headers=foreign_headers, params=params).status_code == 404
    initial = api_client.get(path, headers=owner, params=params)
    assert initial.status_code == 200, initial.text
    assert initial.json()["timezone"] == "Asia/Seoul"
    before = api_client.get("/accounting/settings", headers=writer)
    assert before.status_code == 200
    changed = api_client.patch(
        "/accounting/settings",
        headers=owner,
        json={
            "expected_version": before.json()["version"],
            "reporting_week_start": 6,
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["reporting_week_start"] == 6
    resolved = api_client.get(path, headers=owner, params=params)
    assert resolved.status_code == 200, resolved.text
    assert date.fromisoformat(resolved.json()["date_from"]).weekday() == 6
    assert (
        api_client.patch(
            "/accounting/settings",
            headers=owner,
            json={"expected_version": before.json()["version"], "reporting_week_start": 0},
        ).status_code
        == 409
    )
