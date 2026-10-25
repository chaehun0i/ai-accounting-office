"""Deterministic report datasets rendered into PDF, XLSX or UTF-8 CSV."""

import csv
from dataclasses import dataclass
from io import BytesIO, StringIO

from openpyxl import Workbook  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]


@dataclass(frozen=True)
class ReportDocument:
    metadata: tuple[tuple[str, str], ...]
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


def render_csv(document: ReportDocument) -> bytes:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow((*[key for key, _ in document.metadata], *document.columns))
    prefix = tuple(value for _, value in document.metadata)
    for row in document.rows:
        writer.writerow((*prefix, *row))
    return stream.getvalue().encode("utf-8")


def render_xlsx(document: ReportDocument) -> bytes:
    workbook = Workbook()
    summary = workbook.active
    assert summary is not None
    summary.title = "Summary"
    for key, value in document.metadata:
        summary.append((key, value))
    data = workbook.create_sheet("Dataset")
    data.append(document.columns)
    for row in document.rows:
        # Decimal facts remain strings; Excel's 15-digit float limit cannot alter them.
        data.append(row)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def render_pdf(document: ReportDocument) -> bytes:
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4, pageCompression=1)
    pdf.setTitle("AI Accounting Office Report")
    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    font = "HYSMyeongJo-Medium"
    page_width, page_height = A4
    y = page_height - 42

    def line(value: str) -> None:
        nonlocal y
        if y < 44:
            pdf.showPage()
            y = page_height - 42
        pdf.setFont(font, 9)
        pdf.drawString(40, y, value[:105])
        y -= 15

    for key, value in document.metadata:
        line(f"{key}: {value}")
    y -= 12
    line("  |  ".join(document.columns))
    for row in document.rows:
        line("  |  ".join(row))
    pdf.setFont(font, 8)
    pdf.drawRightString(page_width - 40, 30, "AI Accounting Office")
    pdf.save()
    return stream.getvalue()


def render(document: ReportDocument, format: str) -> tuple[bytes, str, str]:
    if format == "PDF":
        return render_pdf(document), "application/pdf", "pdf"
    if format == "XLSX":
        return (
            render_xlsx(document),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        )
    if format == "CSV":
        return render_csv(document), "text/csv; charset=utf-8", "csv"
    raise ValueError("Unsupported report format")
