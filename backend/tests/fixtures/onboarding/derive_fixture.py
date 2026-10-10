"""native Sheet의 불변 snapshot에서 온보딩 전용 파생 v1을 생성합니다.

원본을 수정하지 않습니다. 별도 금융·세무 Sheet와 수식은 실행하거나 이관하지 않습니다.
"""

from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from app.onboarding.infrastructure.template import template_sheets, workbook_bytes

ROOT = Path(__file__).parent
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def source_rows() -> dict[str, list[dict[str, str]]]:
    result = {}
    selected = {
        "Company",
        "COA",
        "Counterparties",
        "Opening_Balances",
        "Fixed_Assets",
        "Products",
        "Opening_Inventory",
    }
    with ZipFile(ROOT / "sample-company-2025-v1.xlsx") as archive:
        book = ET.fromstring(archive.read("xl/workbook.xml"))
        targets = {
            n.get("Id"): n.get("Target", "")
            for n in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        }
        strings = [
            "".join(n.itertext()) for n in ET.fromstring(archive.read("xl/sharedStrings.xml"))
        ]
        for sheet in book.findall(f"{NS}sheets/{NS}sheet"):
            name = sheet.get("name", "")
            if name not in selected:
                continue
            target = targets[
                sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            ]
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            rows = []
            for node in ET.fromstring(archive.read(target)).findall(f"{NS}sheetData/{NS}row"):
                values = []
                for cell in node.findall(f"{NS}c"):
                    value = cell.findtext(f"{NS}v", "")
                    if cell.get("t") == "s":
                        value = strings[int(value)]
                    elif cell.get("t") == "inlineStr":
                        value = "".join(n.text or "" for n in cell.findall(f"{NS}is//{NS}t"))
                    values.append(value)
                if any(values):
                    rows.append(values)
            result[name] = [dict(zip(rows[0], row, strict=False)) for row in rows[1:]]
    return result


def derive() -> bytes:
    rows = source_rows()
    sheets = template_sheets(datetime(2025, 1, 1, tzinfo=UTC))
    company = rows["Company"][0]
    mapped = {
        "company_name": company["company_name"],
        "taxpayer_type": company["taxpayer_type"],
        "opening_date": company["fiscal_year_start"],
        "timezone": company["timezone"],
    }
    sheets["Company"].append([mapped.get(code, "") for code in sheets["Company"][0]])
    # 원본의 framework 이름은 공식 양식 코드로 명시적으로 변환합니다.
    settings = {
        "functional_currency_code": company["functional_currency"],
        "fiscal_year_start_month": "1",
        "accounting_framework_code": "K_GAAP",
        "reporting_taxonomy_code": "STANDARD",
        "journal_number_prefix": "J",
    }
    sheets["Accounting_Settings"].append(
        [settings.get(code, "") for code in sheets["Accounting_Settings"][0]]
    )
    for source, target in (
        ("COA", "COA"),
        ("Counterparties", "Counterparties"),
        ("Opening_Balances", "Opening_Balances"),
        ("Fixed_Assets", "Fixed_Assets"),
        ("Products", "Inventory_Items"),
        ("Opening_Inventory", "Opening_Inventory"),
    ):
        for original in rows[source]:
            row = dict(original)
            if source == "COA":
                row["posting_allowed"] = (
                    "true" if row["posting_allowed"] in {"1", "1.0", "TRUE"} else "false"
                )
            if source == "Counterparties":
                row["role_code"], row["counterparty_type"] = row["counterparty_type"], "BUSINESS"
            if source == "Products":
                row["cost_method"] = (
                    "WEIGHTED_AVERAGE"
                    if row["cost_method"] == "MOVING_WEIGHTED_AVERAGE"
                    else row["cost_method"]
                )
            if source == "Opening_Inventory":
                row["opening_quantity"], row["opening_unit_cost"] = (
                    row["quantity"],
                    row["unit_cost"],
                )
            sheets[target].append([row.get(code, "") for code in sheets[target][0]])
    return workbook_bytes(sheets)


if __name__ == "__main__":
    (ROOT / "onboarding-syn-mfg-2025-derived-v1.xlsx").write_bytes(derive())
