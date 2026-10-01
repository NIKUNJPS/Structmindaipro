"""Generate export artefacts (Word / PDF / Excel / CSV / Markdown) from analysis output."""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from config import settings

NAVY = colors.HexColor("#0d2240")
GOLD = colors.HexColor("#f5a800")
INK = colors.HexColor("#1a2d44")
MUTED = colors.HexColor("#6b8299")
LINE = colors.HexColor("#e2eaf2")

EXPORT_DIR = Path(settings.upload_dir) / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^\s*[-*+]\s+")
_OL_RE = re.compile(r"^\s*\d+[.)]\s+")
_HR_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


def _is_table_line(line: str) -> bool:
    return line.strip().startswith("|")


def _starts_block(line: str) -> bool:
    s = line.strip()
    return bool(
        _HEADING_RE.match(s) or s.startswith("|") or s.startswith("```")
        or _UL_RE.match(line) or _OL_RE.match(line) or _HR_RE.match(s)
    )


def _split_blocks(md: str) -> list[tuple[str, str]]:
    """Yield (kind, text) blocks: 'h1' 'h2' 'h3' 'table' 'li' 'ol' 'code' 'hr' 'p'."""
    blocks: list[tuple[str, str]] = []
    lines = (md or "").replace("\r\n", "\n").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        hm = _HEADING_RE.match(stripped)
        if stripped.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i].rstrip())
                i += 1
            i += 1  # closing fence
            if any(c.strip() for c in code):
                blocks.append(("code", "\n".join(code)))
        elif hm:
            level = min(len(hm.group(1)), 3)
            blocks.append((f"h{level}", hm.group(2).strip().rstrip("#").strip()))
            i += 1
        elif _HR_RE.match(stripped):
            blocks.append(("hr", ""))
            i += 1
        elif _is_table_line(line):
            tbl = []
            while i < len(lines) and _is_table_line(lines[i]):
                if not _TABLE_SEP_RE.match(lines[i].strip()):
                    tbl.append(lines[i].strip())
                i += 1
            if tbl:
                blocks.append(("table", "\n".join(tbl)))
        elif _UL_RE.match(line):
            items = []
            while i < len(lines) and _UL_RE.match(lines[i]):
                items.append(_UL_RE.sub("", lines[i]).strip())
                i += 1
            blocks.append(("li", "\n".join(items)))
        elif _OL_RE.match(line):
            items = []
            while i < len(lines) and _OL_RE.match(lines[i]):
                items.append(_OL_RE.sub("", lines[i]).strip())
                i += 1
            blocks.append(("ol", "\n".join(items)))
        else:
            para = [stripped]
            i += 1
            while i < len(lines) and lines[i].strip() and not _starts_block(lines[i]):
                para.append(lines[i].strip())
                i += 1
            blocks.append(("p", " ".join(para)))
    return blocks


def _table_rows(tbl_md: str) -> list[list[str]]:
    """Parse a markdown table into a rectangular grid (ragged rows padded)."""
    rows: list[list[str]] = []
    for line in tbl_md.splitlines():
        line = line.strip()
        if not line.startswith("|") or _TABLE_SEP_RE.match(line):
            continue
        body = line[1:-1] if line.endswith("|") and len(line) > 1 else line[1:]
        cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", body)]
        rows.append(cells)
    if not rows:
        return rows
    width = max(len(r) for r in rows)
    return [r + [""] * (width - len(r)) for r in rows]


def _strip_md(text: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", text or "", flags=re.I)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)
    return text


def _rl_markup(text: str) -> str:
    """Markdown inline → ReportLab paragraph markup. Escapes &, <, > first —
    an unescaped '<' (e.g. 'L < 6 m') makes ReportLab abort the whole PDF."""
    text = re.sub(r"<br\s*/?>", "\x00", text or "", flags=re.I)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("\x00", "<br/>")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)
    return text


