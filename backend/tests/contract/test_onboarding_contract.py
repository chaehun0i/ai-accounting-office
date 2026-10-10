"""OpenAPI와 typed command가 화면·자동화에 같은 계약을 제공합니다."""

import pytest
from pydantic import ValidationError

from app.main import create_app
from app.onboarding.api.schemas import ApplyCommand, ValuesUpdate


def test_onboarding_openapi_declares_all_commands(settings):
    paths = create_app(settings).openapi()["paths"]
    expected = {
        "/onboarding": "get",
        "/onboarding/values": "patch",
        "/onboarding/validate": "post",
        "/onboarding/complete": "post",
        "/onboarding/imports": "post",
        "/onboarding/imports/{identifier}": "get",
        "/onboarding/imports/{identifier}/preview": "post",
        "/onboarding/imports/{identifier}/apply": "post",
    }
    assert all(method in paths[path] for path, method in expected.items())
    content = paths["/onboarding/imports"]["post"]["requestBody"]["content"]
    assert set(content) == {"application/json", "multipart/form-data"}


def test_onboarding_commands_reject_extra_fields_and_untyped_money():
    with pytest.raises(ValidationError):
        ValuesUpdate.model_validate({"expected_version": 1, "payload": {}})
    with pytest.raises(ValidationError):
        ValuesUpdate.model_validate(
            {
                "expected_version": 1,
                "values": [
                    {"field_code": "Opening_Balances.debit_amount", "row_key": "x", "value": 0.1}
                ],
            }
        )
    with pytest.raises(ValidationError):
        ApplyCommand.model_validate(
            {
                "expected_version": 1,
                "preview_digest": "x" * 64,
                "choices": {},
                "overwrite_all": True,
            }
        )
