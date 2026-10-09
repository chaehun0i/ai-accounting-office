import logging

from app.core.logging import SensitivePathFilter


def test_invitation_capability_is_redacted_from_transport_logs() -> None:
    token = "sensitive-invitation-capability"
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        "POST /invitations/%s/accept HTTP/1.1",
        (token,),
        None,
    )
    assert SensitivePathFilter().filter(record)
    assert token not in record.getMessage()
    assert "[숨김]" in record.getMessage()