def _cell_value(text: str):
    """Excel cell value: real numbers stay numeric; text never becomes a formula."""
    v = _strip_md(text).strip()
    num = v.replace(",", "")
    if re.fullmatch(r"-?\d+(\.\d+)?", num) and len(num) < 16 and not (len(num) > 1 and num.startswith("0") and "." not in num):
        try:
            return float(num) if "." in num else int(num)
        except ValueError:
            pass
    # openpyxl stores any string beginning with "=" as a formula.
    return "'" + v if v.startswith("=") else v


# ---------- MARKDOWN ----------
def export_markdown(content: str, meta: dict) -> str:
    fname = f"{meta['id']}.md"
    path = EXPORT_DIR / fname
    header = (
        f"# {meta['mode_label']}\n"
        f"**Project:** {meta.get('project_name', 'Quick Analysis')}  \n"
        f"**Generated:** {meta.get('completed_at', '')}  \n"
        f"**Model:** {meta.get('model_used', '')}  \n"
        f"**Hash:** `{meta.get('blockchain_hash', '')}`\n\n---\n\n"
    )
    path.write_text(header + content, encoding="utf-8")
    return str(path)


# ---------- CSV ----------
def export_csv(content: str, meta: dict) -> str:
    fname = f"{meta['id']}.csv"
    path = EXPORT_DIR / fname
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "type", "content"])
    section = ""
    for kind, text in _split_blocks(content):
        if kind in ("h1", "h2", "h3"):
            section = _strip_md(text)
            w.writerow([section, kind, section])
        elif kind == "table":
            for ri, row in enumerate(_table_rows(text)):
                w.writerow([section, "table-header" if ri == 0 else "table-row"] + [_strip_md(c) for c in row])
        elif kind != "hr":
            w.writerow([section, kind, _strip_md(text).replace("\n", " ")])
    path.write_text(buf.getvalue(), encoding="utf-8-sig")
    return str(path)


# ---------- EXCEL ----------
def _sheet_title(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", " ", _strip_md(name)).strip()[:28] or "Table"
    title, n = base, 2
    while title.lower() in used:
        title = f"{base[:25]} {n}"
        n += 1
    used.add(title.lower())
    return title


def _write_table(ws, start_row: int, rows: list[list[str]], header_font, header_fill, thin) -> int:
    for c, h in enumerate(rows[0], start=1):
        cell = ws.cell(row=start_row, column=c, value=_strip_md(h))
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin
    r = start_row + 1
    for data in rows[1:]:
        for c, v in enumerate(data, start=1):
            cell = ws.cell(row=r, column=c, value=_cell_value(v))
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = thin
        r += 1
    return r


def _autosize(ws, max_width: int = 60) -> None:
    widths: dict[int, int] = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None:
                widths[cell.column] = max(widths.get(cell.column, 0), len(str(cell.value)))
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = max(10, min(max_width, w + 2))


def export_xlsx(content: str, meta: dict) -> str:
    """One 'Report' sheet with the full report in reading order, plus every
    table on its own sheet (named after its section) for direct use."""
    fname = f"{meta['id']}.xlsx"
    path = EXPORT_DIR / fname
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill("solid", fgColor="0D2240")
    side = Side(style="thin", color="E2EAF2")
    thin = Border(left=side, right=side, top=side, bottom=side)

    ws["A1"] = meta["mode_label"]
    ws["A1"].font = Font(name="Calibri", bold=True, size=16, color="0D2240")
    ws["A2"] = f"Project: {meta.get('project_name', 'Quick Analysis')}"
    ws["A3"] = f"Generated: {meta.get('completed_at', '')}"
    ws["A4"] = f"Model: {meta.get('model_used', '')}"
    ws["A5"] = f"Hash: {meta.get('blockchain_hash', '')}"

    used_titles = {"report"}
    current_heading = "Table"
    row = 7
    for kind, text in _split_blocks(content):
        if kind in ("h1", "h2", "h3"):
            current_heading = text
            ws.cell(row=row, column=1, value=_strip_md(text)).font = Font(
                bold=True, size={"h1": 14, "h2": 13, "h3": 12}[kind], color="0D2240"
            )
            row += 1
        elif kind == "table":
            rows = _table_rows(text)
            if not rows:
                continue
            row = _write_table(ws, row, rows, header_font, header_fill, thin) + 1
            if len(rows) > 1:
                tws = wb.create_sheet(_sheet_title(current_heading, used_titles))
                _write_table(tws, 1, rows, header_font, header_fill, thin)
                tws.freeze_panes = "A2"
                _autosize(tws)
        elif kind in ("li", "ol"):
            for idx, it in enumerate(text.splitlines(), 1):
                prefix = "• " if kind == "li" else f"{idx}. "
                ws.cell(row=row, column=1, value=prefix + _strip_md(it))
                row += 1
        elif kind == "hr":
            row += 1
        else:
            ws.cell(row=row, column=1, value=_cell_value(text) if kind == "p" else text)
            row += 1

    _autosize(ws)
    wb.save(str(path))
    return str(path)


# ---------- WORD ----------
def _add_md_runs(paragraph, text: str, size: float | None = None, color=None, bold=False) -> None:
    """Add runs to a docx paragraph, honouring **bold** and *italic*."""
    text = re.sub(r"<br\s*/?>", " ", text or "", flags=re.I)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)
    for token in re.split(r"(\*\*.+?\*\*|`.+?`)", text):
        if not token:
            continue
        is_bold = token.startswith("**") and token.endswith("**") and len(token) > 4
        is_code = token.startswith("`") and token.endswith("`") and len(token) > 2
        raw = token[2:-2] if is_bold else token[1:-1] if is_code else _strip_md(token)
        run = paragraph.add_run(raw)
        run.bold = bold or is_bold
        if is_code:
            run.font.name = "Consolas"
        if size:
            run.font.size = Pt(size)
        if color is not None:
            run.font.color.rgb = color


