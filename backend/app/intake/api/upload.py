"""가져오기 API들이 공유하는 크기 제한 multipart 수신입니다."""

from dataclasses import dataclass

from fastapi import Request
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException
from starlette.requests import Request as FormRequest
from starlette.types import Message

from app.contracts.access_errors import InvalidInput
from app.intake.domain.errors import IntakeFileError


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    content: bytes
    content_type: str
    fields: dict[str, str]


async def receive_upload(request: Request) -> UploadedFile:
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > 2_020_000:
            raise IntakeFileError()
        content.extend(chunk)

    async def receive() -> Message:
        return {"type": "http.request", "body": bytes(content), "more_body": False}

    try:
        async with FormRequest(request.scope, receive).form(
            max_files=1, max_fields=3, max_part_size=2_000_000
        ) as form:
            if len(form.multi_items()) != len(form) or "file" not in form:
                raise InvalidInput()
            file = form["file"]
            if not isinstance(file, UploadFile) or file.filename is None:
                raise InvalidInput()
            fields: dict[str, str] = {}
            for key, value in form.items():
                if key != "file":
                    if not isinstance(value, str):
                        raise InvalidInput()
                    fields[key] = value
            return UploadedFile(
                file.filename,
                await file.read(2_000_001),
                file.content_type or "application/octet-stream",
                fields,
            )
    except MultiPartException:
        raise InvalidInput() from None
