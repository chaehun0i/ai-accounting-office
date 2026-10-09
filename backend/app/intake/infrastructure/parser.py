"""한도를 먼저 검사하고 수식·외부 참조를 실행하지 않는 제한적 OOXML 파서입니다."""

import csv
import re
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from app.intake.domain.canonical_fields import normalize
from app.intake.domain.errors import IntakeFileError
from app.intake.domain.workbook import Sheet, Workbook

MAX_BYTES = 2_000_000
MAX_ROWS = 1000
MAX_COLUMNS = 40
MAX_SHEETS = 5
MAX_CELL = 4000
MAX_ENTRIES = 100
MAX_EXPANDED_BYTES = 20_000_000
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def validate_filename(filename: str) -> None:
    if (
        not filename
        or len(filename) > 200
        or filename in {".", ".."}
        or any(c in filename for c in ("/", "\\", "\x00"))
        or any(ord(c) < 32 for c in filename)
    ):
        raise IntakeFileError()


def safe_cell(value: str) -> str:
    if len(value) > MAX_CELL or "\x00" in value:
        raise IntakeFileError()
    stripped = value.lstrip()
    # 음수는 숫자 전체가 명확할 때만 허용하고 명령·수식은 차단합니다.
    if stripped.startswith(("=", "+", "@")) or (
        stripped.startswith("-") and not re.fullmatch(r"-\d+(?:\.\d+)?", stripped)
    ):
        raise IntakeFileError()
    return value


def table(index: int, name: str, rows: list[list[str]]) -> Sheet:
    if len(rows) < 2 or len(rows) > MAX_ROWS + 1:
        raise IntakeFileError()
    headers = tuple(v.strip() for v in rows[0])
    if (
        not headers
        or len(headers) > MAX_COLUMNS
        or any(not h or len(h) > 100 for h in headers)
        or len({normalize(h) for h in headers}) != len(headers)
    ):
        raise IntakeFileError()
    values: list[tuple[str, ...]] = []
    for row in rows[1:]:
        if len(row) != len(headers):
            raise IntakeFileError()
        values.append(tuple(safe_cell(v) for v in row))
    if not any(any(v.strip() for v in row) for row in values):
        raise IntakeFileError()
    return Sheet(index, name, headers, tuple(values))


def xml(data: bytes) -> ET.Element:
    # 모든 내부 XML은 DTD·엔티티 선언을 파싱 전에 거부합니다.
    # UTF-16 등 숨은 선언을 막기 위해 OOXML의 UTF-8 표현만 지원합니다.
    text = data.decode("utf-8-sig")
    if "\x00" in text or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise IntakeFileError()
    return ET.fromstring(text)


def column_number(reference: str) -> int:
    match = re.fullmatch(r"([A-Z]{1,3})([1-9]\d*)", reference)
    if not match:
        raise IntakeFileError()
    result = 0
    for char in match[1]:
        result = result * 26 + ord(char) - 64
    if result > MAX_COLUMNS or int(match[2]) > MAX_ROWS + 1:
        raise IntakeFileError()
    return result - 1