def _shade(cell, fill: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shading)


def export_docx(content: str, meta: dict) -> str:
    fname = f"{meta['id']}.docx"
    path = EXPORT_DIR / fname
    doc = Document()
    navy = RGBColor(0x0D, 0x22, 0x40)
    ink = RGBColor(0x1A, 0x2D, 0x44)

    # Landscape-friendly margins so wide MTO / register tables fit.
    for section in doc.sections:
        section.left_margin = section.right_margin = Inches(0.6)
        section.top_margin = section.bottom_margin = Inches(0.7)

    # Cover
    doc.add_paragraph("4XSTRUCT · STRUCTMIND").runs[0].font.size = Pt(10)
    title = doc.add_paragraph()
    tr = title.add_run(meta["mode_label"].upper())
    tr.bold = True
    tr.font.size = Pt(28)
    tr.font.color.rgb = navy
    doc.add_paragraph(f"Project: {meta.get('project_name', 'Quick Analysis')}")
    doc.add_paragraph(f"Generated: {meta.get('completed_at', '')}")
    doc.add_paragraph(f"Model: {meta.get('model_used', '')}")
    doc.add_paragraph(f"SHA-256 Hash: {meta.get('blockchain_hash', '')}")
    doc.add_paragraph("")

    for kind, text in _split_blocks(content):
        if kind in ("h1", "h2", "h3"):
            lvl = {"h1": 1, "h2": 2, "h3": 3}[kind]
            h = doc.add_heading(_strip_md(text), level=lvl)
            for run in h.runs:
                run.font.color.rgb = navy
        elif kind == "table":
            rows = _table_rows(text)
            if not rows:
                continue
            ncols = len(rows[0])
            font_size = 10 if ncols <= 5 else 9 if ncols <= 8 else 8 if ncols <= 11 else 7
            tbl = doc.add_table(rows=len(rows), cols=ncols)
            try:
                tbl.style = "Table Grid"
            except Exception:  # noqa: BLE001
                pass
            for ri, data in enumerate(rows):
                for ci, value in enumerate(data):
                    cell = tbl.cell(ri, ci)
                    para = cell.paragraphs[0]
                    if ri == 0:
                        _shade(cell, "0D2240")
                        _add_md_runs(para, value, size=font_size, color=RGBColor(0xFF, 0xFF, 0xFF), bold=True)
                    else:
                        if ri % 2 == 0:
                            _shade(cell, "F7F9FC")
                        _add_md_runs(para, value, size=font_size, color=ink)
            doc.add_paragraph("")
        elif kind in ("li", "ol"):
            for it in text.splitlines():
                p = doc.add_paragraph(style="List Bullet" if kind == "li" else "List Number")
                _add_md_runs(p, it)
        elif kind == "code":
            p = doc.add_paragraph()
            run = p.add_run(text)
            run.font.name = "Consolas"
            run.font.size = Pt(9)
        elif kind == "hr":
            doc.add_paragraph("")
        else:
            _add_md_runs(doc.add_paragraph(), text)

    doc.save(str(path))
    return str(path)


