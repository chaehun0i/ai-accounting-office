"""수식과 매크로가 없는 단순 OOXML 양식을 생성합니다. 동일 Catalog를 사용합니다."""

from datetime import UTC, datetime
from io import BytesIO
from xml.sax.saxutils import escape
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
    stream = BytesIO()
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            + "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(
                f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
                for i, name in enumerate(sheets, 1)
            )
            + "</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            + "</Relationships>",
        )
        for index, rows in enumerate(sheets.values(), 1):
            data = "".join(
                f'<row r="{r}">'
                + "".join(
                    f'<c r="{column_name(c)}{r}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>'
                    for c, value in enumerate(row, 1)
                )
                + "</row>"
                for r, row in enumerate(rows, 1)
            )
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                f'<worksheet xmlns="{ns}"><sheetData>{data}</sheetData></worksheet>',
            )
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
