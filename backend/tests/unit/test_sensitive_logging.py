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


def test_uvicorn_formatter_keeps_structured_arguments_and_redacts_capability():
    from uvicorn.logging import AccessFormatter

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "POST", "/invitations/private-token/accept", "1.1", 200),
        None,
    )
    SensitivePathFilter().filter(record)
    formatted = AccessFormatter("%(client_addr)s %(request_line)s %(status_code)s").format(record)
    assert "private-token" not in formatted
    assert "[숨김]" in formatted and "200" in formatted