# ---------- PDF ----------
def _pdf_font_size(ncols: int) -> float:
    return 9 if ncols <= 5 else 8 if ncols <= 8 else 7 if ncols <= 11 else 6


def _pdf_col_widths(rows: list[list[str]], avail: float, font_size: float, pad: float) -> list[float]:
    """Give every column at least the width of its longest single word (so
    marks like 'W18x35' never break mid-token), then share the remaining
    width by content length. Always sums to `avail` so the table fits."""
    ncols = len(rows[0])
    char_w = font_size * 0.56
    mins, weights = [], []
    for c in range(ncols):
        texts = [_strip_md(r[c]) for r in rows]
        longest_word = max((len(w) for t in texts for w in t.split()), default=1)
        mins.append(min(longest_word * char_w + 2 * pad, avail / ncols * 2.2))
        weights.append(min(max(max(len(t) for t in texts), 3), 45))
    base = sum(mins)
    if base >= avail:
        return [m * avail / base for m in mins]
    extra = avail - base
    wsum = sum(weights) or 1
    return [m + extra * w / wsum for m, w in zip(mins, weights)]


def export_pdf(content: str, meta: dict) -> str:
    fname = f"{meta['id']}.pdf"
    path = EXPORT_DIR / fname
    styles = getSampleStyleSheet()

    story = []
    brand = ParagraphStyle("brand", parent=styles["Normal"], fontName="Helvetica-Bold",
                           textColor=GOLD, fontSize=10, spaceAfter=6)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                        textColor=NAVY, fontSize=20, leading=24, spaceAfter=12)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                        textColor=NAVY, fontSize=15, leading=19, spaceBefore=10, spaceAfter=8)
    h3 = ParagraphStyle("h3", parent=styles["Heading3"], fontName="Helvetica-Bold",
                        textColor=NAVY, fontSize=12, leading=15, spaceBefore=6, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica",
                          textColor=INK, fontSize=10, leading=14, spaceAfter=6)
    bullet_s = ParagraphStyle("bullet", parent=body, leftIndent=14, bulletIndent=4, spaceAfter=3)
    code_s = ParagraphStyle("code", parent=body, fontName="Courier", fontSize=8.5, leading=11,
                            backColor=colors.HexColor("#f7f9fc"), borderPadding=6)
    meta_s = ParagraphStyle("meta", parent=body, textColor=MUTED, fontSize=9, spaceAfter=4)

    blocks = _split_blocks(content)
    widest = max((len(_table_rows(t)[0]) for k, t in blocks if k == "table" and _table_rows(t)), default=0)
    # Wide take-off / register tables read far better in landscape.
    pagesize = landscape(LETTER) if widest >= 9 else LETTER
    left = right = 0.6 * inch
    avail = pagesize[0] - left - right

    story.append(Paragraph("4XSTRUCT · STRUCTMIND", brand))
    story.append(Paragraph(_rl_markup(meta["mode_label"].upper()), h1))
    story.append(Paragraph(_rl_markup(f"Project: {meta.get('project_name', 'Quick Analysis')}"), meta_s))
    story.append(Paragraph(_rl_markup(f"Generated: {meta.get('completed_at', '')}"), meta_s))
    story.append(Paragraph(_rl_markup(f"Model: {meta.get('model_used', '')}"), meta_s))
    story.append(Paragraph(_rl_markup(f"SHA-256: {meta.get('blockchain_hash', '')}"), meta_s))
    story.append(Spacer(1, 0.2 * inch))

    def safe_para(markup: str, style) -> Paragraph:
        try:
            return Paragraph(markup, style)
        except Exception:  # noqa: BLE001 — never let one odd line kill the report
            return Paragraph(_rl_markup(_strip_md(re.sub(r"<[^>]+>", "", markup))), style)

    for kind, text in blocks:
        if kind in ("h1", "h2", "h3"):
            story.append(safe_para(_rl_markup(text), {"h1": h1, "h2": h2, "h3": h3}[kind]))
        elif kind == "table":
            rows = _table_rows(text)
            if not rows:
                continue
            ncols = len(rows[0])
            fs = _pdf_font_size(ncols)
            pad = 4 if ncols > 8 else 6
            cell_s = ParagraphStyle("cell", parent=body, fontSize=fs, leading=fs + 2.5, spaceAfter=0)
            head_s = ParagraphStyle("head", parent=cell_s, fontName="Helvetica-Bold", textColor=colors.white)
            data = [
                [safe_para(_rl_markup(c), head_s if ri == 0 else cell_s) for c in r]
                for ri, r in enumerate(rows)
            ]
            tbl = Table(data, colWidths=_pdf_col_widths(rows, avail, fs, pad), repeatRows=1, splitByRow=1)
            tbl.setStyle(TableStyle([
                ("BACKGROUND",     (0, 0), (-1, 0), NAVY),
                ("LEFTPADDING",    (0, 0), (-1, -1), pad),
                ("RIGHTPADDING",   (0, 0), (-1, -1), pad),
                ("TOPPADDING",     (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
                ("GRID",           (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN",         (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 0.15 * inch))
        elif kind in ("li", "ol"):
            for idx, it in enumerate(text.splitlines(), 1):
                bullet = "•" if kind == "li" else f"{idx}."
                story.append(safe_para(_rl_markup(it), ParagraphStyle(
                    f"b{kind}", parent=bullet_s, bulletText=bullet)))
        elif kind == "code":
            story.append(safe_para(_rl_markup(text).replace("\n", "<br/>"), code_s))
        elif kind == "hr":
            story.append(Spacer(1, 0.12 * inch))
        else:
            story.append(safe_para(_rl_markup(text), body))

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(left, 0.45 * inch, f"4XSTRUCT · STRUCTMIND · {meta['mode_label']}")
        canvas.drawRightString(pagesize[0] - right, 0.45 * inch, f"Page {doc_.page}")
        canvas.restoreState()

    pdf = SimpleDocTemplate(
        str(path),
        pagesize=pagesize,
        leftMargin=left,
        rightMargin=right,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=meta.get("project_name") or meta["mode_label"],
        author="4XStruct",
    )
    pdf.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return str(path)


EXPORTERS = {
    "markdown": export_markdown,
    "csv": export_csv,
    "xlsx": export_xlsx,
    "docx": export_docx,
    "pdf": export_pdf,
}


def generate_all_exports(content: str, meta: dict) -> list[dict]:
    results = []
    for fmt, fn in EXPORTERS.items():
        try:
            p = fn(content, meta)
            results.append({"format": fmt, "path": p})
        except Exception as e:  # noqa: BLE001
            results.append({"format": fmt, "path": "", "error": str(e)})
    return results
