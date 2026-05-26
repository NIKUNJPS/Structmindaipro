"""
Deterministic per-role estimation engine.

Every role exposes a single calculate() function returning a structured dict
with `visible` (always shown to user), `internal` (cost basis — only shown to
estimator/admin), `breakdown` (line items), and `meta` (totals, currency, sanity).
"""
from __future__ import annotations

from .rates import (
    COUNTRY_RATES,
    INTERNAL_DETAILER_COST_USD,
    INTERNAL_ENGINEER_COST_USD,
    INTERNAL_FABRICATOR_COST_PER_TON_USD,
    INTERNAL_PM_COST_USD,
    country,
)
from .sanity import sanity_check


# ============================================================
# COMPLEXITY MULTIPLIERS
# ============================================================
COMPLEXITY = {
    "Low":      {"mult": 0.85, "drawings_hr": 1.5},
    "Medium":   {"mult": 1.00, "drawings_hr": 2.5},
    "High":     {"mult": 1.35, "drawings_hr": 4.0},
    "AESS":     {"mult": 1.80, "drawings_hr": 6.5},
    "Critical": {"mult": 2.10, "drawings_hr": 8.0},
}

MATERIAL_FACTOR = {
    "Carbon Steel":    1.00,
    "HSS":             1.05,
    "Galvanised":      1.18,
    "Stainless":       1.55,
    "Weathering (A588)": 1.12,
    "Aluminium":       1.62,
}

SURFACE_FACTOR = {
    "Shop primer only": 1.00,
    "SSPC-SP6 + 2-coat": 1.08,
    "SSPC-SP10 + 3-coat": 1.18,
    "Hot-dip galvanised": 1.28,
    "Intumescent fire-rated": 1.45,
}

ASSEMBLY_FACTOR = {
    "Simple bolted":     1.00,
    "Mixed bolt/weld":   1.10,
    "Heavy welded":      1.22,
    "Architectural AESS": 1.40,
    "Custom curved":     1.55,
}


def _midpoint(rng: tuple[float, float]) -> float:
    return (rng[0] + rng[1]) / 2.0


def _round(x: float) -> float:
    return round(x, 2)


def _format_money(amount: float, c: dict) -> str:
    sym = c["symbol"]
    if c["currency"] in ("INR", "AED", "SAR"):
        return f"{sym} {amount:,.0f}"
    return f"{sym}{amount:,.0f}"


