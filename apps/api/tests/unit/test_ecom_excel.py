from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import PatternFill

from kitframe.content.ecom_excel import (
    apply_row_fill,
    list_rows_to_fill,
    load_workbook_bytes,
    workbook_to_bytes,
)


def _sample_wb() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws["A3"] = "Referencia"
    ws["C3"] = "Título"
    ws["T3"] = "Título ES"
    ws["U3"] = "Desccripción ES"
    # green-ish row to fill
    ws["A4"] = "SKU-GREEN"
    ws["C4"] = "TEE WALL TEST"
    ws["D4"] = "TEE WALL"
    ws["E4"] = "Propis"
    # red row (skip)
    ws["A5"] = "SKU-RED"
    ws["C5"] = "ALREADY DONE"
    ws["A5"].fill = PatternFill(start_color="FFFF0000", end_color="FFFF0000", fill_type="solid")
    ws["U5"] = "Already filled"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_list_rows_skips_red_and_filled() -> None:
    wb = load_workbook_bytes(_sample_wb())
    rows = list_rows_to_fill(wb)
    assert [r.ref for r in rows] == ["SKU-GREEN"]


def test_apply_row_fill_writes_es() -> None:
    wb = load_workbook_bytes(_sample_wb())
    apply_row_fill(
        wb,
        4,
        {
            "ES": {
                "title": "Camiseta test",
                "description": "Descripción de prueba",
                "fit": "Regular fit",
                "measures": "",
                "care": "Algodón",
                "meta_title": "Meta",
                "meta_description": "Meta desc",
            }
        },
    )
    data = workbook_to_bytes(wb)
    wb2 = load_workbook_bytes(data)
    assert wb2.active["T4"].value == "Camiseta test"
    assert wb2.active["U4"].value == "Descripción de prueba"
    assert wb2.active["BK4"].value == "Meta"
    assert wb2.active["BR4"].value == "Meta desc"
