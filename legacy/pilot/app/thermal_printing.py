from __future__ import annotations

import socket
import uuid
from functools import lru_cache
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

from app.core.config import get_settings
from app.labels import LabelItem


LABEL_WIDTH_DOTS = 376
LABEL_HEIGHT_DOTS = 200
LABEL_WIDTH_MM = 47
LABEL_HEIGHT_MM = 25
LABEL_GAP_MM = 2
QR_AREA_WIDTH = 154
RIGHT_MARGIN = 12


class ThermalPrintError(RuntimeError):
    pass


@lru_cache
def _font_path(bold: bool) -> Path:
    font_roots = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
    ]
    names = (
        (
            "DejaVuSansCondensed-Bold.ttf",
            "DejaVuSans-Bold.ttf",
            "NotoSans-Bold.ttf",
            "Arial Narrow Bold.ttf",
            "Arial Bold.ttf",
        )
        if bold
        else (
            "DejaVuSansCondensed.ttf",
            "DejaVuSans.ttf",
            "NotoSans-Regular.ttf",
            "Arial Narrow.ttf",
            "Arial.ttf",
        )
    )
    for root in font_roots:
        if not root.exists():
            continue
        available = {path.name: path for path in root.rglob("*.ttf")}
        for name in names:
            if name in available:
                return available[name]
    raise ThermalPrintError("Не найден TTF-шрифт для термоэтикетки")


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_font_path(bold)), size=size)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _wrap_code(draw: ImageDraw.ImageDraw, code: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    remaining = code
    lines: list[str] = []
    while remaining:
        if _text_width(draw, remaining, font) <= max_width:
            lines.append(remaining)
            break

        end = 1
        while end <= len(remaining) and _text_width(draw, remaining[:end], font) <= max_width:
            end += 1
        end = max(1, end - 1)
        hyphen = remaining.rfind("-", 0, end + 1)
        if hyphen >= max(2, end // 2):
            end = hyphen + 1
        lines.append(remaining[:end])
        remaining = remaining[end:]
    return lines


def _fit_code(
    draw: ImageDraw.ImageDraw,
    code: str,
    max_width: int,
    max_height: int,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    for size in range(30, 13, -1):
        font = _font(size, bold=True)
        lines = _wrap_code(draw, code, font, max_width)
        line_height = size + 4
        if len(lines) <= 3 and len(lines) * line_height <= max_height:
            return font, lines, line_height
    font = _font(13, bold=True)
    return font, _wrap_code(draw, code, font, max_width)[:3], 17


def _qr_image(value: str, max_size: int = 146) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=4,
    )
    qr.add_data(value)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("L")
    scale = max(1, max_size // image.width)
    return image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)


def render_thermal_label(item: LabelItem) -> Image.Image:
    image = Image.new("L", (LABEL_WIDTH_DOTS, LABEL_HEIGHT_DOTS), color=255)
    draw = ImageDraw.Draw(image)

    qr = _qr_image(item.code)
    qr_x = (QR_AREA_WIDTH - qr.width) // 2
    qr_y = (LABEL_HEIGHT_DOTS - qr.height) // 2
    image.paste(qr, (qr_x, qr_y))

    divider_x = QR_AREA_WIDTH
    draw.line((divider_x, 10, divider_x, LABEL_HEIGHT_DOTS - 10), fill=0, width=2)

    content_x = divider_x + 12
    content_width = LABEL_WIDTH_DOTS - content_x - RIGHT_MARGIN
    type_font = _font(21, bold=True)
    object_type = item.object_type.upper()
    while _text_width(draw, object_type, type_font) > content_width and type_font.size > 14:
        type_font = _font(type_font.size - 1, bold=True)
    draw.text((content_x, 15), object_type, font=type_font, fill=0)
    draw.line((content_x, 48, LABEL_WIDTH_DOTS - RIGHT_MARGIN, 48), fill=0, width=1)

    code_font, code_lines, line_height = _fit_code(draw, item.code, content_width, 124)
    code_height = len(code_lines) * line_height
    code_y = 54 + max(0, (LABEL_HEIGHT_DOTS - 60 - code_height) // 2)
    for line in code_lines:
        draw.text((content_x, code_y), line, font=code_font, fill=0)
        code_y += line_height

    return image.point(lambda pixel: 255 if pixel > 160 else 0, mode="1")


def build_thermal_label_tspl(item: LabelItem) -> bytes:
    image = render_thermal_label(item)
    row_bytes = LABEL_WIDTH_DOTS // 8
    bitmap = image.tobytes()
    header = (
        f"SIZE {LABEL_WIDTH_MM} mm,{LABEL_HEIGHT_MM} mm\r\n"
        f"GAP {LABEL_GAP_MM} mm,0 mm\r\n"
        "DIRECTION 1\r\n"
        "REFERENCE 0,0\r\n"
        "CLS\r\n"
        f"BITMAP 0,0,{row_bytes},{LABEL_HEIGHT_DOTS},0,"
    ).encode("ascii")
    return header + bitmap + b"\r\nPRINT 1,1\r\n"


def print_thermal_label(item: LabelItem) -> dict[str, str]:
    settings = get_settings()
    destination = (settings.thermal_printer_host, settings.thermal_printer_port)

    try:
        with socket.create_connection(destination, timeout=3) as printer:
            printer.sendall(build_thermal_label_tspl(item))
    except OSError as exc:
        raise ThermalPrintError(
            f"Принтер {settings.thermal_printer_host}:{settings.thermal_printer_port} недоступен"
        ) from exc

    job_id = f"{settings.thermal_printer_queue}-{uuid.uuid4().hex[:8].upper()}"
    return {"queue": settings.thermal_printer_queue, "job_id": job_id}