# ============================================================
# DETAILER  — hours-based, internal rate hidden from user
# ============================================================
def calculate_detailer(inputs: dict, country_code: str = "USA") -> dict:
    c = country(country_code)
    drawings    = max(1, int(inputs.get("drawings", 40)))
    complexity  = inputs.get("complexity", "Medium")
    revisions   = max(0, int(inputs.get("revisions", 1)))
    modeling_h  = float(inputs.get("modeling_hours", 0))
    checking_h  = float(inputs.get("checking_hours", 0))
    connections = max(0, int(inputs.get("connection_count", 0)))

    comp = COMPLEXITY.get(complexity, COMPLEXITY["Medium"])
    base_dwg_hours  = drawings * comp["drawings_hr"]
    connection_hrs  = connections * 0.35  # 21 min per connection avg
    rev_factor      = 1 + revisions * 0.15
    total_hours     = (base_dwg_hours + connection_hrs) * rev_factor + modeling_h + checking_h

    billable_rate = _midpoint(c["detailer_hourly"])
    final_amount  = total_hours * billable_rate

    # Internal cost — hidden from user (visible only to estimator/admin)
    internal_rate_usd = _midpoint(INTERNAL_DETAILER_COST_USD)
    internal_cost_usd = total_hours * internal_rate_usd

    breakdown = [
        {"item": "Production drawings",     "hours": _round(base_dwg_hours),  "qty": drawings,   "unit": "dwgs"},
        {"item": "Connection detailing",    "hours": _round(connection_hrs),  "qty": connections, "unit": "conn"},
        {"item": "Revisions overhead",      "hours": _round((base_dwg_hours+connection_hrs)*(rev_factor-1)), "qty": revisions, "unit": "cycles"},
        {"item": "3D modeling",             "hours": _round(modeling_h),      "qty": 1,          "unit": "lot"},
        {"item": "QC / checking",           "hours": _round(checking_h),      "qty": 1,          "unit": "lot"},
    ]

    sanity = sanity_check(role="detailer", total=final_amount, drawings=drawings, currency=c["currency"])
    return {
        "role": "detailer",
        "country": country_code,
        "currency": c["currency"],
        "symbol": c["symbol"],
        "visible": {
            "total_hours":    _round(total_hours),
            "scope_summary":  f"{drawings} drawings · {complexity} complexity · {revisions} revision cycle(s)",
            "deliverables":   [
                "Production shop drawings (issued for fabrication)",
                "Connection details and weld map",
                "Anchor-bolt setting plan",
                "3D coordination model (LOD 350)",
                "QC checklist sign-off package",
            ],
            "timeline_weeks": _round(total_hours / 38),     # 38 productive hrs/week
            "final_amount":   _format_money(final_amount, c),
            "final_amount_raw": _round(final_amount),
        },
        "internal": {
            "billable_rate_per_hour": _round(billable_rate),
            "internal_cost_rate_usd": _round(internal_rate_usd),
            "internal_cost_total_usd": _round(internal_cost_usd),
            "gross_margin_pct": _round((final_amount - internal_cost_usd*_convert_usd_to_local(1, c)) / final_amount * 100) if final_amount else 0,
        },
        "breakdown": breakdown,
        "meta": {
            "complexity": complexity,
            "complexity_multiplier": comp["mult"],
            "productivity_hrs_per_drawing": comp["drawings_hr"],
            "sanity": sanity,
        },
    }


def _convert_usd_to_local(usd_amount: float, c: dict) -> float:
    """Rough USD→local for internal cost comparison only."""
    rates = {"USD":1.0,"CAD":1.36,"GBP":0.79,"AED":3.67,"AUD":1.52,"INR":83.5,"EUR":0.92,"SAR":3.75,"SGD":1.34}
    return usd_amount * rates.get(c["currency"], 1.0)


