from types import SimpleNamespace

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
    marker = b"BITMAP 0,0,47,200,0,"
    bitmap_start = payload.index(marker) + len(marker)
    assert payload[bitmap_start] == 0xFF


def test_print_label_sends_tspl_directly_to_printer_socket(monkeypatch):
    item = LabelItem(object_type="Палета", code="PLT-000123", title="Демо")
    sent: list[bytes] = []

    class FakePrinter:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def sendall(self, payload):
            sent.append(payload)

    def fake_connection(destination, timeout):
        assert destination == ("192.0.2.204", 9100)
        assert timeout == 3
        return FakePrinter()

    monkeypatch.setattr(
        thermal_printing,
        "get_settings",
        lambda: SimpleNamespace(
            thermal_printer_host="192.0.2.204",
            thermal_printer_port=9100,
            thermal_printer_queue="ATOL_TT42",
        ),
    )
    monkeypatch.setattr(thermal_printing.socket, "create_connection", fake_connection)

    result = print_thermal_label(item)

    assert result["queue"] == "ATOL_TT42"
    assert result["job_id"].startswith("ATOL_TT42-")
    assert len(sent) == 1
    assert sent[0].startswith(b"SIZE 47 mm,25 mm\r\n")
