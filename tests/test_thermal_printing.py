import subprocess

from app import thermal_printing
from app.labels import LabelItem
from app.thermal_printing import (
    LABEL_HEIGHT_DOTS,
    LABEL_WIDTH_DOTS,
    build_thermal_label_tspl,
    print_thermal_label,
    render_thermal_label,
)


def test_thermal_label_has_expected_size_and_single_qr_layout():
    item = LabelItem(object_type="Палета", code="PLT-000123", title="Демо")

    image = render_thermal_label(item)

    assert image.size == (LABEL_WIDTH_DOTS, LABEL_HEIGHT_DOTS)
    assert image.mode == "1"
    assert image.getextrema() == (0, 255)


def test_thermal_label_tspl_contains_one_bitmap_and_one_print_command():
    item = LabelItem(
        object_type="Ячейка",
        code="WH01-FR01-R01-B01-L01-P01",
        title="Адрес хранения",
    )

    payload = build_thermal_label_tspl(item)

    assert payload.startswith(b"SIZE 47 mm,25 mm\r\nGAP 2 mm,0 mm\r\n")
    assert payload.count(b"BITMAP ") == 1
    assert payload.endswith(b"\r\nPRINT 1,1\r\n")


def test_print_job_id_is_parsed_from_localized_cups_output(monkeypatch):
    item = LabelItem(object_type="Палета", code="PLT-000123", title="Демо")
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="id запроса ATOL_TT42-27 (0 файл.)\n".encode(),
        stderr=b"",
    )
    monkeypatch.setattr(thermal_printing.shutil, "which", lambda _: "/usr/bin/lp")
    monkeypatch.setattr(thermal_printing.subprocess, "run", lambda *args, **kwargs: completed)

    result = print_thermal_label(item)

    assert result == {"queue": "ATOL_TT42", "job_id": "ATOL_TT42-27"}