# ============================================================
# FABRICATOR — tonnage × per-ton rate with process breakdown
# ============================================================
def calculate_fabricator(inputs: dict, country_code: str = "USA") -> dict:
    c = country(country_code)
    tonnage         = max(0.1, float(inputs.get("tonnage", 100)))
    material        = inputs.get("material_type", "Carbon Steel")
    weld_inches     = float(inputs.get("weld_inches", 0))
    cut_meters      = float(inputs.get("cut_meters", 0))
    surface         = inputs.get("surface_treatment", "Shop primer only")
    assembly        = inputs.get("assembly_complexity", "Simple bolted")

    mat_f  = MATERIAL_FACTOR.get(material, 1.0)
    surf_f = SURFACE_FACTOR.get(surface, 1.0)
    asm_f  = ASSEMBLY_FACTOR.get(assembly, 1.0)

    base_per_ton = _midpoint(c["fabricator_per_ton"])
    adjusted_per_ton = base_per_ton * mat_f * surf_f * asm_f

    # Process split (industry typical)
    material_cost     = adjusted_per_ton * 0.35 * tonnage
    labour_cost       = adjusted_per_ton * 0.30 * tonnage
    coatings_cost     = adjusted_per_ton * 0.12 * tonnage
    consumables_cost  = adjusted_per_ton * 0.06 * tonnage
    equipment_cost    = adjusted_per_ton * 0.07 * tonnage
    overhead_cost     = adjusted_per_ton * 0.06 * tonnage
    margin            = adjusted_per_ton * 0.04 * tonnage
    final_amount      = material_cost + labour_cost + coatings_cost + consumables_cost + equipment_cost + overhead_cost + margin

    # Add tax
    tax_amount = final_amount * c["tax_pct"] / 100.0
    grand_total = final_amount + tax_amount

    # Internal cost basis
    internal_per_ton_usd = _midpoint(INTERNAL_FABRICATOR_COST_PER_TON_USD)
    internal_cost_usd = internal_per_ton_usd * tonnage

    sanity = sanity_check(role="fabricator", total=final_amount, tonnage=tonnage, currency=c["currency"])

    return {
        "role": "fabricator",
        "country": country_code,
        "currency": c["currency"],
        "symbol": c["symbol"],
        "visible": {
            "tonnage":         _round(tonnage),
            "rate_per_ton":    _format_money(adjusted_per_ton, c),
            "rate_per_ton_raw": _round(adjusted_per_ton),
            "process_breakdown": [
                {"process": "Material (mill sections + plate)", "amount": _format_money(material_cost, c),    "amount_raw": _round(material_cost),    "pct": "35%"},
                {"process": "Shop labour (cut/weld/fit)",        "amount": _format_money(labour_cost, c),      "amount_raw": _round(labour_cost),      "pct": "30%"},
                {"process": "Coatings / surface prep",           "amount": _format_money(coatings_cost, c),    "amount_raw": _round(coatings_cost),    "pct": "12%"},
                {"process": "Consumables (weld wire / bolts)",   "amount": _format_money(consumables_cost, c), "amount_raw": _round(consumables_cost), "pct": "6%"},
                {"process": "Equipment / burn-machine",          "amount": _format_money(equipment_cost, c),   "amount_raw": _round(equipment_cost),   "pct": "7%"},
                {"process": "Overhead / QA-QC",                  "amount": _format_money(overhead_cost, c),    "amount_raw": _round(overhead_cost),    "pct": "6%"},
                {"process": "Margin",                            "amount": _format_money(margin, c),           "amount_raw": _round(margin),           "pct": "4%"},
            ],
            "subtotal":      _format_money(final_amount, c),
            "tax":           _format_money(tax_amount, c) + f"  ({c['tax_pct']:.0f}%)",
            "final_amount":  _format_money(grand_total, c),
            "final_amount_raw": _round(grand_total),
        },
        "internal": {
            "internal_cost_per_ton_usd": _round(internal_per_ton_usd),
            "internal_cost_total_usd":   _round(internal_cost_usd),
            "material_factor":   mat_f,
            "surface_factor":    surf_f,
            "assembly_factor":   asm_f,
            "labour_index":      c["labour_index"],
            "material_index":    c["material_index"],
        },
        "breakdown": [
            {"item": "Welding (linear inches)",  "qty": weld_inches, "unit": "in",  "rate": "incl. in labour"},
            {"item": "Cutting (linear meters)",  "qty": cut_meters,  "unit": "m",   "rate": "incl. in labour"},
            {"item": "Material type",            "qty": material,    "unit": "",    "rate": f"factor ×{mat_f:.2f}"},
            {"item": "Surface treatment",        "qty": surface,     "unit": "",    "rate": f"factor ×{surf_f:.2f}"},
            {"item": "Assembly complexity",      "qty": assembly,    "unit": "",    "rate": f"factor ×{asm_f:.2f}"},
        ],
        "meta": {"sanity": sanity},
    }


