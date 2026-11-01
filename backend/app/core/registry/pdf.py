import re
from pathlib import Path

from app.config import get_settings

FONT_PATH = Path(__file__).resolve().parents[3] / "static" / "fonts" / "DejaVuSansCondensed.ttf"


def card_pdf(model, version) -> Path:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    if FONT_PATH.exists():
        pdf.add_font("DejaVu", "", str(FONT_PATH))
        pdf.set_font("DejaVu", size=10)
    else:
        pdf.set_font("Helvetica", size=10)

    settings = get_settings()
    out_dir = settings.storage_path / "exports" / f"card_{model.id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    for line in (version.card_md or "").splitlines():
        clean = re.sub(r"[#*`]", "", line).strip()
        if not clean:
            pdf.ln(2)
            continue
        if line.startswith("# "):
            pdf.set_font_size(14)
            pdf.multi_cell(0, 6, clean)
            pdf.set_font_size(10)
        else:
            pdf.multi_cell(0, 5, clean)
    out = out_dir / f"model_card_v{version.version}.pdf"
    pdf.output(str(out))
    return out
