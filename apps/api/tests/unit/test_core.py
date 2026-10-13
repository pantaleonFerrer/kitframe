from __future__ import annotations

from kitframe.qc.color import delta_e2000
from kitframe.shopify.mapping import render_filename
from kitframe.studio.rights import _normalize
from kitframe.workflow.transitions import NEXT_PHASE


def test_delta_e_identical() -> None:
    assert delta_e2000((50, 0, 0), (50, 0, 0)) == 0


def test_normalize_rights() -> None:
    assert "jugador" in _normalize("Jugadór, Ejemplo!")


def test_filename_slug() -> None:
    name = render_filename(
        "{reference}-{shot}-{index}-{channel}",
        reference="FCB 001",
        sku="X",
        color="red",
        shot="product_front",
        index=1,
        channel="shopify",
    )
    assert " " not in name
    assert name.islower() or "-" in name


def test_phase_order() -> None:
    assert NEXT_PHASE["data"] == "visuals"
    assert NEXT_PHASE["approval"] == "published"