# ============================================================
# ENGINEER — design hours × consultancy rate
# ============================================================
def calculate_engineer(inputs: dict, country_code: str = "USA") -> dict:
    c = country(country_code)
    design_hours    = float(inputs.get("design_hours", 40))
    analysis        = inputs.get("analysis_complexity", "Medium")
    review_cycles   = max(0, int(inputs.get("review_cycles", 2)))
    calc_sheets     = max(0, int(inputs.get("calc_sheets", 8)))
    coord_meetings  = max(0, int(inputs.get("coord_meetings", 6)))

    comp = COMPLEXITY.get(analysis, COMPLEXITY["Medium"])
    cycle_hours = review_cycles * 8.0
    sheet_hours = calc_sheets * 2.5
    meeting_hours = coord_meetings * 1.5
    total_hours = (design_hours + cycle_hours + sheet_hours + meeting_hours) * comp["mult"]

    rate = _midpoint(c["engineer_hourly"])
    final_amount = total_hours * rate

    internal_rate_usd = _midpoint(INTERNAL_ENGINEER_COST_USD)
    internal_cost_usd = total_hours * internal_rate_usd

    sanity = sanity_check(role="engineer", total=final_amount, hours=total_hours, currency=c["currency"])

    return {
        "role": "engineer",
        "country": country_code,
        "currency": c["currency"],
        "symbol": c["symbol"],
        "visible": {
            "total_hours":   _round(total_hours),
            "deliverables":  [
                "Connection design package (AISC 360-22)",
                f"{calc_sheets} stamped calculation sheets",
                f"{review_cycles} review cycle(s) with EOR coordination",
                "Code-compliance memo",
                "Approval sign-off package",
            ],
            "scope_summary": f"{analysis} complexity · {review_cycles} review cycle(s) · {calc_sheets} calcs",
            "final_amount":  _format_money(final_amount, c),
            "final_amount_raw": _round(final_amount),
        },
        "internal": {
            "billable_rate_per_hour": _round(rate),
            "internal_cost_rate_usd": _round(internal_rate_usd),
            "internal_cost_total_usd": _round(internal_cost_usd),
        },
        "breakdown": [
            {"item": "Design hours",               "hours": _round(design_hours)},
            {"item": "Review cycles",              "hours": _round(cycle_hours)},
            {"item": "Calculation sheets",         "hours": _round(sheet_hours)},
            {"item": "Coordination meetings",      "hours": _round(meeting_hours)},
            {"item": "Complexity multiplier",      "hours": f"×{comp['mult']}"},
        ],
        "meta": {"sanity": sanity},
    }


# ============================================================
# PROJECT MANAGER — duration × team × rate + overhead
# ============================================================
def calculate_pm(inputs: dict, country_code: str = "USA") -> dict:
    c = country(country_code)
    duration_weeks = max(1, int(inputs.get("duration_weeks", 12)))
    team_size      = max(1, int(inputs.get("team_size", 6)))
    complexity     = inputs.get("complexity", "Medium")
    meetings_pw    = float(inputs.get("meetings_per_week", 3))
    site_visits    = max(0, int(inputs.get("site_visits", 4)))

    comp = COMPLEXITY.get(complexity, COMPLEXITY["Medium"])
    pm_hours_coordination = duration_weeks * team_size * 1.5
    pm_hours_meetings     = duration_weeks * meetings_pw * 1.0
    pm_hours_reporting    = duration_weeks * 4.0
    pm_hours_site         = site_visits * 6.0
    total_hours = (pm_hours_coordination + pm_hours_meetings + pm_hours_reporting + pm_hours_site) * comp["mult"]

    rate = _midpoint(c["pm_hourly"])
    direct_cost = total_hours * rate
    overhead    = direct_cost * 0.18  # management overhead
    final_amount = direct_cost + overhead

    internal_rate_usd = _midpoint(INTERNAL_PM_COST_USD)
    internal_cost_usd = total_hours * internal_rate_usd

    sanity = sanity_check(role="pm", total=final_amount, hours=total_hours, currency=c["currency"])

    return {
        "role": "pm",
        "country": country_code,
        "currency": c["currency"],
        "symbol": c["symbol"],
        "visible": {
            "duration_weeks": duration_weeks,
            "team_size": team_size,
            "total_hours": _round(total_hours),
            "deliverables": [
                "Weekly progress reports",
                f"{int(meetings_pw * duration_weeks)} coordination meetings",
                f"{site_visits} site visit(s)",
                "Client-facing dashboard",
                "Risk + change-order log",
            ],
            "final_amount":  _format_money(final_amount, c),
            "final_amount_raw": _round(final_amount),
        },
        "internal": {
            "billable_rate_per_hour": _round(rate),
            "internal_cost_rate_usd": _round(internal_rate_usd),
            "internal_cost_total_usd": _round(internal_cost_usd),
            "overhead_pct": 18.0,
            "direct_cost": _round(direct_cost),
            "overhead_cost": _round(overhead),
        },
        "breakdown": [
            {"item": "Team coordination",   "hours": _round(pm_hours_coordination)},
            {"item": "Meetings",            "hours": _round(pm_hours_meetings)},
            {"item": "Reporting",           "hours": _round(pm_hours_reporting)},
            {"item": "Site visits",         "hours": _round(pm_hours_site)},
            {"item": "Complexity factor",   "hours": f"×{comp['mult']}"},
        ],
        "meta": {"sanity": sanity},
    }


