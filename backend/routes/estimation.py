"""Estimation API — role-aware deterministic engine + PDF export."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from db import get_db
from estimation.engine import (
    CALCULATORS,
    calculate,
    visibility_for_role,
)
from estimation.pdf import render_pdf
from estimation.rates import COUNTRY_RATES, supported_countries
from security import get_current_user, sha256_hex

router = APIRouter(prefix="/api/estimation", tags=["estimation"])


@router.get("/countries")
async def list_countries(user=Depends(get_current_user)):
    return {"countries": supported_countries()}


@router.get("/schema/{role}")
async def schema_for_role(role: str, user=Depends(get_current_user)):
    """Return the input schema the frontend should render for the given role."""
    role = role.lower()
    schemas = {
        "detailer": {
            "title": "Detailing Estimate",
            "subtitle": "Hours-based estimate from drawing scope and complexity.",
            "fields": [
                {"key": "drawings",         "label": "Number of drawings", "type": "number", "default": 60,  "min": 1, "max": 5000},
                {"key": "complexity",       "label": "Complexity",         "type": "select", "default": "Medium", "options": ["Low","Medium","High","AESS","Critical"]},
                {"key": "connection_count", "label": "Connection count",   "type": "number", "default": 320, "min": 0, "max": 50000},
                {"key": "revisions",        "label": "Expected revision cycles", "type": "number", "default": 2, "min": 0, "max": 20},
                {"key": "modeling_hours",   "label": "3D modeling hours",  "type": "number", "default": 80,  "min": 0},
                {"key": "checking_hours",   "label": "QC checking hours",  "type": "number", "default": 40,  "min": 0},
            ],
            "kpis": ["total_hours", "timeline_weeks", "final_amount"],
        },
        "fabricator": {
            "title": "Fabrication Estimate",
            "subtitle": "Tonnage-based estimate with process breakdown.",
            "fields": [
                {"key": "tonnage",             "label": "Total tonnage", "type": "number", "default": 220, "min": 0.1},
                {"key": "material_type",       "label": "Material",      "type": "select", "default": "Carbon Steel",
                 "options": ["Carbon Steel","HSS","Galvanised","Stainless","Weathering (A588)","Aluminium"]},
                {"key": "weld_inches",         "label": "Total weld length (in)", "type": "number", "default": 4200, "min": 0},
                {"key": "cut_meters",          "label": "Total cut length (m)",   "type": "number", "default": 2200, "min": 0},
                {"key": "surface_treatment",   "label": "Surface treatment",      "type": "select", "default": "SSPC-SP6 + 2-coat",
                 "options": ["Shop primer only","SSPC-SP6 + 2-coat","SSPC-SP10 + 3-coat","Hot-dip galvanised","Intumescent fire-rated"]},
                {"key": "assembly_complexity", "label": "Assembly complexity",    "type": "select", "default": "Mixed bolt/weld",
                 "options": ["Simple bolted","Mixed bolt/weld","Heavy welded","Architectural AESS","Custom curved"]},
            ],
            "kpis": ["tonnage", "rate_per_ton", "final_amount"],
        },
        "engineer": {
            "title": "Engineering Estimate",
            "subtitle": "Design-hours estimate per international consultancy standards.",
            "fields": [
                {"key": "design_hours",        "label": "Design hours",            "type": "number", "default": 120, "min": 1},
                {"key": "analysis_complexity", "label": "Analysis complexity",     "type": "select", "default": "Medium", "options": ["Low","Medium","High","AESS","Critical"]},
                {"key": "review_cycles",       "label": "Review cycles",           "type": "number", "default": 3,   "min": 0},
                {"key": "calc_sheets",         "label": "Calculation sheets",      "type": "number", "default": 14,  "min": 0},
                {"key": "coord_meetings",      "label": "Coordination meetings",   "type": "number", "default": 10,  "min": 0},
            ],
            "kpis": ["total_hours", "final_amount"],
        },
        "pm": {
            "title": "Project Management Estimate",
            "subtitle": "Effort + overhead estimate by duration and team size.",
            "fields": [
                {"key": "duration_weeks",   "label": "Project duration (weeks)", "type": "number", "default": 16, "min": 1, "max": 260},
                {"key": "team_size",        "label": "Team size",                "type": "number", "default": 8,  "min": 1, "max": 200},
                {"key": "complexity",       "label": "Project complexity",       "type": "select", "default": "Medium", "options": ["Low","Medium","High","AESS","Critical"]},
                {"key": "meetings_per_week","label": "Coord. meetings per week", "type": "number", "default": 3,  "min": 0},
                {"key": "site_visits",      "label": "Site visits planned",      "type": "number", "default": 6,  "min": 0},
            ],
            "kpis": ["duration_weeks", "team_size", "final_amount"],
        },
        "modular": {
            "title": "Modular Assembly Estimate",
            "subtitle": "Kit-of-parts estimate based on module count and logistics.",
            "fields": [
                {"key": "module_count",              "label": "Module count",              "type": "number", "default": 18, "min": 1},
                {"key": "assembly_hours_per_module", "label": "Assembly hours per module", "type": "number", "default": 22, "min": 1},
                {"key": "transport_km",              "label": "Transport distance (km)",   "type": "number", "default": 380, "min": 0},
                {"key": "crane_lifts",               "label": "Crane lifts planned",       "type": "number", "default": 18, "min": 0},
                {"key": "prefab_complexity",         "label": "Prefab complexity",         "type": "select", "default": "Medium", "options": ["Low","Medium","High","AESS","Critical"]},
            ],
            "kpis": ["module_count", "rate_per_module", "final_amount"],
        },
        "estimator": {
            "title": "Full Bid Estimate",
            "subtitle": "Integrated bid: detailing + fab + engineering + PM with margin and sanity check.",
            "fields": [
                {"key": "tonnage",            "label": "Total tonnage",     "type": "number", "default": 220, "min": 0.1},
                {"key": "drawings",           "label": "Number of drawings","type": "number", "default": 60,  "min": 1},
                {"key": "complexity",         "label": "Overall complexity","type": "select", "default": "Medium", "options": ["Low","Medium","High","AESS","Critical"]},
                {"key": "design_hours",       "label": "Engineering hours", "type": "number", "default": 120, "min": 0},
                {"key": "duration_weeks",     "label": "Duration (weeks)",  "type": "number", "default": 16,  "min": 1},
                {"key": "team_size",          "label": "Team size",         "type": "number", "default": 8,   "min": 1},
                {"key": "target_margin_pct",  "label": "Target margin %",   "type": "number", "default": 12,  "min": 0, "max": 60},
            ],
            "kpis": ["direct_total", "margin", "final_amount"],
        },
    }
    schemas["admin"] = schemas["estimator"]
    schema = schemas.get(role)
    if not schema:
        raise HTTPException(status_code=400, detail=f"No estimation schema for role '{role}'")
    return {"role": role, "schema": schema}


def _compose_estimator_inputs(payload: dict) -> dict:
    """Map the flat estimator form into the nested component inputs."""
    return {
        "detailer": {
            "drawings": payload.get("drawings", 60),
            "complexity": payload.get("complexity", "Medium"),
            "revisions": payload.get("revisions", 2),
            "connection_count": payload.get("connection_count", payload.get("drawings", 60) * 5),
            "modeling_hours": payload.get("modeling_hours", 80),
            "checking_hours": payload.get("checking_hours", 40),
        },
        "fabricator": {
            "tonnage": payload.get("tonnage", 220),
            "material_type": payload.get("material_type", "Carbon Steel"),
            "weld_inches": payload.get("weld_inches", 4200),
            "cut_meters": payload.get("cut_meters", 2200),
            "surface_treatment": payload.get("surface_treatment", "SSPC-SP6 + 2-coat"),
            "assembly_complexity": payload.get("assembly_complexity", "Mixed bolt/weld"),
        },
        "engineer": {
            "design_hours": payload.get("design_hours", 120),
            "analysis_complexity": payload.get("complexity", "Medium"),
            "review_cycles": payload.get("review_cycles", 3),
            "calc_sheets": payload.get("calc_sheets", 14),
            "coord_meetings": payload.get("coord_meetings", 10),
        },
        "pm": {
            "duration_weeks": payload.get("duration_weeks", 16),
            "team_size": payload.get("team_size", 8),
            "complexity": payload.get("complexity", "Medium"),
            "meetings_per_week": payload.get("meetings_per_week", 3),
            "site_visits": payload.get("site_visits", 6),
        },
        "target_margin_pct": payload.get("target_margin_pct", 12),
    }


@router.post("/calculate")
async def post_calculate(payload: dict, user=Depends(get_current_user)):
    role     = (payload.get("role") or user["role"]).lower()
    country  = payload.get("country") or "USA"
    inputs   = payload.get("inputs") or {}
    project  = payload.get("project_name") or "Quick Estimate"

    if role not in CALCULATORS:
        raise HTTPException(status_code=400, detail=f"Unknown role '{role}'")

    # Non-admin users can only run their own role's calculator
    if user["role"] != "admin" and role != user["role"]:
        raise HTTPException(status_code=403, detail="You may only run your own role's estimate.")

    # If estimator/admin, flatten form into component inputs
    if role in ("estimator", "admin"):
        inputs = _compose_estimator_inputs(inputs)

    result = calculate(role, inputs, country)

    # Role visibility filter — strip internal keys if role isn't allowed
    vis = visibility_for_role(user["role"])
    if not vis["show_internal"]:
        result = {k: v for k, v in result.items() if k != "internal"}

    # Persist
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": sha256_hex(f"est:{user['id']}:{role}:{now}")[:24],
        "user_id": user["id"],
        "role": role,
        "country": country,
        "project_name": project,
        "inputs": payload.get("inputs") or {},
        "result": result,
        "created_at": now,
    }
    await db.estimates.insert_one(record)
    record.pop("_id", None)
    return record


@router.get("/")
async def list_estimates(user=Depends(get_current_user)):
    db = get_db()
    q = {} if user["role"] == "admin" else {"user_id": user["id"]}
    items = await db.estimates.find(q, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"items": items}


@router.get("/{eid}")
async def get_estimate(eid: str, user=Depends(get_current_user)):
    db = get_db()
    e = await db.estimates.find_one({"id": eid}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Estimate not found")
    if user["role"] != "admin" and e["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return e


@router.get("/{eid}/pdf")
async def download_pdf(eid: str, user=Depends(get_current_user)):
    db = get_db()
    e = await db.estimates.find_one({"id": eid})
    if not e:
        raise HTTPException(status_code=404, detail="Estimate not found")
    if user["role"] != "admin" and e["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Re-compute so estimator gets the full breakdown including internal (PDF version is
    # always written from the canonical calculator output, never from a cached visible-only copy).
    inputs = e["inputs"]
    role = e["role"]
    if role in ("estimator", "admin"):
        inputs = _compose_estimator_inputs(inputs)
    full_result = calculate(role, inputs, e["country"])

    # If the viewer isn't an estimator/admin, hide internal layer before rendering
    vis = visibility_for_role(user["role"])
    if not vis["show_internal"] and role not in ("estimator", "admin"):
        full_result.pop("internal", None)

    path = render_pdf(full_result, e.get("project_name", "Project"), filename=f"{eid}.pdf")
    if not Path(path).exists():
        raise HTTPException(status_code=500, detail="PDF render failed")
    return FileResponse(
        path,
        filename=f"StructMind_{role.title()}_Estimate.pdf",
        media_type="application/pdf",
    )


@router.delete("/{eid}")
async def delete_estimate(eid: str, user=Depends(get_current_user)):
    db = get_db()
    e = await db.estimates.find_one({"id": eid})
    if not e:
        raise HTTPException(status_code=404, detail="Estimate not found")
    if user["role"] != "admin" and e["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    await db.estimates.delete_one({"id": eid})
    return {"message": "Estimate deleted"}
