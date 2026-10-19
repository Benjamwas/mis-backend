"""Receipt PDF rendering with reportlab — branded SALA receipt."""
import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, HRFlowable
)
from django.conf import settings

# Brand colours
NAVY = colors.HexColor("#152847")
NAVY_MID = colors.HexColor("#1F3A5F")
GOLD = colors.HexColor("#F4C243")
GOLD_LIGHT = colors.HexColor("#FBD574")
WHITE = colors.white
LIGHT_BG = colors.HexColor("#F5F7FA")
TEXT_DARK = colors.HexColor("#1A2233")
TEXT_MUTED = colors.HexColor("#4B5568")


def _styles():
    base = getSampleStyleSheet()
    s = {}
    s["school"] = ParagraphStyle(
        "school", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=16, leading=20,
        textColor=WHITE, alignment=TA_LEFT,
    )
    s["tagline"] = ParagraphStyle(
        "tagline", parent=base["Normal"],
        fontName="Helvetica", fontSize=8, leading=11,
        textColor=GOLD, alignment=TA_LEFT,
    )
    s["address"] = ParagraphStyle(
        "address", parent=base["Normal"],
        fontName="Helvetica", fontSize=7.5, leading=10,
        textColor=colors.HexColor("#B3C4D8"), alignment=TA_LEFT,
    )
    s["title"] = ParagraphStyle(
        "title", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=13, leading=16,
        textColor=NAVY, alignment=TA_CENTER,
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle", parent=base["Normal"],
        fontName="Helvetica", fontSize=8.5, leading=12,
        textColor=TEXT_MUTED, alignment=TA_CENTER,
    )
    s["label"] = ParagraphStyle(
        "label", parent=base["Normal"],
        fontName="Helvetica", fontSize=8.5, leading=12,
        textColor=TEXT_MUTED, alignment=TA_LEFT,
    )
    s["value"] = ParagraphStyle(
        "value", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=9, leading=12,
        textColor=TEXT_DARK, alignment=TA_LEFT,
    )
    s["cell"] = ParagraphStyle(
        "cell", parent=base["Normal"],
        fontName="Helvetica", fontSize=9, leading=12,
        textColor=TEXT_DARK,
    )
    s["cell_bold"] = ParagraphStyle(
        "cell_bold", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=9.5, leading=13,
        textColor=TEXT_DARK,
    )
    s["total_label"] = ParagraphStyle(
        "total_label", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=10, leading=13,
        textColor=WHITE, alignment=TA_RIGHT,
    )
    s["total_value"] = ParagraphStyle(
        "total_value", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=13, leading=16,
        textColor=GOLD, alignment=TA_RIGHT,
    )
    s["footer"] = ParagraphStyle(
        "footer", parent=base["Normal"],
        fontName="Helvetica", fontSize=7, leading=9.5,
        textColor=TEXT_MUTED, alignment=TA_CENTER,
    )
    s["muted"] = ParagraphStyle(
        "muted", parent=base["Normal"],
        fontName="Helvetica", fontSize=8, leading=11,
        textColor=TEXT_MUTED, alignment=TA_LEFT,
    )
    return s


