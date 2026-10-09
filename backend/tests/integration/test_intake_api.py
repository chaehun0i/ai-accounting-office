"""실제 PostgreSQL과 파일 저장소를 사용하는 업로드→영수증 검증입니다."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import sessionmaker

from app.companies.infrastructure.models import MembershipModel
from app.evidence.infrastructure.models import EvidenceModel
from app.intake.infrastructure.models import (
    ImportConfirmationModel,
    ImportModel,
    ImportReceiptModel,
    ImportSourceRecordModel,
)
from app.intake.infrastructure.repository import ImportRepository
from app.storage.domain.contracts import StorageUnavailable
from app.storage.infrastructure.local import LocalObjectStorage
from app.storage.infrastructure.models import StorageObjectModel

CSV = b"source_id,date,amount,currency\nsource-1,2026-01-02,100.0001,KRW\n"
COMPANY = {
    "company_name": "자료 검증 회사",
    "business_number": "1234567890",
    "taxpayer_type": "CORPORATION",
    "opening_date": "2026-01-01",
    "address": "테스트 주소",
}


def setup(client, auth_service):
    result = client.post(
        "/auth/register", json={"email": "intake@example.com", "password": "StrongPassword!2026"}
    )
    assert result.status_code == 201, result.text
    headers = {"Authorization": "Bearer " + result.json()["access_token"]}
    company = client.post("/companies", json=COMPANY, headers=headers)
    assert company.status_code == 201, company.text
    headers["X-Company-ID"] = company.json()["id"]
    _, connection = auth_service
    factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    with factory.begin() as session:
        session.execute(
            update(MembershipModel)
            .where(MembershipModel.company_id == UUID(company.json()["id"]))
            .values(role_code="ACCOUNTANT")
        )
    return headers, factory


def upload(client, headers, content=CSV):
    result = client.post(
        "/imports",
        headers=headers,
        data={"source_type": "SALES"},
        files={"file": ("sales.csv", content, "text/csv")},
    )
    assert result.status_code == 201, result.text
    return result.json()


def preview(client, headers, value):
    result = client.post(
        f"/imports/{value['id']}/preview",
        headers=headers,
        json={"expected_version": value["version"]},
    )
    assert result.status_code == 200, result.text
    return result.json()


def confirm(client, headers, value, draft, key="confirm-one"):
    return client.post(
        f"/imports/{value['id']}/confirm",
        headers={**headers, "Idempotency-Key": key},
        json={
            "expected_version": draft["version"],
            "preview_digest": draft["preview_digest"],
            "confirmed": True,
        },
    )


def test_upload_preview_confirm_receipt_and_replay(api_client, auth_service, caplog):
    headers, factory = setup(api_client, auth_service)
    value = upload(api_client, headers)
    draft = preview(api_client, headers, value)
    assert draft["valid"] and draft["row_count"] == 1
    with factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(ImportReceiptModel)) == 0
        stored = session.scalar(select(StorageObjectModel))
        evidence = session.scalar(select(EvidenceModel))
        assert evidence.sha256 == stored.sha256 == value["file_sha256"]
        assert evidence.storage_object_id == stored.id
        assert stored.storage_key != stored.original_filename
    result = confirm(api_client, headers, value, draft)
    assert result.status_code == 200, result.text
    assert result.json()["transaction_count"] == 0
    assert result.json()["evidence_count"] == 1
    assert confirm(api_client, headers, value, draft).json() == result.json()
    assert (
        api_client.get(f"/imports/{value['id']}/receipt", headers=headers).json() == result.json()
    )
    other = upload(api_client, headers)
    other_draft = preview(api_client, headers, other)
    assert confirm(api_client, headers, other, other_draft).status_code == 409
    assert confirm(api_client, headers, other, other_draft, "confirm-two").status_code == 200
    with factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(ImportSourceRecordModel)) == 1
    assert "source-1" not in caplog.text and "100.0001" not in caplog.text


def test_stale_mapping_source_conflict_and_company_isolation(api_client, auth_service):
    headers, factory = setup(api_client, auth_service)
    value = upload(api_client, headers)
    draft = preview(api_client, headers, value)
    columns = api_client.get(f"/imports/{value['id']}/columns", headers=headers).json()
    mappings = [
        {
            "sheet_index": c["sheet_index"],
            "column_index": c["column_index"],
            "canonical_field_code": c["mapping"]["canonical_field_code"],
        }
        for c in columns["columns"]
    ]
    changed = api_client.put(
        f"/imports/{value['id']}/mapping",
        headers=headers,
        json={"expected_version": draft["version"], "mappings": mappings},
    )
    assert changed.status_code == 200, changed.text
    assert confirm(api_client, headers, value, draft).json()["code"] == "PREVIEW_STALE"
    current = changed.json()
    draft = preview(api_client, headers, current)
    assert confirm(api_client, headers, current, draft).status_code == 200
    conflict = upload(api_client, headers, CSV.replace(b"100.0001", b"200.0001"))
    assert (
        confirm(
            api_client, headers, conflict, preview(api_client, headers, conflict), "different"
        ).json()["code"]
        == "IMPORT_SOURCE_CONFLICT"
    )
    with factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(ImportReceiptModel)) == 1
    foreign = {**headers, "X-Company-ID": str(uuid4())}
    for suffix in ("", "/columns", "/errors", "/receipt"):
        assert (
            api_client.get(f"/imports/{value['id']}" + suffix, headers=foreign).status_code == 404
        )
    with factory.begin() as session:
        session.execute(update(MembershipModel).values(status="REVOKED", revoked_at=func.now()))
    assert api_client.get(f"/imports/{value['id']}", headers=headers).status_code == 404


def test_invalid_rows_and_permission_do_not_confirm(api_client, auth_service):
    headers, factory = setup(api_client, auth_service)
    value = upload(api_client, headers, CSV.replace(b"2026-01-02", b"2026-02-30"))
    draft = preview(api_client, headers, value)
    assert not draft["valid"]
    errors = api_client.get(f"/imports/{value['id']}/errors", headers=headers).json()
    assert errors[0]["error_code"] == "INVALID_FIELD_VALUE"
    assert "2026-02-30" not in str(errors)
    assert confirm(api_client, headers, value, draft).status_code == 409
    with factory.begin() as session:
        session.execute(update(MembershipModel).values(role_code="VIEWER"))
    assert api_client.get(f"/imports/{value['id']}", headers=headers).status_code == 403
    assert (
        api_client.post(
            "/imports",
            headers=headers,
            data={"source_type": "SALES"},
            files={"file": ("sales.csv", CSV, "text/csv")},
        ).status_code
        == 403
    )


def test_storage_failure_and_confirm_failure_are_atomic(api_client, auth_service, monkeypatch):
    headers, factory = setup(api_client, auth_service)

    def unavailable(*args):
        raise StorageUnavailable()

    with monkeypatch.context() as patch:
        patch.setattr(LocalObjectStorage, "put", unavailable)
        result = api_client.post(
            "/imports",
            headers=headers,
            data={"source_type": "SALES"},
            files={"file": ("data.csv", CSV, "text/csv")},
        )
        assert result.status_code == 503
    with factory.begin() as session:
        assert session.scalar(select(func.count()).select_from(ImportModel)) == 0
    value = upload(api_client, headers)
    draft = preview(api_client, headers, value)
    original = ImportRepository.confirm

    def fail_after_writes(self, *args):
        original(self, *args)
        raise StorageUnavailable()

    with monkeypatch.context() as patch:
        patch.setattr(ImportRepository, "confirm", fail_after_writes)
        assert confirm(api_client, headers, value, draft).status_code == 503
    with factory.begin() as session:
        for model in (ImportReceiptModel, ImportConfirmationModel, ImportSourceRecordModel):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    assert confirm(api_client, headers, value, draft).status_code == 200


def test_expired_preview_tampered_file_and_wrong_requester(api_client, auth_service):
    from datetime import UTC, datetime, timedelta

    headers, factory = setup(api_client, auth_service)
    value = upload(api_client, headers)
    draft = preview(api_client, headers, value)
    with factory.begin() as session:
        session.execute(
            update(ImportModel).values(preview_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert confirm(api_client, headers, value, draft).json()["code"] == "PREVIEW_STALE"
    current = api_client.get(f"/imports/{value['id']}", headers=headers).json()
    fresh = preview(api_client, headers, current)
    storage = api_client.app.state.services.intake.storage
    with factory.begin() as session:
        key = session.scalar(select(StorageObjectModel.storage_key))
    path = storage.root / key
    path.write_bytes(CSV.replace(b"100.0001", b"101.0001"))
    assert confirm(api_client, headers, value, fresh).json()["code"] == "PREVIEW_STALE"
    path.write_bytes(CSV)
    other = api_client.post(
        "/auth/register",
        json={"email": "other-intake@example.com", "password": "StrongPassword!2026"},
    )
    other_id = UUID(other.json()["user"]["id"])
    with factory.begin() as session:
        session.add(
            MembershipModel(
                id=uuid4(),
                company_id=UUID(headers["X-Company-ID"]),
                user_id=other_id,
                role_code="ACCOUNTANT",
            )
        )
    foreign_actor = {**headers, "Authorization": "Bearer " + other.json()["access_token"]}
    assert api_client.get(f"/imports/{value['id']}", headers=foreign_actor).status_code == 403


def test_evidence_derivation_preserves_original_and_company_boundary(api_client, auth_service):
    from app.contracts.access_errors import ResourceNotFound
    from app.evidence.application.service import EvidenceService
    from app.evidence.domain.types import EvidenceType
    from app.identity.sessions.infrastructure.models import RefreshSessionModel
    from app.identity.users.domain.entities import Principal
    from app.intake.infrastructure.unit_of_work import IntakeSQLAlchemyUnitOfWork

    headers, factory = setup(api_client, auth_service)
    upload(api_client, headers)
    with factory.begin() as session:
        parent = session.scalar(select(EvidenceModel))
        parent_id, user_id, company_id = parent.id, parent.created_by, parent.company_id
        session_id = session.scalar(
            select(RefreshSessionModel.id).where(RefreshSessionModel.user_id == user_id)
        )
    actor = Principal(user_id, session_id, "intake@example.com")
    service = EvidenceService(lambda: IntakeSQLAlchemyUnitOfWork(factory))
    original = service.get(actor, company_id, parent_id)
    derived = service.derive(actor, company_id, parent_id, EvidenceType.RULE_RESULT, uuid4())
    assert derived.id != original.id and derived.parent_evidence_id == original.id
    assert derived.sha256 == original.sha256
    assert derived.storage_object_id == original.storage_object_id
    assert service.get(actor, company_id, original.id) == original
    with pytest.raises(ResourceNotFound):
        service.get(actor, uuid4(), parent_id)


def test_database_failure_removes_unreferenced_object(api_client, auth_service, monkeypatch):
    headers, factory = setup(api_client, auth_service)
    storage = api_client.app.state.services.intake.storage
    original = ImportRepository.add

    def fail_after_insert(self, *args):
        original(self, *args)
        raise StorageUnavailable()

    monkeypatch.setattr(ImportRepository, "add", fail_after_insert)
    result = api_client.post(
        "/imports",
        headers=headers,
        data={"source_type": "SALES"},
        files={"file": ("data.csv", CSV, "text/csv")},
    )
    assert result.status_code == 503
    assert not [p for p in storage.root.rglob("*") if p.is_file()]
    with factory.begin() as session:
        for model in (StorageObjectModel, EvidenceModel, ImportModel):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_ambiguous_mapping_requires_user_correction(api_client, auth_service):
    headers, _ = setup(api_client, auth_service)
    value = upload(
        api_client,
        headers,
        b"source_id,date,transaction_date,amount,currency,unknown\ns1,2026-01-01,2026-01-01,1.0001,KRW,ignored\n",  # noqa: E501
    )
    draft = preview(api_client, headers, value)
    assert not draft["valid"]
    assert any(e["error_code"] == "MAPPING_AMBIGUOUS" for e in draft["errors"])
    corrected = api_client.put(
        f"/imports/{value['id']}/mapping",
        headers=headers,
        json={
            "expected_version": draft["version"],
            "mappings": [
                {"sheet_index": 0, "column_index": index, "canonical_field_code": code}
                for index, code in enumerate(
                    ["source_id", "transaction_date", None, "amount", "currency", None]
                )
            ],
        },
    )
    assert corrected.status_code == 200
    fresh = preview(api_client, headers, corrected.json())
    assert fresh["valid"]
    assert confirm(api_client, headers, value, fresh).status_code == 200


def test_xlsx_upload_to_receipt(api_client, auth_service):
    from io import BytesIO
    from zipfile import ZipFile

    headers, _ = setup(api_client, auth_service)
    output = BytesIO()
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relationships = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    rows = []
    for number, values in enumerate(
        [
            ("source_id", "transaction_date", "amount", "currency"),
            ("xlsx-1", "2026-01-02", "100.0001", "KRW"),
        ],
        1,
    ):
        cells = "".join(
            f'<c r="{chr(65 + i)}{number}" t="inlineStr"><is><t>{value}</t></is></c>'
            for i, value in enumerate(values)
        )
        rows.append(f'<row r="{number}">{cells}</row>')
    with ZipFile(output, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{ns}" xmlns:r="{relationships}"><sheets><sheet name="Sales" sheetId="1" r:id="r1"/></sheets></workbook>',  # noqa: E501
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{ns}"><sheetData>{"".join(rows)}</sheetData></worksheet>',
        )
    result = api_client.post(
        "/imports",
        headers=headers,
        data={"source_type": "SALES"},
        files={
            "file": (
                "sales.xlsx",
                output.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert result.status_code == 201, result.text
    value = result.json()
    draft = preview(api_client, headers, value)
    assert draft["valid"]
    assert confirm(api_client, headers, value, draft).status_code == 200