# ============================================================
# MODULAR — modules × assembly × transport
# ============================================================
def calculate_modular(inputs: dict, country_code: str = "USA") -> dict:
    c = country(country_code)
    module_count       = max(1, int(inputs.get("module_count", 12)))
    assembly_h_per_mod = float(inputs.get("assembly_hours_per_module", 18))
    transport_km       = float(inputs.get("transport_km", 250))
    crane_lifts        = max(0, int(inputs.get("crane_lifts", module_count)))
    prefab_complexity  = inputs.get("prefab_complexity", "Medium")

    comp = COMPLEXITY.get(prefab_complexity, COMPLEXITY["Medium"])

    base_per_module = _midpoint(c["modular_per_module"])
    per_module = base_per_module * comp["mult"]

    assembly_cost  = per_module * 0.55 * module_count
    transport_cost = (transport_km * 4.5) * module_count  # rate per km per module
    crane_cost     = crane_lifts * 1200 * (c["labour_index"])
    install_cost   = per_module * 0.35 * module_count
    margin         = per_module * 0.10 * module_count
    final_amount   = assembly_cost + transport_cost + crane_cost + install_cost + margin

    tax_amount  = final_amount * c["tax_pct"] / 100.0
    grand_total = final_amount + tax_amount

    sanity = sanity_check(role="modular", total=final_amount, modules=module_count, currency=c["currency"])

    return {
        "role": "modular",
        "country": country_code,
        "currency": c["currency"],
        "symbol": c["symbol"],
        "visible": {
            "module_count": module_count,
            "rate_per_module": _format_money(per_module, c),
            "rate_per_module_raw": _round(per_module),
            "process_breakdown": [
                {"process": "Factory assembly",   "amount": _format_money(assembly_cost, c),  "amount_raw": _round(assembly_cost)},
                {"process": "Transport / haul",   "amount": _format_money(transport_cost, c), "amount_raw": _round(transport_cost)},
                {"process": "Crane / lift",       "amount": _format_money(crane_cost, c),     "amount_raw": _round(crane_cost)},
                {"process": "Site installation",  "amount": _format_money(install_cost, c),   "amount_raw": _round(install_cost)},
                {"process": "Margin",             "amount": _format_money(margin, c),         "amount_raw": _round(margin)},
            ],
            "subtotal":     _format_money(final_amount, c),
            "tax":          _format_money(tax_amount, c) + f"  ({c['tax_pct']:.0f}%)",
            "final_amount": _format_money(grand_total, c),
            "final_amount_raw": _round(grand_total),
        },
        "internal": {
            "prefab_complexity": prefab_complexity,
            "complexity_multiplier": comp["mult"],
            "labour_index": c["labour_index"],
        },
        "breakdown": [
            {"item": "Modules",                  "qty": module_count, "unit": "ea"},
            {"item": "Assembly hrs per module",  "qty": assembly_h_per_mod, "unit": "hr"},
            {"item": "Transport distance",       "qty": transport_km, "unit": "km"},
            {"item": "Crane lifts",              "qty": crane_lifts,  "unit": "lifts"},
        ],
        "meta": {"sanity": sanity},
    }


