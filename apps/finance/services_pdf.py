"""Receipt PDF rendering with reportlab."""
import io
import os
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from django.conf import settings


def render_receipt_pdf(receipt):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"SALA School Digital Platform", styles["Title"]))
    story.append(Paragraph(f"OFFICIAL RECEIPT", styles["Heading2"]))
    story.append(Paragraph(f"Receipt No: {receipt.receipt_number}", styles["Normal"]))
    story.append(Paragraph(f"Student: {receipt.student.full_name}", styles["Normal"]))
    story.append(Paragraph(f"Admission No: {receipt.student.admission_number}", styles["Normal"]))
    story.append(Paragraph(f"Date: {receipt.issued_at.strftime('%d-%b-%Y %H:%M')}", styles["Normal"]))
    story.append(Paragraph(f"Payment Method: {receipt.method}", styles["Normal"]))
    story.append(Paragraph(f"Transaction Ref: {receipt.payment.transaction_ref}", styles["Normal"]))
    story.append(Spacer(1, 12))

    table_data = [["Description", "Amount (KES)"]]
    table_data.append(["Received payment", f"{receipt.amount:.2f}"])
    table_data.append(["TOTAL", f"{receipt.amount:.2f}"])
    table = Table(table_data)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16a34a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    story.append(table)
    story.append(Spacer(1, 24))
    story.append(Paragraph(f"Thank you for your payment.", styles["Normal"]))

    doc.build(story)
    pdf_bytes = buffer.getvalue()

    relative = f"receipts/{receipt.receipt_number}.pdf"
    abs_path = os.path.join(settings.MEDIA_ROOT, relative)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as fh:
        fh.write(pdf_bytes)

    from urllib.parse import urljoin

    url = urljoin(settings.MEDIA_URL or "/media/", relative)
    return url, True