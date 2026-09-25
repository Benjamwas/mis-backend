"""Payslip PDF rendering with reportlab."""
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def render_payslip_pdf(payslip):
    """Render a payslip to a PDF saved under media/payslips.

    Returns (pdf_path_or_url, created_book).
    """
    import os

    from django.conf import settings

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"PAYSLIP", styles["Title"]))
    story.append(Paragraph(f"{payslip.employee.full_name}", styles["Heading2"]))
    story.append(Paragraph(f"Employee No: {payslip.employee.employee_number}", styles["Normal"]))
    story.append(Paragraph(f"Period: {payslip.payroll_period.name}", styles["Normal"]))
    story.append(Paragraph(f"Generated: {date.today().isoformat()}", styles["Normal"]))
    story.append(Spacer(1, 12))

    rows = [["Item", "Type", "Amount (KES)"]]
    for item in payslip.items.all():
        rows.append([item.description, item.item_type, f"{item.amount:.2f}"])
    rows.append(["Gross Salary", "TOTAL", f"{payslip.gross_salary:.2f}"])
    rows.append(["Total Deductions", "TOTAL", f"{payslip.total_deductions:.2f}"])
    rows.append(["Net Salary", "NET", f"{payslip.net_salary:.2f}"])

    table = Table(rows)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16a34a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story.append(table)

    doc.build(story)
    pdf_bytes = buffer.getvalue()

    relative = f"payslips/{payslip.id}.pdf"
    abs_path = os.path.join(settings.MEDIA_ROOT, relative)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as fh:
        fh.write(pdf_bytes)

    if settings.MEDIA_URL:
        from urllib.parse import urljoin

        payslip.pdf_url = urljoin(settings.MEDIA_URL, relative)
    else:
        payslip.pdf_url = relative
    payslip.save(update_fields=["pdf_url", "updated_at"])
    return payslip.pdf_url, True