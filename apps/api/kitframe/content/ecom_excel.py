"""Fill FC Barcelona 'Descripcions producte per ecom' workbooks.

Green / non-red rows missing Spanish description are filled. Red rows are skipped.
Locales in the sheet: ES, CA, EN, FR, DE, JP, KR (+ meta titles/descriptions).

Descriptions are grounded in product photos; fit / measures / care come from
operator notes when provided (translated to all locales).
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string
from openpyxl.workbook.workbook import Workbook

from kitframe.extraction.schema import enforce_strict_schema

ECOM_LOCALES = ("ES", "CA", "EN", "FR", "DE", "JP", "KR")

LANG_BLOCKS = {
    "ES": dict(title="T", desc="U", fit="V", measures="W", care="X"),
    "CA": dict(title="Z", desc="AA", fit="AB", measures="AC", care="AD"),
    "EN": dict(title="AF", desc="AG", fit="AH", measures="AI", care="AJ"),
    "FR": dict(title="AL", desc="AM", fit="AN", measures="AO", care="AP"),
    "DE": dict(title="AR", desc="AS", fit="AT", measures="AU", care="AV"),
    "JP": dict(title="AX", desc="AY", fit="AZ", measures="BA", care="BB"),
    "KR": dict(title="BD", desc="BE", fit="BF", measures="BG", care="BH"),
}

META = {
    "CA": ("BJ", "BQ"),
    "ES": ("BK", "BR"),
    "EN": ("BL", "BS"),
    "DE": ("BM", "BT"),
    "FR": ("BN", "BU"),
    "JA": ("BO", "BV"),
    "KO": ("BP", "BW"),
}

META_SRC = {"JA": "JP", "KO": "KR"}

DEFAULT_FIT = {
    "ES": "Regular fit: elige tu talla habitual.",
    "CA": "Regular fit: escull la teva talla habitual.",
    "EN": "Regular fit: choose your usual size.",
    "FR": "Coupe regular : choisis ta taille habituelle.",
    "DE": "Regular Fit: wähle deine übliche Größe.",
    "JP": "レギュラーフィット：いつものサイズを選んでください。",
    "KR": "레귤러 핏: 평소 사이즈를 선택하세요.",
}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_IMAGES_PER_REF = 8


@dataclass
class EcomRow:
    row: int
    ref: str
    title: str
    collection: str
    product_type: str
    existing_fit_es: str


def _cell(ws: Any, row: int, letter: str) -> Any:
    return ws.cell(row, column_index_from_string(letter))


def _is_red(cell: Any) -> bool:
    fill = cell.fill
    if not fill or fill.patternType is None or not fill.fgColor:
        return False
    rgb = getattr(fill.fgColor, "rgb", None)
    return bool(rgb and str(rgb).upper().endswith("FF0000"))


def load_workbook_bytes(data: bytes) -> Workbook:
    return load_workbook(io.BytesIO(data))


def workbook_to_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def list_rows_to_fill(wb: Workbook, *, only_missing_es_desc: bool = True) -> list[EcomRow]:
    ws = wb.active
    out: list[EcomRow] = []
    for row in range(4, (ws.max_row or 0) + 1):
        ref_cell = ws.cell(row, 1)
        ref = ref_cell.value
        if ref is None or str(ref).strip() == "":
            continue
        if _is_red(ref_cell):
            continue
        es_desc = _cell(ws, row, "U").value
        if only_missing_es_desc and es_desc and str(es_desc).strip():
            continue
        out.append(
            EcomRow(
                row=row,
                ref=str(ref).strip(),
                title=str(ws.cell(row, 3).value or "").strip(),
                collection=str(ws.cell(row, 4).value or "").strip(),
                product_type=str(ws.cell(row, 5).value or "").strip(),
                existing_fit_es=str(_cell(ws, row, "V").value or "").strip(),
            )
        )
    return out


def normalize_ref_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.strip().upper())


def is_product_image_filename(filename: str) -> bool:
    suffix = PurePosixPath(filename).suffix.lower()
    return suffix in IMAGE_SUFFIXES


def match_filename_to_ref(filename: str, refs: list[str]) -> str | None:
    """Map `BLMP813081_front.jpg` / `blmp813081-1.png` to a pending ref."""
    if not refs or not is_product_image_filename(filename):
        return None
    stem = PurePosixPath(filename).stem
    # Longer refs first so BLMP813081A beats BLMP813081
    ordered = sorted(refs, key=len, reverse=True)
    for ref in ordered:
        if not ref.strip():
            continue
        pattern = re.compile(
            r"^" + re.escape(ref.strip()) + r"(?:$|[_\-\s.].*)",
            re.IGNORECASE,
        )
        if pattern.match(stem):
            return ref
    return None


def group_images_by_ref(
    filenames: list[str],
    refs: list[str],
) -> tuple[dict[str, list[str]], list[str]]:
    """Return (ref -> filenames, unmatched filenames)."""
    grouped: dict[str, list[str]] = {r: [] for r in refs}
    unmatched: list[str] = []
    for name in filenames:
        ref = match_filename_to_ref(name, refs)
        if ref is None:
            unmatched.append(name)
            continue
        if len(grouped[ref]) < MAX_IMAGES_PER_REF:
            grouped[ref].append(name)
    return grouped, unmatched


def parse_notes_json(raw: str | None) -> dict[str, dict[str, str]]:
    """Parse notes keyed by product ref: {fit, care, measures, extra}."""
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"notes_json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("notes_json must be an object keyed by product reference")
    out: dict[str, dict[str, str]] = {}
    for key, value in data.items():
        ref = str(key).strip()
        if not ref:
            continue
        if isinstance(value, str):
            out[ref] = {"extra": value.strip()}
            continue
        if not isinstance(value, dict):
            continue
        block: dict[str, str] = {}
        for field in ("fit", "care", "measures", "extra"):
            v = value.get(field)
            if v is not None and str(v).strip():
                block[field] = str(v).strip()
        if block:
            out[ref] = block
    return out


def ecom_row_schema() -> dict[str, Any]:
    locale_block = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "fit": {"type": "string"},
            "measures": {"type": "string"},
            "care": {"type": "string"},
            "meta_title": {"type": "string"},
            "meta_description": {"type": "string"},
        },
        "required": [
            "title",
            "description",
            "fit",
            "measures",
            "care",
            "meta_title",
            "meta_description",
        ],
    }
    return enforce_strict_schema(
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {loc: locale_block for loc in ECOM_LOCALES},
            "required": list(ECOM_LOCALES),
        }
    )


def apply_row_fill(wb: Workbook, row: int, content: dict[str, Any]) -> None:
    ws = wb.active
    for lang, cols in LANG_BLOCKS.items():
        block = content.get(lang) or {}
        if not isinstance(block, dict):
            continue
        title = str(block.get("title") or "").strip()
        desc = str(block.get("description") or "").strip()
        fit = str(block.get("fit") or "").strip() or DEFAULT_FIT.get(lang, "")
        measures = str(block.get("measures") or "").strip()
        care = str(block.get("care") or "").strip()
        if title:
            _cell(ws, row, cols["title"]).value = title
        if desc:
            _cell(ws, row, cols["desc"]).value = desc
        if fit:
            _cell(ws, row, cols["fit"]).value = fit
        if measures:
            _cell(ws, row, cols["measures"]).value = measures
        if care:
            _cell(ws, row, cols["care"]).value = care

    for meta_lang, (title_col, desc_col) in META.items():
        src = META_SRC.get(meta_lang, meta_lang)
        block = content.get(src) or {}
        if not isinstance(block, dict):
            continue
        meta_title = str(block.get("meta_title") or block.get("title") or "").strip()
        meta_desc = str(block.get("meta_description") or "").strip()
        if meta_title:
            _cell(ws, row, title_col).value = meta_title
        if meta_desc:
            _cell(ws, row, desc_col).value = meta_desc


DESCRIPTION_STYLE_RULES = """
PRODUCT DESCRIPTION RULES (apply to the "description" field in EVERY locale):

