"""독립 PostgreSQL 연결에서 동일 기간의 결산 명령 경쟁을 검증합니다."""

from uuid import uuid4

from tests.integration.test_business_document_concurrency import parallel
from tests.integration.test_closing_workflow import request, reviewer

pytest_plugins = ["tests.integration.test_business_document_concurrency"]


def test_parallel_start_same_key_creates_one_active_run(isolated_document_client):
    client, (owner, writer, payload, _, _, connection) = isolated_document_client
    period_id = payload["accounting_period_id"]
    key = str(uuid4())
    results = parallel(
        lambda _: request(client, writer, "/closing-runs", {"accounting_period_id": period_id}, key)
    )
    assert [response.status_code for response in results] == [201, 201]
    assert results[0].json()["id"] == results[1].json()["id"]
    assert len(client.get(f"/closing/periods/{period_id}/runs", headers=owner).json()) == 1


def test_parallel_close_increments_version_once(isolated_document_client):
    client, (owner, writer, payload, _, _, connection) = isolated_document_client
    review = reviewer(client, owner, connection)
    period_id = payload["accounting_period_id"]
    run = request(client, writer, "/closing-runs", {"accounting_period_id": period_id}).json()
    approval = request(
        client, review, f"/closing-runs/{run['id']}/submit", {"reason": "동시 마감 검토"}
    ).json()
    assert (
        request(
            client, owner, f"/closing-approvals/{approval['id']}/approve", {"reason": "검토 완료"}
        ).status_code
        == 200
    )
    key = str(uuid4())
    results = parallel(
        lambda _: request(
            client,
            owner,
            f"/closing-runs/{run['id']}/close",
            {"approval_id": approval["id"]},
            key,
        )
    )
    assert [response.status_code for response in results] == [200, 200]
    periods = client.get("/closing/periods", headers=owner).json()
    assert next(period for period in periods if period["id"] == period_id)["close_version"] == 1
