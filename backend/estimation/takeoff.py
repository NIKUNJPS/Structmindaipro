"""Deterministic member-by-member take-off.

The model reads the drawings and lists members (mark, profile, quantity,
length, sheet). Everything numeric happens here: unit weights come from
``steel_sections``, lengths are parsed from the drawing strings, duplicates
across sheets are resolved, and totals are summed exactly. The same take-off
feeds the MTO / Master Intake reports and the fabricator estimate, so every
consumer reports identical tonnage and member counts.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict

from .steel_sections import parse_length_mm, unit_weight

# Allowance for connection material not itemised on the drawings.
CONNECTION_ALLOWANCE_PCT = float(os.environ.get("TAKEOFF_CONNECTION_ALLOWANCE_PCT", "3.0"))
# When plates / connection material ARE itemised, only bolts + weld metal remain.
BOLT_WELD_ALLOWANCE_PCT = float(os.environ.get("TAKEOFF_BOLT_WELD_ALLOWANCE_PCT", "1.5"))
# A model-quoted unit weight differing from the catalogue by more than this is reported.
UNIT_WEIGHT_TOLERANCE = 0.08

CATEGORY_GROUPS = {
    "column": "Primary framing", "beam": "Primary framing", "girder": "Primary framing",
    "rafter": "Primary framing", "brace": "Bracing", "bracing": "Bracing",
    "truss": "Primary framing", "transfer": "Primary framing",
    "purlin": "Secondary framing", "girt": "Secondary framing", "joist": "Secondary framing",
    "strut": "Secondary framing", "sag rod": "Secondary framing", "lintel": "Secondary framing",
    "stair": "Miscellaneous metals", "handrail": "Miscellaneous metals",
    "ladder": "Miscellaneous metals", "platform": "Miscellaneous metals",
    "grating": "Miscellaneous metals", "misc": "Miscellaneous metals",
    "embed": "Embeds & anchors", "anchor": "Embeds & anchors",
    "plate": "Plates & connections", "connection": "Plates & connections",
    "stiffener": "Plates & connections", "base plate": "Plates & connections",
}
GROUP_ORDER = ["Primary framing", "Bracing", "Secondary framing", "Miscellaneous metals",
               "Plates & connections", "Embeds & anchors", "Other"]

_SCHEDULE_SOURCES = {"bom", "schedule", "member schedule", "cut list", "material list", "shop"}


def _group(category: str, family: str) -> str:
    cat = (category or "").strip().lower()
    for key, grp in CATEGORY_GROUPS.items():
        if key in cat:
            return grp
    if family == "PLATE":
        return "Plates & connections"
    return "Other"


def _num(v, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _norm_mark(mark) -> str:
    return re.sub(r"\s+", "", str(mark or "")).upper()


def _resolve_line(raw: dict, units: str) -> dict:
    profile = str(raw.get("profile") or raw.get("p") or "").strip()
    qty = int(round(_num(raw.get("qty", raw.get("q")), 0)))
    length_raw = raw.get("length", raw.get("l"))
    length_mm = parse_length_mm(length_raw, units)
    if length_mm is None:
        length_mm = parse_length_mm(raw.get("length_mm"), "metric")

    sec = unit_weight(profile, units)
    model_uw = _num(raw.get("unit_weight_kg_m"), 0.0)
    issues: list[str] = []
    if sec:
        uw, uw_source, family, profile_norm = sec.kg_per_m, sec.source, sec.family, sec.normalized
        if model_uw > 0 and abs(model_uw - uw) / uw > UNIT_WEIGHT_TOLERANCE:
            issues.append(f"drawing/model unit weight {model_uw:g} kg/m vs catalogue {uw:g} kg/m — catalogue used")
    elif model_uw > 0:
        uw, uw_source, family, profile_norm = model_uw, "model", "OTHER", profile.upper()
        issues.append("section not in catalogue — unit weight read from drawings")
    else:
        uw, uw_source, family, profile_norm = 0.0, "unresolved", "OTHER", profile.upper()

    weight_kg = _num(raw.get("weight_kg"), 0.0)   # explicit total (e.g. grating, deck)
    if uw > 0 and length_mm and qty > 0:
        weight_kg = qty * uw * length_mm / 1000.0
    elif weight_kg > 0:
        uw_source = "drawing total"
    else:
        if qty <= 0:
            issues.append("quantity missing")
        if not length_mm:
            issues.append("length missing")
        if uw <= 0:
            issues.append("unit weight unknown")

    display = re.sub(r"(?<=[\d/.])X(?=[\d])", "x", (profile_norm or profile).upper())
    return {
        "mark": str(raw.get("mark") or raw.get("m") or "").strip(),
        "profile": display,
        "qty": qty,
        "length_mm": round(length_mm, 1) if length_mm else None,
        "length_raw": str(length_raw) if length_raw not in (None, "") else "",
        "unit_kg_m": round(uw, 3),
        "weight_kg": round(weight_kg, 2),
        "sheet": str(raw.get("sheet") or raw.get("s") or "").strip(),
        "category": str(raw.get("category") or raw.get("c") or "").strip().lower(),
        "group": _group(str(raw.get("category") or ""), family),
        "source": str(raw.get("source") or "").strip().lower(),
        "grade": str(raw.get("grade") or "").strip(),
        "weight_source": uw_source,
        "issues": issues,
    }


def _deduplicate(lines: list[dict]) -> tuple[list[dict], list[str]]:
    """Resolve members counted more than once.

    1. The same mark/profile/length on the same sheet seen twice (e.g. a sheet
       present in two uploaded files) is counted once (max quantity).
    2. If a mark appears in a BOM / member schedule, the schedule quantity is
       the project total, so plan/elevation counts of that mark are dropped.
    3. Plan counts of the same mark on DIFFERENT sheets are distinct physical
       members (e.g. typical beam on several floors) and are kept.
    """
    notes: list[str] = []
    keyed: dict[tuple, dict] = {}
    unmarked: list[dict] = []
    for ln in lines:
        mark = _norm_mark(ln["mark"])
        if not mark:
            unmarked.append(ln)
            continue
        key = (mark, ln["profile"], round((ln["length_mm"] or 0) / 25.0), ln["sheet"].upper())
        prev = keyed.get(key)
        if prev is not None:
            notes.append(f"{ln['mark']} on {ln['sheet'] or 'unknown sheet'} listed twice — counted once")
        if prev is None or ln["qty"] > prev["qty"]:
            keyed[key] = ln

    scheduled_marks = {
        (_norm_mark(ln["mark"]), ln["profile"])
        for ln in keyed.values()
        if any(s in ln["source"] for s in _SCHEDULE_SOURCES)
    }
    kept: list[dict] = []
    dropped = 0
    for ln in keyed.values():
        k = (_norm_mark(ln["mark"]), ln["profile"])
        is_sched = any(s in ln["source"] for s in _SCHEDULE_SOURCES)
        if k in scheduled_marks and not is_sched:
            dropped += 1
            continue
        kept.append(ln)
    if dropped:
        notes.append(f"{dropped} plan/elevation line(s) superseded by BOM / member-schedule quantities")
    return kept + unmarked, notes


def build_takeoff(batch_results: list[dict]) -> dict:
    """Combine per-batch member lists into one verified take-off."""
    units = "auto"
    for r in batch_results:
        u = str(r.get("units") or "").lower()
        if u in ("imperial", "metric"):
            units = u
            break

    raw_lines: list[dict] = []
    sheets: set[str] = set()
    drawings_seen = 0
    materials: list[str] = []
    model_notes: list[str] = []
    model_claimed = 0.0
    truncated = False
    for r in batch_results:
        batch_units = str(r.get("units") or units).lower()
        for m in r.get("members") or []:
            if isinstance(m, dict):
                raw_lines.append(_resolve_line(m, batch_units if batch_units in ("imperial", "metric") else units))
        sheets.update(str(s) for s in (r.get("sheets") or []) if s)
        drawings_seen += int(_num(r.get("drawings_seen"), 0))
        if r.get("primary_material"):
            materials.append(str(r["primary_material"]))
        if r.get("notes"):
            model_notes.append(str(r["notes"]))
        model_claimed += _num(r.get("tonnage"), 0.0)
        truncated = truncated or bool(r.get("_truncated"))

    lines, dedupe_notes = _deduplicate(raw_lines)
    lines.sort(key=lambda ln: (GROUP_ORDER.index(ln["group"]) if ln["group"] in GROUP_ORDER else 99,
                               ln["profile"], ln["mark"]))

    net_kg = sum(ln["weight_kg"] for ln in lines)
    plate_kg = sum(ln["weight_kg"] for ln in lines if ln["group"] == "Plates & connections")
    itemised = net_kg > 0 and plate_kg / net_kg >= 0.02
    allowance_pct = BOLT_WELD_ALLOWANCE_PCT if itemised else CONNECTION_ALLOWANCE_PCT
    allowance_kg = net_kg * allowance_pct / 100.0
    total_t = (net_kg + allowance_kg) / 1000.0

    by_group: dict[str, dict] = defaultdict(lambda: {"pieces": 0, "lines": 0, "length_m": 0.0, "weight_kg": 0.0})
    by_profile: dict[str, dict] = defaultdict(lambda: {"pieces": 0, "length_m": 0.0, "weight_kg": 0.0,
                                                       "unit_kg_m": 0.0, "group": ""})
    for ln in lines:
        g = by_group[ln["group"]]
        g["pieces"] += ln["qty"]
        g["lines"] += 1
        g["length_m"] += ln["qty"] * (ln["length_mm"] or 0) / 1000.0
        g["weight_kg"] += ln["weight_kg"]
        p = by_profile[ln["profile"]]
        p["pieces"] += ln["qty"]
        p["length_m"] += ln["qty"] * (ln["length_mm"] or 0) / 1000.0
        p["weight_kg"] += ln["weight_kg"]
        p["unit_kg_m"] = ln["unit_kg_m"]
        p["group"] = ln["group"]

    unresolved = [ln for ln in lines if ln["weight_kg"] <= 0]
    flagged = [ln for ln in lines if ln["issues"] and ln["weight_kg"] > 0]
    sources = defaultdict(int)
    for ln in lines:
        sources[ln["weight_source"]] += 1

    notes = list(model_notes)
    notes += dedupe_notes
    if unresolved:
        notes.append(f"{len(unresolved)} line(s) could not be weighed (missing size/length/qty) — see RFIs")
    if truncated:
        notes.append("Part of the drawing set returned an incomplete member list — re-run recommended")

    members_counted = sum(ln["qty"] for ln in lines if ln["group"] != "Plates & connections")

    return {
        # Backwards-compatible headline fields
        "tonnage": round(total_t, 2),
        "members_counted": members_counted,
        "primary_material": max(set(materials), key=materials.count) if materials else "",
        "drawings_seen": max(drawings_seen, len(sheets)),
        "accessory_allowance_pct": allowance_pct,
        "notes": " | ".join(notes),
        # Verified take-off detail
        "method": "deterministic member-by-member take-off",
        "units": units,
        "net_steel_t": round(net_kg / 1000.0, 3),
        "allowance_t": round(allowance_kg / 1000.0, 3),
        "allowance_basis": ("bolts + weld metal (connection plates itemised)" if itemised
                            else "connection plates, bolts, welds (not itemised on drawings)"),
        "pieces_total": sum(ln["qty"] for ln in lines),
        "line_items": len(lines),
        "sheets": sorted(sheets),
        "by_group": [
            {"group": g, "pieces": v["pieces"], "lines": v["lines"],
             "length_m": round(v["length_m"], 1), "weight_t": round(v["weight_kg"] / 1000, 3)}
            for g, v in sorted(by_group.items(),
                               key=lambda kv: GROUP_ORDER.index(kv[0]) if kv[0] in GROUP_ORDER else 99)
        ],
        "by_profile": [
            {"profile": k, "group": v["group"], "pieces": v["pieces"], "length_m": round(v["length_m"], 1),
             "unit_kg_m": round(v["unit_kg_m"], 2), "weight_t": round(v["weight_kg"] / 1000, 3)}
            for k, v in sorted(by_profile.items(), key=lambda kv: -kv[1]["weight_kg"])
        ],
        "members": lines,
        "unresolved": unresolved,
        "flagged": flagged,
        "weight_sources": dict(sources),
        "model_claimed_tonnage": round(model_claimed, 2) if model_claimed else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Markdown rendering (appended to MTO / Master Intake reports)
# ─────────────────────────────────────────────────────────────────────────────

def _cell(v) -> str:
    return str(v if v not in (None, "") else "—").replace("|", "\\|").replace("\n", " ")


def _fmt_len(mm: float | None, raw: str) -> str:
    if raw:
        return raw
    return f"{mm:,.0f} mm" if mm else "—"


def takeoff_summary_markdown(t: dict, max_profiles: int = 60) -> str:
    """Compact summary for the model's system prompt."""
    lines = [
        f"- Total fabricated tonnage: **{t['tonnage']:,.2f} t** "
        f"(net steel {t['net_steel_t']:,.3f} t + {t['accessory_allowance_pct']:g}% allowance "
        f"{t['allowance_t']:,.3f} t for {t['allowance_basis']})",
        f"- Members counted: **{t['members_counted']:,}** "
        f"({t['pieces_total']:,} pieces incl. plates, {t['line_items']:,} line items)",
        "",
        "| Group | Pieces | Length (m) | Weight (t) |",
        "|---|---:|---:|---:|",
    ]
    lines += [f"| {g['group']} | {g['pieces']:,} | {g['length_m']:,.1f} | {g['weight_t']:,.3f} |"
              for g in t["by_group"]]
    lines += ["", "| Profile | Pieces | Length (m) | kg/m | Weight (t) |", "|---|---:|---:|---:|---:|"]
    lines += [f"| {_cell(p['profile'])} | {p['pieces']:,} | {p['length_m']:,.1f} | {p['unit_kg_m']:,.2f} | {p['weight_t']:,.3f} |"
              for p in t["by_profile"][:max_profiles]]
    return "\n".join(lines)