def render_receipt_pdf(receipt):
    """Render a branded single-page receipt PDF. Returns (url, True)."""
    buffer = io.BytesIO()
    page_w, page_h = A4
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=0, bottomMargin=14 * mm,
    )
    st = _styles()
    story = []
    school = receipt.school
    school_name = school.name if school else "St. Ann Lifred Academy Schools"
    school_addr = (school.address if school else "") or "Kiambu Road, Runda Gardens, Nairobi"
    school_phone = (school.phone if school else "") or ""
    school_email = (school.email if school else "") or ""
    school_motto = (school.motto if school else "") or "Learn. Grow. Lead."
    school_logo = (school.logo_url if school else "") or ""

    # ── Header band (navy) ──────────────────────────────────────────────
    logo_cell = ""
    if school_logo and school_logo.startswith(("http", "/")):
        try:
            if school_logo.startswith("/"):
                local = os.path.join(settings.MEDIA_ROOT, school_logo.lstrip("/"))
                if os.path.exists(local):
                    logo_cell = Image(local, width=38, height=38)
        except Exception:
            logo_cell = ""

    header_left = [
        Paragraph(school_name, st["school"]),
        Paragraph(school_motto.upper(), st["tagline"]),
        Spacer(1, 3),
        Paragraph(school_addr, st["address"]),
    ]
    if school_phone or school_email:
        contact = " · ".join(x for x in [school_phone, school_email] if x)
        header_left.append(Paragraph(contact, st["address"]))

    header_right = [
        Paragraph("OFFICIAL RECEIPT", st["tagline"]),
        Spacer(1, 2),
        Paragraph(f"Receipt No<br/><b>{receipt.receipt_number}</b>", ParagraphStyle(
            "rn", parent=st["address"], fontSize=9, leading=12, textColor=WHITE, alignment=TA_RIGHT,
        )),
    ]

    left_col = [logo_cell, Spacer(1, 2)] if logo_cell else []
    left_col += header_left

    header_data = [[left_col, header_right]]
    header_table = Table(header_data, colWidths=[page_w - 36 * mm - 70, 70])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (0, 0), 14),
        ("RIGHTPADDING", (-1, 0), (-1, 0), 14),
    ]))
    story.append(header_table)

    # Gold accent strip
    gold_strip = Table([[""]], colWidths=[page_w - 36 * mm], rowHeights=[4])
    gold_strip.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GOLD)]))
    story.append(gold_strip)
    story.append(Spacer(1, 16))

    # ── Title ───────────────────────────────────────────────────────────
    story.append(Paragraph("Payment Receipt", st["title"]))
    story.append(Spacer(1, 2))
    story.append(Paragraph(
        f"Issued {receipt.issued_at.strftime('%d %B %Y at %H:%M')}", st["subtitle"],
    ))
    story.append(Spacer(1, 14))

    # ── Details grid ────────────────────────────────────────────────────
    method_label = {
        "M_PESA": "M-Pesa", "M_PESA_PULL": "M-Pesa Pull",
        "BANK_TRANSFER": "Bank Transfer", "CARD": "Card", "CASH": "Cash",
    }.get(receipt.method, receipt.method)

    def row(label, value):
        return [
            Paragraph(label, st["label"]),
            Paragraph(str(value or "—"), st["value"]),
        ]

    details = [
        row("Student", receipt.student.full_name),
        row("Admission No", receipt.student.admission_number),
        row("Payment method", method_label),
        row("Transaction ref", receipt.payment.transaction_ref if receipt.payment else "—"),
    ]
    details_table = Table(details, colWidths=[(page_w - 36 * mm) * 0.35, (page_w - 36 * mm) * 0.65])
    details_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#E2E8F0")),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 14))

    # ── Amount table ────────────────────────────────────────────────────
    amount = f"{receipt.amount:,.2f}"
    amount_data = [
        [Paragraph("Description", st["cell_bold"]), Paragraph("Amount (KES)", st["cell_bold"])],
        [Paragraph("School fees payment", st["cell"]), Paragraph(amount, st["cell"])],
    ]
    amount_table = Table(amount_data, colWidths=[(page_w - 36 * mm) * 0.6, (page_w - 36 * mm) * 0.4])
    amount_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    story.append(amount_table)
    story.append(Spacer(1, 0))

    # Total band (navy with gold amount)
    total_data = [[
        Paragraph("TOTAL PAID", st["total_label"]),
        Paragraph(f"KES {amount}", st["total_value"]),
    ]]
    total_table = Table(total_data, colWidths=[(page_w - 36 * mm) * 0.6, (page_w - 36 * mm) * 0.4])
    total_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY_MID),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (0, 0), 10),
        ("RIGHTPADDING", (-1, 0), (-1, 0), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(total_table)
    story.append(Spacer(1, 18))

    # ── Thank you ───────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=GOLD))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Thank you for your payment. This is a computer-generated receipt and does not require a signature.",
        st["footer"],
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"{school_name} · {school_addr}", st["footer"]))

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
