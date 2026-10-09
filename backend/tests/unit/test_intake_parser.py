from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.intake.domain.errors import IntakeFileError
from app.intake.infrastructure.parser import MAX_BYTES, XLSX_MIME, parse_file


def workbook(extra: dict[str, bytes] | None = None, cell: str = "<v>10.0001</v>") -> bytes:
    files = {
        "[Content_Types].xml": b"<Types/>",
        "xl/workbook.xml": b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sales" sheetId="1" r:id="r1"/></sheets></workbook>',  # noqa: E501
        "xl/_rels/workbook.xml.rels": b'<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>',  # noqa: E501
        "xl/worksheets/sheet1.xml": (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>amount</t></is></c></row><row r="2"><c r="A2">'  # noqa: E501
            + cell
            + "</c></row></sheetData></worksheet>"
        ).encode(),
    }
    files.update(extra or {})
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
def test_csv_and_decimal_text_are_preserved(bom: bytes) -> None:
    result = parse_file("sales.csv", bom + b"amount,date\n10.0001,2026-01-01\n", "text/csv")
    assert result.sheets[0].rows[0][0] == "10.0001"
    assert parse_file("sales.xlsx", workbook(), XLSX_MIME).sheets[0].rows == (("10.0001",),)


@pytest.mark.parametrize(
    "filename,content,mime",
    [
        ("../a.csv", b"a\nb", "text/csv"),
        ("a\\b.csv", b"a\nb", "text/csv"),
        ("a.csv", b"", "text/csv"),
        ("a.csv", b"x" * (MAX_BYTES + 1), "text/csv"),
        ("a.exe", b"a\nb", "text/csv"),
        ("a.csv", b"a,a\n1,2", "text/csv"),
        ("a.csv", b"a,\n1,2", "text/csv"),
        ("a.csv", b"a\n=CMD()", "text/csv"),
        ("a.csv", b"a\n+CMD", "text/csv"),
        ("a.csv", b"a\n-CMD", "text/csv"),
        ("a.csv", b"a\n@SUM(1)", "text/csv"),
        ("a.csv", b"a\n\xff", "text/csv"),
        ("a.csv", b"a\nb", "image/png"),
        ("a.xlsx", b"PK\x03\x04bad", XLSX_MIME),
        ("a.xlsx", workbook(), "text/csv"),
    ],
    ids=lambda v: f"bytes-{len(v)}" if isinstance(v, bytes) else v,
)
def test_unsafe_input_is_rejected(filename: str, content: bytes, mime: str) -> None:
    with pytest.raises(IntakeFileError):
        parse_file(filename, content, mime)


@pytest.mark.parametrize(
    "extra,cell",
    [
        ({"../escape.xml": b"<x/>"}, "<v>1</v>"),
        ({"xl/vbaProject.bin": b"macro"}, "<v>1</v>"),
        ({"xl/externalLinks/link.xml": b"<x/>"}, "<v>1</v>"),
        ({"xl/embeddings/obj.bin": b"object"}, "<v>1</v>"),
        ({"xl/activeX/x.bin": b"object"}, "<v>1</v>"),
        ({"entity.xml": b'<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>'}, "<v>1</v>"),
        (
            {
                "external.rels": b'<Relationships><Relationship TargetMode="External"/></Relationships>'  # noqa: E501
            },
            "<v>1</v>",
        ),
        ({"huge.xml": b" " * 20_000_001}, "<v>1</v>"),
        ({}, "<f>SUM(1)</f><v>1</v>"),
    ],
)
def test_workbook_security_preflight(extra: dict[str, bytes], cell: str) -> None:
    with pytest.raises(IntakeFileError):
        parse_file("data.xlsx", workbook(extra, cell), XLSX_MIME)
