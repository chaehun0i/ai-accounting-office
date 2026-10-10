import pytest

from app.intake.domain.errors import IntakeFileError
from app.intake.infrastructure.parser import XLSX_MIME, parse_file
from app.onboarding.domain.errors import TemplateUnsupported
from app.onboarding.domain.template import read_template
from app.onboarding.infrastructure.template import (
    generate_template,
    parse_onboarding,
    template_sheets,
    workbook_bytes,
)


def test_empty_official_template_and_shared_parser_profile() -> None:
    content = generate_template()
    book = parse_onboarding("onboarding.xlsx", content, XLSX_MIME)
    metadata, cells, errors = read_template(book)
    assert metadata["template_version"] == "1"
    assert not cells and not errors
    assert len(book.sheets) == 14


def test_unsupported_template_version() -> None:
    sheets = template_sheets()
    sheets["Metadata"][2][1] = "999"
    with pytest.raises(TemplateUnsupported):
        read_template(parse_onboarding("test.xlsx", workbook_bytes(sheets), XLSX_MIME))


def test_existing_parser_keeps_its_stricter_profile() -> None:
    with pytest.raises(IntakeFileError):
        parse_file("test.xlsx", generate_template(), XLSX_MIME)