SOURCE OF TRUTH
- Base descriptions EXCLUSIVELY on what is visible in the product photographs.
- Do NOT add information that cannot be confirmed from the images.
- Operator notes (fit / measures / care) may only fill those dedicated fields, never invent visual details.

STYLE AND LENGTH
- Short but complete: typically 1 to 3 sentences.
- Natural, clear, fluent prose; easy to understand and to translate.
- Avoid overly technical, complex or ambiguous wording.

CONTENT
- Describe only visible product features.
- Include relevant visible details: colours, graphics, prints, logos, apparent materials, finishes, visible functional elements.
- Do NOT add opinions, value judgments or subjective claims about quality, comfort, style or performance
  (forbidden examples: "cómodos", "perfectos", "ideal", "muy bonito", "must-have", "premium feel").

TONE
- Informative, objective and descriptive.
- No promotional or commercial sales language.
- Do not repeat information unnecessarily.

FC BARCELONA TERMINOLOGY (mandatory)
- Always use "FC Barcelona" for the club. NEVER use "Barça", "Barca", "FCB" as the club name in copy.
- In Spanish (ES): club fans are "culés".
- In all other locales (CA, EN, FR, DE, JP, KR): always use "culers" — do not translate or adapt that term.

GOOD EXAMPLE (ES):
"Calcetines infantiles FC Barcelona con diseño del escudo del club en la parte superior y motivos gráficos navideños en la zona del pie. Incorporan forro interior de aspecto afelpado visible en el borde superior y elementos antideslizantes en la planta."

