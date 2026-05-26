"""Role-aware PDF generator for estimation reports. Proper contrast, padding, page breaks."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from config import settings

# ─── BRAND ─────────────────────────────────────────────
NAVY   = colors.HexColor("#0d2240")
NAVYM  = colors.HexColor("#1a3a5c")
GOLD   = colors.HexColor("#f5a800")
GOLDL  = colors.HexColor("#ffd166")
GOLDP  = colors.HexColor("#fff8e6")
INK    = colors.HexColor("#1a2d44")
MUTED  = colors.HexColor("#6b8299")
LINE   = colors.HexColor("#e2eaf2")
BG     = colors.HexColor("#f7f9fc")
WHITE  = colors.white
SUCCESS = colors.HexColor("#16a34a")
WARN   = colors.HexColor("#f59e0b")
DANGER = colors.HexColor("#ef4444")

EXPORT_DIR = Path(settings.upload_dir) / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _styles():
    s = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("brand", parent=s["Normal"], fontName="Helvetica-Bold",
                                textColor=GOLD, fontSize=11, leading=14, spaceAfter=8,
                                letterSpacing=2),
        "title": ParagraphStyle("title", parent=s["Heading1"], fontName="Helvetica-Bold",
                                textColor=NAVY, fontSize=26, leading=30, spaceAfter=16),
        "subtitle": ParagraphStyle("subtitle", parent=s["Normal"], fontName="Helvetica",
                                   textColor=MUTED, fontSize=11, leading=14, spaceAfter=18),
        "h2": ParagraphStyle("h2", parent=s["Heading2"], fontName="Helvetica-Bold",
                             textColor=NAVY, fontSize=15, leading=18, spaceBefore=16, spaceAfter=10),
        "h3": ParagraphStyle("h3", parent=s["Heading3"], fontName="Helvetica-Bold",
                             textColor=NAVY, fontSize=12, leading=15, spaceBefore=10, spaceAfter=6),
        "body": ParagraphStyle("body", parent=s["Normal"], fontName="Helvetica",
                               textColor=INK, fontSize=10.5, leading=15, spaceAfter=6),
        "meta": ParagraphStyle("meta", parent=s["Normal"], fontName="Helvetica",
                               textColor=MUTED, fontSize=9, leading=12, spaceAfter=3),
        "money": ParagraphStyle("money", parent=s["Normal"], fontName="Helvetica-Bold",
                                textColor=NAVY, fontSize=14, leading=18),
        "moneyBig": ParagraphStyle("moneyBig", parent=s["Normal"], fontName="Helvetica-Bold",
                                   textColor=GOLD, fontSize=28, leading=32),
        "tableCell": ParagraphStyle("tableCell", parent=s["Normal"], fontName="Helvetica",
                                    textColor=INK, fontSize=9.5, leading=12),
        "tableCellHead": ParagraphStyle("tableCellHead", parent=s["Normal"],
                                        fontName="Helvetica-Bold", textColor=WHITE, fontSize=9.5, leading=12),
    }


# ─── REUSABLE: high-contrast data table ────────────────
def _table(rows: list[list[str]], st: dict, col_widths: list[float] | None = None,
           highlight_last: bool = False) -> Table:
    """First row = header. Renders with navy bg + white bold text. Auto alternating rows."""
    styles = st
    data = []
    for ri, row in enumerate(rows):
        rendered = []
        style_choice = "tableCellHead" if ri == 0 else "tableCell"
        for cell in row:
            rendered.append(Paragraph(str(cell), styles[style_choice]))
        data.append(rendered)
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        # HEADER row — solid navy, white text (high contrast)
        ("BACKGROUND",     (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR",      (0, 0), (-1, 0), WHITE),
        ("ALIGN",          (0, 0), (-1, 0), "LEFT"),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING",  (0, 0), (-1, 0), 10),
        ("TOPPADDING",     (0, 0), (-1, 0), 10),
        ("LEFTPADDING",    (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 10),
        ("TOPPADDING",     (0, 1), (-1, -1), 8),
        ("BOTTOMPADDING",  (0, 1), (-1, -1), 8),
        # Body — alternating white/bg, ink-line borders
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, BG]),
        ("LINEBELOW",      (0, 0), (-1, 0), 0, NAVY),
        ("LINEBELOW",      (0, 1), (-1, -1), 0.4, LINE),
        ("LINEAFTER",      (0, 0), (-2, -1), 0.4, LINE),
        ("BOX",            (0, 0), (-1, -1), 0.6, LINE),
    ]
    if highlight_last:
        style_cmds += [
            ("BACKGROUND",   (0, -1), (-1, -1), GOLDP),
            ("FONTNAME",     (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE",    (0, -1), (-1, -1), 1.5, GOLD),
        ]
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _header_block(st, role: str, country: str, project: str) -> list:
    """Branded header strip used on every page."""
    band = Table(
        [[
            Paragraph("4XSTRUCT · STRUCTMIND AI", st["brand"]),
            Paragraph(
                f"{role.upper()} · {country.upper()} · {datetime.now().strftime('%d %b %Y')}",
                ParagraphStyle("rhdr", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
                               textColor=WHITE, alignment=2)
            ),
        ]],
        colWidths=[3.6 * inch, 3.6 * inch],
    )
    band.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("TOPPADDING",    (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return [band, Spacer(1, 0.18 * inch)]


def _kpi_strip(st, kpis: list[tuple[str, str]]) -> Table:
    """Row of KPI tiles."""
    cells = []
    for label, value in kpis:
        inner = Table(
            [[Paragraph(label, ParagraphStyle("kpiLabel", fontName="Helvetica-Bold", fontSize=7.5,
                                              leading=10, textColor=MUTED, letterSpacing=1))],
             [Paragraph(value, ParagraphStyle("kpiVal", fontName="Helvetica-Bold", fontSize=14,
                                              leading=18, textColor=NAVY))]],
            colWidths=[1.7 * inch],
        )
        inner.setStyle(TableStyle([
            ("LEFTPADDING", (0,0), (-1,-1), 12), ("RIGHTPADDING", (0,0), (-1,-1), 12),
            ("TOPPADDING", (0,0), (-1,-1), 10), ("BOTTOMPADDING", (0,0), (-1,-1), 10),
            ("BACKGROUND", (0,0), (-1,-1), WHITE),
            ("LINEABOVE", (0,0), (-1,0), 2.5, GOLD),
            ("BOX", (0,0), (-1,-1), 0.6, LINE),
        ]))
        cells.append(inner)
    table = Table([cells], colWidths=[1.85 * inch] * len(cells))
    table.setStyle(TableStyle([("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0)]))
    return table


# ─── ROLE-SPECIFIC RENDERERS ───────────────────────────
def _render_detailer(result: dict, project: str, st: dict) -> list:
    """Detailer PDF — total hours, scope, timeline, deliverables, final cost. NO internal rate."""
    v = result["visible"]
    story = _header_block(st, "DETAILER", result["country"], project)
    story += [
        Paragraph("DETAILING ESTIMATE", st["title"]),
        Paragraph(f"Project: {project} · Country: {result['country']} · Currency: {result['currency']}", st["subtitle"]),

        _kpi_strip(st, [
            ("TOTAL HOURS", f"{v['total_hours']:,.0f}"),
            ("TIMELINE",    f"{v['timeline_weeks']:.0f} weeks"),
            ("FINAL COST",  v["final_amount"]),
        ]),
        Spacer(1, 0.25 * inch),

        Paragraph("SCOPE OF WORK", st["h2"]),
        Paragraph(v["scope_summary"], st["body"]),
        Spacer(1, 0.08 * inch),

        Paragraph("HOURS BREAKDOWN BY CATEGORY", st["h2"]),
        _table(
            [["Category", "Quantity", "Unit", "Hours"]] +
            [[b["item"], str(b.get("qty","-")), b.get("unit",""), f"{b['hours']:,.1f}"] for b in result["breakdown"]] +
            [["TOTAL HOURS", "", "", f"{v['total_hours']:,.1f}"]],
            st, col_widths=[3.0*inch, 1.0*inch, 1.0*inch, 1.3*inch], highlight_last=True,
        ),
        Spacer(1, 0.2 * inch),

        Paragraph("DELIVERABLES INCLUDED", st["h2"]),
    ]
    for d in v["deliverables"]:
        story.append(Paragraph(f"&#9656; &nbsp; {d}", st["body"]))

    story += [
        Spacer(1, 0.25 * inch),
        Paragraph("FINAL DETAILING COST", st["h2"]),
        Paragraph(v["final_amount"], st["moneyBig"]),
        Paragraph(f"All-inclusive · {result['currency']} · Excludes taxes (where applicable)", st["meta"]),
    ]
    return story


def _render_fabricator(result: dict, project: str, st: dict) -> list:
    v = result["visible"]
    story = _header_block(st, "FABRICATOR", result["country"], project)
    story += [
        Paragraph("FABRICATION ESTIMATE", st["title"]),
        Paragraph(f"Project: {project} · Country: {result['country']} · Currency: {result['currency']}", st["subtitle"]),

        _kpi_strip(st, [
            ("TONNAGE",     f"{v['tonnage']:,.1f} t"),
            ("RATE / TON",  v["rate_per_ton"]),
            ("FINAL AMOUNT", v["final_amount"]),
        ]),
        Spacer(1, 0.25 * inch),

        Paragraph("PROCESS COST BREAKDOWN", st["h2"]),
        _table(
            [["Process Activity", "Share", "Amount"]] +
            [[r["process"], r["pct"], r["amount"]] for r in v["process_breakdown"]] +
            [["SUBTOTAL", "", v["subtotal"]],
             [f"Tax ({result['country']})", "", v["tax"]],
             ["GRAND TOTAL", "", v["final_amount"]]],
            st, col_widths=[3.6*inch, 1.0*inch, 1.7*inch], highlight_last=True,
        ),
        Spacer(1, 0.25 * inch),

        Paragraph("MATERIAL & SHOP ACTIVITIES", st["h2"]),
        _table(
            [["Item", "Quantity / Spec", "Adjustment Factor"]] +
            [[b["item"], f"{b.get('qty','')} {b.get('unit','')}".strip(), b.get("rate", "")]
             for b in result["breakdown"]],
            st, col_widths=[2.5*inch, 2.4*inch, 1.4*inch],
        ),
        Spacer(1, 0.25 * inch),

        Paragraph("FINAL FABRICATION AMOUNT", st["h2"]),
        Paragraph(v["final_amount"], st["moneyBig"]),
        Paragraph(f"Includes tax · {result['currency']} · Industrial fabrication scope", st["meta"]),
    ]
    return story


def _render_engineer(result: dict, project: str, st: dict) -> list:
    v = result["visible"]
    story = _header_block(st, "ENGINEER", result["country"], project)
    story += [
        Paragraph("ENGINEERING ESTIMATE", st["title"]),
        Paragraph(f"Project: {project} · Country: {result['country']} · Currency: {result['currency']}", st["subtitle"]),

        _kpi_strip(st, [
            ("TOTAL HOURS",  f"{v['total_hours']:,.0f}"),
            ("REVIEW CYCLES", v["scope_summary"].split("·")[1].strip() if "·" in v["scope_summary"] else "—"),
            ("FINAL COST",   v["final_amount"]),
        ]),
        Spacer(1, 0.25 * inch),

        Paragraph("ENGINEERING SCOPE", st["h2"]),
        Paragraph(v["scope_summary"], st["body"]),
        Spacer(1, 0.1 * inch),

        Paragraph("HOURS BREAKDOWN", st["h2"]),
        _table(
            [["Activity", "Hours"]] +
            [[b["item"], str(b.get("hours", "—"))] for b in result["breakdown"]] +
            [["TOTAL HOURS", f"{v['total_hours']:,.1f}"]],
            st, col_widths=[4.5*inch, 1.8*inch], highlight_last=True,
        ),
        Spacer(1, 0.2 * inch),

        Paragraph("ENGINEERING DELIVERABLES", st["h2"]),
    ]
    for d in v["deliverables"]:
        story.append(Paragraph(f"&#9656; &nbsp; {d}", st["body"]))

    story += [
        Spacer(1, 0.25 * inch),
        Paragraph("FINAL ENGINEERING COST", st["h2"]),
        Paragraph(v["final_amount"], st["moneyBig"]),
        Paragraph(f"All-inclusive · {result['currency']} · Per international consultancy standards", st["meta"]),
    ]
    return story


def _render_pm(result: dict, project: str, st: dict) -> list:
    v = result["visible"]
    story = _header_block(st, "PROJECT MANAGER", result["country"], project)
    story += [
        Paragraph("PROJECT MANAGEMENT ESTIMATE", st["title"]),
        Paragraph(f"Project: {project} · Country: {result['country']} · Currency: {result['currency']}", st["subtitle"]),

        _kpi_strip(st, [
            ("DURATION",   f"{v['duration_weeks']} wk"),
            ("TEAM SIZE",  f"{v['team_size']} ppl"),
            ("FINAL COST", v["final_amount"]),
        ]),
        Spacer(1, 0.25 * inch),

        Paragraph("MANAGEMENT EFFORT BREAKDOWN", st["h2"]),
        _table(
            [["Activity", "Hours"]] +
            [[b["item"], str(b.get("hours", "—"))] for b in result["breakdown"]] +
            [["TOTAL HOURS", f"{v['total_hours']:,.1f}"]],
            st, col_widths=[4.5*inch, 1.8*inch], highlight_last=True,
        ),
        Spacer(1, 0.2 * inch),

        Paragraph("DELIVERABLES & COORDINATION SCOPE", st["h2"]),
    ]
    for d in v["deliverables"]:
        story.append(Paragraph(f"&#9656; &nbsp; {d}", st["body"]))

    story += [
        Spacer(1, 0.25 * inch),
        Paragraph("FINAL MANAGEMENT COST", st["h2"]),
        Paragraph(v["final_amount"], st["moneyBig"]),
        Paragraph(f"Includes 18% management overhead · {result['currency']}", st["meta"]),
    ]
    return story


def _render_modular(result: dict, project: str, st: dict) -> list:
    v = result["visible"]
    story = _header_block(st, "MODULAR SPECIALIST", result["country"], project)
    story += [
        Paragraph("MODULAR ASSEMBLY ESTIMATE", st["title"]),
        Paragraph(f"Project: {project} · Country: {result['country']} · Currency: {result['currency']}", st["subtitle"]),

        _kpi_strip(st, [
            ("MODULES",        f"{v['module_count']}"),
            ("RATE / MODULE",  v["rate_per_module"]),
            ("FINAL AMOUNT",   v["final_amount"]),
        ]),
        Spacer(1, 0.25 * inch),

        Paragraph("PROCESS COST BREAKDOWN", st["h2"]),
        _table(
            [["Process", "Amount"]] +
            [[r["process"], r["amount"]] for r in v["process_breakdown"]] +
            [["SUBTOTAL", v["subtotal"]],
             [f"Tax ({result['country']})", v["tax"]],
             ["GRAND TOTAL", v["final_amount"]]],
            st, col_widths=[4.5*inch, 1.8*inch], highlight_last=True,
        ),
        Spacer(1, 0.25 * inch),

        Paragraph("ASSEMBLY & LOGISTICS SCOPE", st["h2"]),
        _table(
            [["Item", "Quantity", "Unit"]] +
            [[b["item"], str(b.get("qty","")), b.get("unit","")] for b in result["breakdown"]],
            st, col_widths=[3.0*inch, 1.6*inch, 1.6*inch],
        ),
        Spacer(1, 0.25 * inch),

        Paragraph("FINAL MODULAR AMOUNT", st["h2"]),
        Paragraph(v["final_amount"], st["moneyBig"]),
        Paragraph(f"Includes tax · {result['currency']} · Kit-of-parts assembly + transport + install", st["meta"]),
    ]
    return story


def _render_estimator(result: dict, project: str, st: dict) -> list:
    """Estimator gets the FULL breakdown including normally-hidden internal cost basis."""
    v = result["visible"]
    sanity = result.get("meta", {}).get("sanity", {})
    sanity_color = {"ok": SUCCESS, "over": DANGER, "under": WARN}.get(sanity.get("status"), MUTED)

    story = _header_block(st, "ESTIMATOR", result["country"], project)
    story += [
        Paragraph("FULL BID ESTIMATE", st["title"]),
        Paragraph(f"Project: {project} · Country: {result['country']} · Currency: {result['currency']}", st["subtitle"]),

        _kpi_strip(st, [
            ("DIRECT TOTAL",     v["direct_total"]),
            ("MARGIN",           v["margin"].split("(")[0].strip()),
            ("BID PRICE",        v["final_amount"]),
        ]),
        Spacer(1, 0.25 * inch),

        Paragraph("COMPONENT ROLL-UP", st["h2"]),
        _table(
            [["Component", "Scope Summary", "Amount"]] +
            [[c["label"], c["scope"] or "—", c["amount"]] for c in v["components"]] +
            [["", "", ""],
             ["DIRECT TOTAL", "", v["direct_total"]],
             ["Contingency (5%)", "", v["contingency"].split("(")[0].strip()],
             ["Margin", "", v["margin"].split("(")[0].strip()],
             ["Subtotal", "", v["subtotal"]],
             ["Tax", "", v["tax"].split("(")[0].strip()],
             ["BID PRICE", "", v["final_amount"]]],
            st, col_widths=[1.8*inch, 3.0*inch, 1.7*inch], highlight_last=True,
        ),
        Spacer(1, 0.25 * inch),
    ]

    if v.get("per_ton_calibration"):
        story.append(Paragraph(
            f"<b>Per-ton calibration:</b> {v['per_ton_calibration']}",
            st["body"]
        ))
        story.append(Spacer(1, 0.12 * inch))

    # Sanity status box
    sanity_table = Table([[
        Paragraph(f"<b>SANITY CHECK · {sanity.get('status','OK').upper()}</b>",
                  ParagraphStyle("snHd", fontName="Helvetica-Bold", fontSize=10.5,
                                 leading=14, textColor=WHITE)),
        Paragraph(sanity.get("message", "Within market range."),
                  ParagraphStyle("snBd", fontName="Helvetica", fontSize=10,
                                 leading=14, textColor=WHITE)),
    ]], colWidths=[1.8*inch, 4.7*inch])
    sanity_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), sanity_color),
        ("LEFTPADDING", (0,0), (-1,-1), 14),
        ("RIGHTPADDING", (0,0), (-1,-1), 14),
        ("TOPPADDING", (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story += [sanity_table, Spacer(1, 0.2 * inch), PageBreak()]

    # Internal cost basis (estimator-only)
    story.append(Paragraph("INTERNAL COST BASIS (CONFIDENTIAL)", st["h2"]))
    story.append(Paragraph(
        "The figures below show cost-side calculations and target margins.<br/>"
        "Do not distribute outside the estimating team.",
        st["meta"],
    ))
    story.append(Spacer(1, 0.1 * inch))

    detail = result.get("internal", {}).get("components_detail", {})
    rows = [["Component", "Internal Rate (USD)", "Internal Total (USD)", "Margin Indicator"]]
    for label, comp in detail.items():
        internal = comp.get("internal", {}) or {}
        rate = internal.get("billable_rate_per_hour") or internal.get("internal_cost_per_ton_usd") or internal.get("internal_cost_rate_usd") or "—"
        total = internal.get("internal_cost_total_usd") or "—"
        margin = f"{internal.get('gross_margin_pct','—')}%" if internal.get("gross_margin_pct") else "—"
        rows.append([label.title(), str(rate), str(total), str(margin)])
    rows.append(["Target margin", "", "", f"{result['internal'].get('target_margin_pct', 12)}%"])
    story.append(_table(rows, st, col_widths=[1.7*inch, 1.6*inch, 1.7*inch, 1.5*inch], highlight_last=True))

    return story


RENDERERS = {
    "detailer":   _render_detailer,
    "fabricator": _render_fabricator,
    "engineer":   _render_engineer,
    "pm":         _render_pm,
    "modular":    _render_modular,
    "estimator":  _render_estimator,
    "admin":      _render_estimator,  # admin gets full estimator view
}


def render_pdf(result: dict, project: str, *, filename: str | None = None) -> str:
    """Generate the role-specific PDF and return its absolute path."""
    st = _styles()
    renderer = RENDERERS.get(result["role"], _render_estimator)
    story = renderer(result, project, st)

    fname = filename or f"estimation_{result['role']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    path = EXPORT_DIR / fname
    pdf = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title=f"StructMind AI · {result['role'].title()} Estimate",
        author="StructMind AI · 4XStruct Inc.",
    )
    pdf.build(story)
    return str(path)
