"""수식과 매크로가 없는 단순 OOXML 양식을 생성합니다. 동일 Catalog를 사용합니다."""

from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from app.intake.domain.workbook import Workbook
from app.intake.infrastructure.parser import parse_file
from app.onboarding.domain.catalog import SECTIONS
from app.onboarding.domain.template import (
    LOCALE,
    SCHEMA_VERSION,
    TEMPLATE_CODE,
    TEMPLATE_VERSION,
    sheet_fields,
)


def parse_onboarding(filename: str, content: bytes, content_type: str) -> Workbook:
    # 동일 보안 파서의 제한된 공식 양식 profile만 확장합니다.
    return parse_file(filename, content, content_type, max_sheets=16, allow_empty=True)


def column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def workbook_bytes(sheets: dict[str, list[list[str]]]) -> bytes:
    from xml.etree.ElementTree import Element, SubElement, tostring

    stream = BytesIO()
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    doc_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    content_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    types = Element(f"{{{content_ns}}}Types")
    for extension, content_type in (
        ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
        ("xml", "application/xml"),
    ):
        SubElement(types, f"{{{content_ns}}}Default", Extension=extension, ContentType=content_type)
    SubElement(
        types,
        f"{{{content_ns}}}Override",
        PartName="/xl/workbook.xml",
        ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    )
    root_rel = Element(f"{{{rel_ns}}}Relationships")
    SubElement(
        root_rel,
        f"{{{rel_ns}}}Relationship",
        Id="rId1",
        Type=doc_rel + "/officeDocument",
        Target="xl/workbook.xml",
    )
    book = Element(f"{{{ns}}}workbook")
    listed = SubElement(book, f"{{{ns}}}sheets")
    relationships = Element(f"{{{rel_ns}}}Relationships")
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for index, (name, rows) in enumerate(sheets.items(), 1):
            path = f"xl/worksheets/sheet{index}.xml"
            SubElement(
                types,
                f"{{{content_ns}}}Override",
                PartName="/" + path,
                ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
            )
            SubElement(
                listed,
                f"{{{ns}}}sheet",
                {"name": name, "sheetId": str(index), f"{{{doc_rel}}}id": f"rId{index}"},
            )
            SubElement(
                relationships,
                f"{{{rel_ns}}}Relationship",
                Id=f"rId{index}",
                Type=doc_rel + "/worksheet",
                Target=f"worksheets/sheet{index}.xml",
            )
            worksheet = Element(f"{{{ns}}}worksheet")
            data = SubElement(worksheet, f"{{{ns}}}sheetData")
            for number, values in enumerate(rows, 1):
                row = SubElement(data, f"{{{ns}}}row", r=str(number))
                for column, value in enumerate(values, 1):
                    cell = SubElement(
                        row, f"{{{ns}}}c", r=f"{column_name(column)}{number}", t="inlineStr"
                    )
                    text = SubElement(SubElement(cell, f"{{{ns}}}is"), f"{{{ns}}}t")
                    text.text = value
            archive.writestr(path, tostring(worksheet, encoding="utf-8", xml_declaration=True))
        for path, document in (
            ("[Content_Types].xml", types),
            ("_rels/.rels", root_rel),
            ("xl/workbook.xml", book),
            ("xl/_rels/workbook.xml.rels", relationships),
        ):
            archive.writestr(path, tostring(document, encoding="utf-8", xml_declaration=True))
    return stream.getvalue()


def template_sheets(now: datetime | None = None) -> dict[str, list[list[str]]]:
    now = now or datetime.now(UTC)
    sheets = {
        "README": [
            ["항목", "안내"],
            ["사용 방법", "각 Sheet에 직접 입력하고 업로드 후 병합 내용을 확인해 주세요."],
            ["보안", "수식·매크로·계좌 원번호·비밀번호를 입력하지 마세요."],
            [
                "미지원 업무",
                "기초잔액·자산·재고·채권채무 자료는 초안에 보존되며 완료가 차단됩니다.",
            ],
        ]
    }
    for section in SECTIONS:
        fields = sheet_fields(section)
        sheets[section] = [[f.field_code.split(".")[1] for f in fields]]
        for field in fields:
            sheets["README"].append(
                [
                    field.field_code,
                    f"{field.label} / {field.data_type} / {field.required_rule_code}",
                ]
            )
    sheets["Metadata"] = [
        ["key", "value"],
        ["template_code", TEMPLATE_CODE],
        ["template_version", TEMPLATE_VERSION],
        ["schema_version", SCHEMA_VERSION],
        ["generated_at", now.isoformat()],
        ["locale", LOCALE],
    ]
    return sheets


def generate_template() -> bytes:
    return workbook_bytes(template_sheets())