# ============================================================
# ESTIMATOR — full visibility: combines all roles + margin + vendor
# ============================================================
def calculate_estimator(inputs: dict, country_code: str = "USA") -> dict:
    """Full integrated estimate combining detailing + fab + engineer + PM."""
    c = country(country_code)
    detailer_in = inputs.get("detailer", {})
    fabric_in   = inputs.get("fabricator", {})
    engineer_in = inputs.get("engineer", {})
    pm_in       = inputs.get("pm", {})
    target_margin_pct = float(inputs.get("target_margin_pct", 12))

    det = calculate_detailer(detailer_in, country_code) if detailer_in else None
    fab = calculate_fabricator(fabric_in, country_code) if fabric_in else None
    eng = calculate_engineer(engineer_in, country_code) if engineer_in else None
    pm  = calculate_pm(pm_in, country_code) if pm_in else None

    components = [
        ("Detailing",   det),
        ("Fabrication", fab),
        ("Engineering", eng),
        ("Project Management", pm),
    ]

    direct_total = sum(c_["visible"]["final_amount_raw"] for _, c_ in components if c_)
    contingency  = direct_total * 0.05
    margin       = direct_total * (target_margin_pct / 100.0)
    bid_total    = direct_total + contingency + margin
    tax_amount   = bid_total * c["tax_pct"] / 100.0
    grand_total  = bid_total + tax_amount

    sanity = sanity_check(role="estimator", total=grand_total, tonnage=fabric_in.get("tonnage", 0), currency=c["currency"])

    return {
        "role": "estimator",
        "country": country_code,
        "currency": c["currency"],
        "symbol": c["symbol"],
        "visible": {
            "components": [
                {
                    "label": label,
                    "amount": comp["visible"]["final_amount"] if comp else "—",
                    "amount_raw": comp["visible"]["final_amount_raw"] if comp else 0,
                    "scope": comp["visible"].get("scope_summary", "") if comp else "",
                } for label, comp in components
            ],
            "direct_total": _format_money(direct_total, c),
            "contingency":  _format_money(contingency, c) + "  (5%)",
            "margin":       _format_money(margin, c) + f"  ({target_margin_pct:.0f}%)",
            "subtotal":     _format_money(bid_total, c),
            "tax":          _format_money(tax_amount, c) + f"  ({c['tax_pct']:.0f}%)",
            "final_amount": _format_money(grand_total, c),
            "final_amount_raw": _round(grand_total),
            "per_ton_calibration": _format_money(grand_total / max(fabric_in.get("tonnage", 1), 1), c) + " / ton" if fabric_in.get("tonnage") else None,
        },
        "internal": {
            "components_detail": {label.lower(): comp for label, comp in components if comp},
            "target_margin_pct": target_margin_pct,
        },
        "breakdown": [
            {"item": label, "amount": comp["visible"]["final_amount"] if comp else "—"}
            for label, comp in components
        ],
        "meta": {"sanity": sanity},
    }


# ============================================================
# MAIN DISPATCHER
# ============================================================
CALCULATORS = {
    "detailer":   calculate_detailer,
    "fabricator": calculate_fabricator,
    "engineer":   calculate_engineer,
    "pm":         calculate_pm,
    "modular":    calculate_modular,
    "estimator":  calculate_estimator,
    "admin":      calculate_estimator,  # admin sees the full estimator view
}


def calculate(role: str, inputs: dict, country_code: str = "USA") -> dict:
    fn = CALCULATORS.get((role or "estimator").lower())
    if not fn:
        raise ValueError(f"No estimation calculator for role '{role}'")
    return fn(inputs, country_code)


def visibility_for_role(role: str) -> dict:
    """Return what each role is allowed to see in the response."""
    role = (role or "").lower()
    if role in ("estimator", "admin"):
        return {"show_internal": True, "show_breakdown": True, "show_rates": True}
    if role == "fabricator":
        return {"show_internal": False, "show_breakdown": True, "show_rates": True}
    return {"show_internal": False, "show_breakdown": True, "show_rates": False}
