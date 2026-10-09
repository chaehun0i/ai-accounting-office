import pytest
from pydantic import ValidationError

from app.intake.api.schemas import ConfirmCommand


@pytest.mark.parametrize("value", [False, 0, 1, "true", "false", None])
def test_confirm_requires_explicit_boolean_consent(value: object) -> None:
    with pytest.raises(ValidationError):
        ConfirmCommand.model_validate(
            {"expected_version": 2, "preview_digest": "a" * 64, "confirmed": value}
        )


def test_confirm_rejects_extra_fields() -> None:
    assert ConfirmCommand(expected_version=2, preview_digest="a" * 64, confirmed=True).confirmed
    with pytest.raises(ValidationError):
        ConfirmCommand.model_validate(
            {
                "expected_version": 2,
                "preview_digest": "a" * 64,
                "confirmed": True,
                "company_id": "untrusted",
            }
        )