BAD EXAMPLE (ES) — do NOT write like this:
"Calcetines infantiles FC Barcelona muy cómodos y perfectos para los pequeños aficionados. Su diseño navideño los convierte en una opción ideal para el invierno."
""".strip()


def build_system_prompt(*, tone: str, do_not_translate: list[str]) -> str:
    # Brand glossary extras; still enforce FC Barcelona naming above "Barça".
    protected = list(do_not_translate or [])
    for term in ("FC Barcelona", "culés", "culers"):
        if term not in protected:
            protected.append(term)
    # Explicitly ban Barça in ecom descriptions even if glossary listed it historically.
    return (
        "You write ecommerce product copy for FC Barcelona merchandising "
        "(official Club / co-branded / licensed products). "
        f"Brand glossary tone hint (secondary to description rules): {tone or 'informative, objective'}. "
        f"Protected terms (keep as-is when they appear): {protected}. "
        f"\n\n{DESCRIPTION_STYLE_RULES}\n\n"
        "OTHER FIELDS:\n"
        "- title: derive a natural commercial product name from the technical title; keep it factual, not promotional.\n"
        "- fit / measures / care: when the operator provides notes, translate those facts faithfully "
        "into every locale and do NOT invent numbers or care symbols. "
        "If notes omit a field, leave measures empty; for care use cautious wording "
        "(follow the care label) rather than inventing fabric percentages. "
        "Accessories may use N/A for fit when appropriate.\n"
        "- meta_title <= 70 chars, meta_description <= 160 chars; factual, no hype; still use FC Barcelona (never Barça).\n"
        "Return ALL locales: ES, CA, EN, FR, DE, JP, KR. "
        "Plain text only (no HTML)."
    )


def build_user_prompt(
    row: EcomRow,
    *,
    notes: dict[str, str] | None = None,
    image_count: int = 0,
) -> str:
    notes = notes or {}
    payload = {
        "referencia": row.ref,
        "titulo_tecnico": row.title,
        "coleccion": row.collection,
        "tipo_producto": row.product_type,
        "fit_es_existente": row.existing_fit_es or None,
        "fotos_adjuntas": image_count,
        "notas_operador": {
            "fit": notes.get("fit") or None,
            "medidas": notes.get("measures") or None,
            "cuidados": notes.get("care") or None,
            "extra": notes.get("extra") or None,
        },
        "instrucciones": (
            "Write description ONLY from what you see in the photos (1–3 objective sentences). "
            "No promotional language. Always 'FC Barcelona' (never 'Barça'). "
            "ES fans = 'culés'; other locales = 'culers'. "
            "Use notas_operador only for fit/measures/care fields when present; translate them to every locale."
        ),
    }
    return json.dumps(payload, ensure_ascii=False)
