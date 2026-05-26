"""Sanity check — detects over-priced / under-priced estimates and returns warnings."""
from __future__ import annotations

# Market-floor and market-ceiling per-unit benchmarks (USD-equivalent).
# Tuned for 2026 mid-size commercial project.
FLOORS = {
    "detailer_per_drawing":     45,    # USD
    "fabricator_per_ton":       1800,
    "engineer_per_hour":        70,
    "pm_per_hour":              55,
    "modular_per_module":       8000,
    "estimator_per_ton":        3200,
}
CEILINGS = {
    "detailer_per_drawing":     520,
    "fabricator_per_ton":       7500,   # includes high-end AESS / seismic
    "engineer_per_hour":        350,
    "pm_per_hour":              280,
    "modular_per_module":       95000,
    "estimator_per_ton":        9500,
}

# Rough USD conversion table (only for sanity normalisation — not displayed)
USD_RATE = {"USD":1.0,"CAD":0.74,"GBP":1.27,"AED":0.27,"AUD":0.66,"INR":0.012,"EUR":1.09,"SAR":0.27,"SGD":0.74}


def _to_usd(amount: float, currency: str) -> float:
    return amount * USD_RATE.get(currency, 1.0)


def sanity_check(role: str, total: float, currency: str = "USD",
                 drawings: int = 0, tonnage: float = 0, hours: float = 0,
                 modules: int = 0) -> dict:
    """Return {status: ok|over|under|review, message: str}."""
    role = (role or "").lower()
    total_usd = _to_usd(total, currency)

    pairs = []
    if role == "detailer" and drawings > 0:
        per_unit = total_usd / drawings
        pairs.append(("detailer_per_drawing", per_unit, "per drawing"))
    if role == "fabricator" and tonnage > 0:
        per_unit = total_usd / tonnage
        pairs.append(("fabricator_per_ton", per_unit, "per ton"))
    if role in ("engineer", "pm") and hours > 0:
        per_unit = total_usd / hours
        pairs.append((f"{role}_per_hour", per_unit, "per hour"))
    if role == "modular" and modules > 0:
        per_unit = total_usd / modules
        pairs.append(("modular_per_module", per_unit, "per module"))
    if role in ("estimator", "admin") and tonnage > 0:
        per_unit = total_usd / tonnage
        pairs.append(("estimator_per_ton", per_unit, "per ton"))

    if not pairs:
        return {"status": "ok", "message": "Within expected commercial range.", "checks": []}

    checks = []
    overall = "ok"
    for key, per_unit, label in pairs:
        floor = FLOORS.get(key, 0)
        ceil  = CEILINGS.get(key, 1e12)
        if per_unit < floor:
            status = "under"
            note = f"USD-equivalent {per_unit:.0f} {label} is below the practical market floor of USD {floor:.0f}."
            if overall == "ok":
                overall = "under"
        elif per_unit > ceil:
            status = "over"
            note = f"USD-equivalent {per_unit:.0f} {label} exceeds the practical market ceiling of USD {ceil:.0f}."
            overall = "over"
        else:
            status = "ok"
            note = f"USD-equivalent {per_unit:.0f} {label} sits within market band [{floor:.0f} – {ceil:.0f}]."
        checks.append({"metric": label, "usd_equivalent": round(per_unit, 2), "floor": floor, "ceiling": ceil, "status": status, "note": note})

    msg_map = {
        "ok":    "Estimate is within practical commercial range for the selected market.",
        "over":  "Estimate exceeds the realistic market ceiling — review assumptions before publishing.",
        "under": "Estimate sits below the realistic market floor — risk of underbidding.",
    }
    return {"status": overall, "message": msg_map[overall], "checks": checks}