def takeoff_report_markdown(t: dict) -> str:
    """Full verified take-off appendix: summary, profile totals, every member."""
    out = [
        "## Verified Tonnage Take-Off (Member-by-Member)",
        "",
        "Every line below was weighed individually: quantity × length × catalogue unit "
        "weight (AISC / CISC / AS-NZS / EN / IS section tables, or exact geometry for "
        "HSS, pipe, angles, plates and bars; steel density 7,850 kg/m³). Totals are exact "
        "sums of the lines.",
        "",
        "Table: Tonnage Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Net steel weight | {t['net_steel_t']:,.3f} t |",
        f"| Allowance ({t['accessory_allowance_pct']:g}% — {t['allowance_basis']}) | {t['allowance_t']:,.3f} t |",
        f"| **Total fabricated tonnage** | **{t['tonnage']:,.2f} t** |",
        f"| Members counted (excl. plates) | {t['members_counted']:,} |",
        f"| Total pieces (incl. plates) | {t['pieces_total']:,} |",
        f"| Line items | {t['line_items']:,} |",
        f"| Drawings reviewed | {t['drawings_seen']:,} |",
        "",
        "Table: Tonnage by Category",
        "",
        "| Category | Line Items | Pieces | Total Length (m) | Weight (t) | Share |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    net = max(t["net_steel_t"], 1e-9)
    for g in t["by_group"]:
        out.append(f"| {g['group']} | {g['lines']:,} | {g['pieces']:,} | {g['length_m']:,.1f} | "
                   f"{g['weight_t']:,.3f} | {g['weight_t'] / net * 100:.1f}% |")
    out.append(f"| **Total (net)** | **{t['line_items']:,}** | **{t['pieces_total']:,}** | "
               f"**{sum(g['length_m'] for g in t['by_group']):,.1f}** | **{t['net_steel_t']:,.3f}** | **100%** |")

    out += ["", "Table: Tonnage by Profile", "",
            "| Profile | Category | Pieces | Total Length (m) | Unit Wt (kg/m) | Weight (t) |",
            "|---|---|---:|---:|---:|---:|"]
    for p in t["by_profile"]:
        out.append(f"| {_cell(p['profile'])} | {p['group']} | {p['pieces']:,} | {p['length_m']:,.1f} | "
                   f"{p['unit_kg_m']:,.2f} | {p['weight_t']:,.3f} |")

    out += ["", "Table: Member Schedule", "",
            "| # | Mark | Profile | Qty | Length | Unit Wt (kg/m) | Weight (kg) | Category | Sheet |",
            "|---:|---|---|---:|---|---:|---:|---|---|"]
    for i, ln in enumerate(t["members"], 1):
        out.append(
            f"| {i} | {_cell(ln['mark'])} | {_cell(ln['profile'])} | {ln['qty']:,} | "
            f"{_cell(_fmt_len(ln['length_mm'], ln['length_raw']))} | {ln['unit_kg_m']:,.2f} | "
            f"{ln['weight_kg']:,.1f} | {_cell(ln['category'] or ln['group'])} | {_cell(ln['sheet'])} |"
        )

    issues = t.get("unresolved", []) + t.get("flagged", [])
    if issues:
        out += ["", "Table: Take-Off Exceptions (RFI candidates)", "",
                "| Mark | Profile | Sheet | Issue |", "|---|---|---|---|"]
        for ln in issues:
            out.append(f"| {_cell(ln['mark'])} | {_cell(ln['profile'])} | {_cell(ln['sheet'])} | "
                       f"{_cell('; '.join(ln['issues']))} |")
    return "\n".join(out)
