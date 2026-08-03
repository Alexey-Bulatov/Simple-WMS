from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import qrcode
from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas


FONT_REGULAR = "WMS-Regular"
FONT_BOLD = "WMS-Bold"


@dataclass(frozen=True)
class LabelItem:
    object_type: str
    code: str
    title: str
    lines: tuple[str, ...] = ()


def register_fonts() -> tuple[str, str]:
    font_roots = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
    ]
    regular_names = {
        "DejaVuSans.ttf",
        "NotoSans-Regular.ttf",
        "LiberationSans-Regular.ttf",
        "FreeSans.ttf",
        "Arial Unicode.ttf",
        "Arial.ttf",
    }
    bold_names = {
        "DejaVuSans-Bold.ttf",
        "NotoSans-Bold.ttf",
        "LiberationSans-Bold.ttf",
        "FreeSansBold.ttf",
        "Arial Bold.ttf",
    }
    available_fonts = [path for root in font_roots if root.exists() for path in root.rglob("*.ttf")]
    regular_candidates = [path for path in available_fonts if path.name in regular_names]
    bold_candidates = [path for path in available_fonts if path.name in bold_names]
    regular = next((path for path in regular_candidates if path.exists()), None)
    bold = next((path for path in bold_candidates if path.exists()), None)
    if regular is None:
        raise RuntimeError("Не найден TTF-шрифт с кириллицей для PDF-этикеток")
    if bold is None:
        bold = regular
    if regular and FONT_REGULAR not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular)))
    if bold and FONT_BOLD not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))
    return FONT_REGULAR, FONT_BOLD


def qr_reader(value: str) -> ImageReader:
    qr = qrcode.QRCode(version=None, box_size=8, border=1)
    qr.add_data(value)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return ImageReader(image)


def fit_text(canvas: Canvas, text: str, font_name: str, max_size: float, min_size: float, width: float) -> float:
    size = max_size
    while size > min_size and canvas.stringWidth(text, font_name, size) > width:
        size -= 0.5
    return size


def draw_code128(canvas: Canvas, code: str, x: float, y: float, width: float) -> None:
    barcode = Code128(code, barHeight=8 * mm, barWidth=0.24 * mm, humanReadable=False)
    scale = min(1.0, width / barcode.width)
    canvas.saveState()
    canvas.translate(x, y)
    canvas.scale(scale, 1)
    barcode.drawOn(canvas, 0, 0)
    canvas.restoreState()


def draw_label(canvas: Canvas, item: LabelItem, x: float, y: float, width: float, height: float, font: str, bold: str) -> None:
    pad = 5 * mm
    qr_size = 24 * mm
    canvas.setStrokeColor(colors.HexColor("#9aa4b2"))
    canvas.setLineWidth(0.6)
    canvas.roundRect(x, y, width, height, 3 * mm, stroke=1, fill=0)

    canvas.setFillColor(colors.HexColor("#101828"))
    canvas.setFont(bold, 8)
    canvas.drawString(x + pad, y + height - pad - 2 * mm, item.object_type.upper())

    code_width = width - qr_size - pad * 3
    code_size = fit_text(canvas, item.code, bold, 18, 9, code_width)
    canvas.setFont(bold, code_size)
    canvas.drawString(x + pad, y + height - pad - 10 * mm, item.code)

    canvas.setFont(font, 8)
    canvas.setFillColor(colors.HexColor("#344054"))
    canvas.drawString(x + pad, y + height - pad - 18 * mm, item.title[:62])

    line_y = y + height - pad - 25 * mm
    for line in item.lines[:4]:
        canvas.setFont(font, 7.4)
        canvas.drawString(x + pad, line_y, line[:76])
        line_y -= 4.2 * mm

    qr_x = x + width - pad - qr_size
    qr_y = y + height - pad - qr_size
    canvas.drawImage(qr_reader(item.code), qr_x, qr_y, qr_size, qr_size, mask="auto")
    draw_code128(canvas, item.code, x + pad, y + pad + 2 * mm, width - pad * 2)
    canvas.setFont(font, 6)
    canvas.setFillColor(colors.HexColor("#667085"))
    canvas.drawCentredString(x + width / 2, y + pad - 1 * mm, "QR / Code128")


def build_labels_pdf(items: list[LabelItem], *, title: str) -> bytes:
    font, bold = register_fonts()
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    margin_x = 10 * mm
    margin_y = 12 * mm
    gap = 5 * mm
    label_width = (page_width - margin_x * 2 - gap) / 2
    label_height = 58 * mm
    labels_per_page = 4 * 2

    for index, item in enumerate(items):
        page_index = index % labels_per_page
        if page_index == 0:
            if index:
                canvas.showPage()
            canvas.setTitle(title)
            canvas.setFont(bold, 11)
            canvas.setFillColor(colors.HexColor("#101828"))
            canvas.drawString(margin_x, page_height - 7 * mm, title)

        row = page_index // 2
        col = page_index % 2
        x = margin_x + col * (label_width + gap)
        y = page_height - 14 * mm - (row + 1) * label_height - row * gap
        draw_label(canvas, item, x, y, label_width, label_height, font, bold)

    if not items:
        canvas.setFont(bold, 14)
        canvas.drawString(margin_x, page_height - 25 * mm, "Нет данных для печати")
    canvas.save()
    return buffer.getvalue()