def parse_xlsx(content: bytes) -> Workbook:
    with ZipFile(BytesIO(content)) as archive:
        entries = archive.infolist()
        if (
            len(entries) > MAX_ENTRIES
            or len({e.filename for e in entries}) != len(entries)
            or sum(e.file_size for e in entries) > MAX_EXPANDED_BYTES
        ):
            raise IntakeFileError()
        documents: dict[str, ET.Element] = {}
        for entry in entries:
            path = entry.filename
            low = path.lower()
            if (
                entry.flag_bits & 1
                or "\\" in path
                or path.startswith("/")
                or ".." in PurePosixPath(path).parts
                or ":" in path
                or any(v in low for v in ("vba", "macro", "externallink", "embeddings", "activex"))
            ):
                raise IntakeFileError()
            if low.endswith((".xml", ".rels")):
                root = xml(archive.read(entry))
                if "macroenabled" in ET.tostring(root, encoding="unicode").lower():
                    raise IntakeFileError()
                if low.endswith(".rels") and any(
                    item.get("TargetMode", "").lower() == "external" for item in root
                ):
                    raise IntakeFileError()
                documents[path] = root
        book = documents["xl/workbook.xml"]
        relationships = documents["xl/_rels/workbook.xml.rels"]
        targets = {r.get("Id"): r.get("Target", "") for r in relationships}
        shared: list[str] = []
        if "xl/sharedStrings.xml" in documents:
            shared = ["".join(node.itertext()) for node in documents["xl/sharedStrings.xml"]]
        date_styles: set[int] = set()
        styles = documents.get("xl/styles.xml")
        if styles is not None:
            formats = {
                int(n.get("numFmtId", "0")): n.get("formatCode", "")
                for n in styles.findall(f"{NS}numFmts/{NS}numFmt")
            }
            for index, node in enumerate(styles.findall(f"{NS}cellXfs/{NS}xf")):
                fmt = int(node.get("numFmtId", "0"))
                if fmt in range(14, 23) or re.search(r"[yd]", formats.get(fmt, ""), re.I):
                    date_styles.add(index)
        epoch_1904 = book.find(f"{NS}workbookPr")
        is_1904 = epoch_1904 is not None and epoch_1904.get("date1904") in {"1", "true"}
        sheets = book.findall(f"{NS}sheets/{NS}sheet")
        if not sheets or len(sheets) > MAX_SHEETS:
            raise IntakeFileError()
        result: list[Sheet] = []
        for index, sheet in enumerate(sheets):
            target = targets[sheet.get(f"{REL}id")]
            path = target.lstrip("/") if target.startswith("/") else "xl/" + target
            if ".." in PurePosixPath(path).parts:
                raise IntakeFileError()
            root = documents[path]
            if root.findall(f".//{NS}f") or root.findall(f".//{NS}hyperlink"):
                raise IntakeFileError()
            rows: list[list[str]] = []
            for row in root.findall(f"{NS}sheetData/{NS}row"):
                row_no = int(row.get("r", "0"))
                if row_no != len(rows) + 1 or row_no > MAX_ROWS + 1:
                    raise IntakeFileError()
                values: dict[int, str] = {}
                for cell in row.findall(f"{NS}c"):
                    reference = cell.get("r", "")
                    if not reference.endswith(str(row_no)):
                        raise IntakeFileError()
                    col = column_number(reference)
                    if col in values:
                        raise IntakeFileError()
                    value = cell.findtext(f"{NS}v", "")
                    kind = cell.get("t", "n")
                    if kind == "s":
                        offset = int(value)
                        if offset < 0:
                            raise IntakeFileError()
                        value = shared[offset]
                    elif kind == "inlineStr":
                        value = "".join(n.text or "" for n in cell.findall(f"{NS}is//{NS}t"))
                    elif kind == "e":
                        raise IntakeFileError()
                    elif kind == "n" and value and int(cell.get("s", "0")) in date_styles:
                        serial = Decimal(value)
                        if serial != serial.to_integral_value() or serial < 0 or serial == 60:
                            raise IntakeFileError()
                        days = int(serial)
                        origin = date(1904, 1, 1) if is_1904 else date(1899, 12, 31)
                        value = (
                            origin + timedelta(days=days - (not is_1904 and days > 60))
                        ).isoformat()
                    values[col] = safe_cell(value)
                width = len(rows[0]) if rows else max(values, default=-1) + 1
                if any(c >= width for c in values):
                    raise IntakeFileError()
                rows.append([values.get(c, "") for c in range(width)])
            result.append(table(index, sheet.get("name", "Sheet"), rows))
        if sum(len(s.rows) for s in result) > MAX_ROWS:
            raise IntakeFileError()
        return Workbook(tuple(result), "OOXML_UTF8")


def parse_file(filename: str, content: bytes, content_type: str) -> Workbook:
    validate_filename(filename)
    if not content or len(content) > MAX_BYTES:
        raise IntakeFileError()
    extension = PurePosixPath(filename).suffix.lower()
    try:
        if extension == ".csv":
            if content_type not in {"text/csv", "text/plain", "application/octet-stream"}:
                raise IntakeFileError()
            reader = csv.reader(StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
            rows: list[list[str]] = []
            for row in reader:
                if len(rows) >= MAX_ROWS + 1 or len(row) > MAX_COLUMNS:
                    raise IntakeFileError()
                rows.append(row)
            return Workbook(
                (table(0, "CSV", rows),),
                "UTF-8-BOM" if content.startswith(b"\xef\xbb\xbf") else "UTF-8",
            )
        if extension != ".xlsx" or content_type != XLSX_MIME:
            raise IntakeFileError()
        if not content.startswith(b"PK\x03\x04"):
            raise IntakeFileError()
        return parse_xlsx(content)
    except IntakeFileError:
        raise
    except (
        UnicodeError,
        csv.Error,
        BadZipFile,
        ET.ParseError,
        ValueError,
        KeyError,
        IndexError,
        OverflowError,
        RuntimeError,
        OSError,
    ):
        raise IntakeFileError() from None
