"""Estimation API — Detailer + Fabricator only.

Wired to feature_permissions: `canRunEstimation`, `estimationCountries`, audit logging.
Fabricator schema requires user-provided per-ton cost range.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from db import get_db
from estimation.engine import CALCULATORS, calculate
from estimation.pdf import render_pdf
from estimation.rates import supported_countries
from middleware.permission_guard import (
    audit_log,
    check_country,
    check_feature,
    load_permissions,
)
from security import block_write_if_readonly, get_current_user, sha256_hex

router = APIRouter(prefix="/api/estimation", tags=["estimation"])


# ─── COUNTRIES ──────────────────────────────────────────────────────────
@router.get("/countries")
async def list_countries(user=Depends(get_current_user), perms: dict = Depends(load_permissions)):
    """Return only the countries this user is allowed to estimate against."""
    all_countries = supported_countries()
    if user["role"] == "super_admin":
        return {"countries": all_countries}
    allowed = set(perms.get("estimationCountries", []))
    return {"countries": [c for c in all_countries if c["code"] in allowed]}


# ─── SCHEMA ─────────────────────────────────────────────────────────────
@router.get("/schema/{role}")
async def schema_for_role(role: str, user=Depends(get_current_user)):
    role = role.lower()
    if role not in ("detailer", "fabricator"):
        raise HTTPException(status_code=400, detail=f"Estimation only supported for detailer or fabricator (got '{role}').")
    # Lock non-super-admins to their own role's schema
    if user["role"] != "super_admin" and role != user["role"]:
        raise HTTPException(status_code=403, detail="You may only request your own role's schema.")

    schemas = {
        "detailer": {
            "title": "Detailing Estimate",
            "subtitle": "Hours-based estimate from drawing scope and complexity.",
            "fields": [
                {"key": "drawings",         "label": "Number of drawings", "type": "number", "default": 60,  "min": 1, "max": 5000},
                {"key": "complexity",       "label": "Complexity",         "type": "select", "default": "Medium", "options": ["Low", "Medium", "High", "AESS", "Critical"]},
                {"key": "connection_count", "label": "Connection count",   "type": "number", "default": 320, "min": 0, "max": 50000},
                {"key": "revisions",        "label": "Expected revision cycles", "type": "number", "default": 2,  "min": 0, "max": 20},
                {"key": "modeling_hours",   "label": "3D modeling hours",  "type": "number", "default": 80,  "min": 0},
                {"key": "checking_hours",   "label": "QC checking hours",  "type": "number", "default": 40,  "min": 0},
            ],
            "kpis": ["total_hours", "timeline_weeks", "final_amount"],
        },
        "fabricator": {
            "title": "Fabrication Estimate",
            "subtitle": "Tonnage × user-provided per-ton range. Output is a low → high range.",
            "fields": [
                {"key": "tonnage",            "label": "Total tonnage",                   "type": "number", "default": 220, "min": 0.1, "required": True},
                {"key": "cost_per_ton_low",   "label": "Your per-ton cost — LOW",         "type": "number", "default": 2400, "min": 1,   "required": True, "help": "Lower bound of your shop's per-ton cost band (local currency)."},
                {"key": "cost_per_ton_high",  "label": "Your per-ton cost — HIGH",        "type": "number", "default": 3600, "min": 1,   "required": True, "help": "Upper bound of your shop's per-ton cost band (local currency)."},
                {"key": "material_type",      "label": "Material",                        "type": "select", "default": "Carbon Steel",
                 "options": ["Carbon Steel", "HSS", "Galvanised", "Stainless", "Weathering (A588)", "Aluminium"]},
                {"key": "weld_inches",        "label": "Total weld length (in)",          "type": "number", "default": 4200, "min": 0},
                {"key": "cut_meters",         "label": "Total cut length (m)",            "type": "number", "default": 2200, "min": 0},
                {"key": "surface_treatment",  "label": "Surface treatment",               "type": "select", "default": "SSPC-SP6 + 2-coat",
                 "options": ["Shop primer only", "SSPC-SP6 + 2-coat", "SSPC-SP10 + 3-coat", "Hot-dip galvanised", "Intumescent fire-rated"]},
                {"key": "assembly_complexity", "label": "Assembly complexity",            "type": "select", "default": "Mixed bolt/weld",
                 "options": ["Simple bolted", "Mixed bolt/weld", "Heavy welded", "Architectural AESS", "Custom curved"]},
            ],
            "kpis": ["tonnage", "rate_band", "final_amount"],
        },
    }
    return {"role": role, "schema": schemas[role]}


# ─── CALCULATE ──────────────────────────────────────────────────────────
@router.post("/calculate")
async def post_calculate(
    payload: dict,
    request: Request,
    user=Depends(get_current_user),
    perms: dict = Depends(load_permissions),
):
    block_write_if_readonly(user)
    role     = (payload.get("role") or user["role"]).lower()
    country  = payload.get("country") or "USA"
    inputs   = payload.get("inputs") or {}
    project  = payload.get("project_name") or "Quick Estimate"

    if role not in CALCULATORS or role == "super_admin":
        # super_admin selects an explicit role to run; we still require detailer/fabricator here
        if role not in ("detailer", "fabricator"):
            raise HTTPException(status_code=400, detail="Estimation supports only 'detailer' or 'fabricator'.")

    # Non-super-admin can only run their own role
    if user["role"] != "super_admin" and role != user["role"]:
        raise HTTPException(status_code=403, detail="You may only run your own role's estimate.")

    if user["role"] != "super_admin":
        check_feature(perms, "canRunEstimation")
        check_country(perms, country)

    # Validate fabricator-specific required inputs at API boundary
    if role == "fabricator":
        try:
            low  = float(inputs.get("cost_per_ton_low", 0))
            high = float(inputs.get("cost_per_ton_high", 0))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="cost_per_ton_low and cost_per_ton_high must be numbers.")
        if low <= 0 or high <= 0:
            raise HTTPException(status_code=422, detail="Fabricator estimates require cost_per_ton_low and cost_per_ton_high (both > 0).")

    try:
        result = calculate(role, inputs, country)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

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
    await audit_log(user["id"], "estimation.calculate", "estimate", record["id"], request,
                    extra={"role": role, "country": country})
    record.pop("_id", None)
    return record


@router.get("/")
async def list_estimates(user=Depends(get_current_user)):
    db = get_db()
    q = {} if user["role"] == "super_admin" else {"user_id": user["id"]}
    items = await db.estimates.find(q, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"items": items}


@router.get("/{eid}")
async def get_estimate(eid: str, user=Depends(get_current_user)):
    db = get_db()
    e = await db.estimates.find_one({"id": eid}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Estimate not found")
    if user["role"] != "super_admin" and e["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return e


@router.get("/{eid}/pdf")
async def download_pdf(
    eid: str,
    request: Request,
    user=Depends(get_current_user),
    perms: dict = Depends(load_permissions),
):
    db = get_db()
    e = await db.estimates.find_one({"id": eid})
    if not e:
        raise HTTPException(status_code=404, detail="Estimate not found")
    if user["role"] != "super_admin" and e["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    if user["role"] != "super_admin":
        check_feature(perms, "canDownloadReports")

    try:
        full_result = calculate(e["role"], e["inputs"], e["country"])
    except ValueError as ex:
        raise HTTPException(status_code=422, detail=str(ex))

    path = render_pdf(full_result, e.get("project_name", "Project"), filename=f"{eid}.pdf")
    if not Path(path).exists():
        raise HTTPException(status_code=500, detail="PDF render failed")
    await audit_log(user["id"], "estimation.pdf", "estimate", eid, request)
    return FileResponse(
        path,
        filename=f"StructMind_{e['role'].title()}_Estimate.pdf",
        media_type="application/pdf",
    )


@router.delete("/{eid}")
async def delete_estimate(eid: str, request: Request, user=Depends(get_current_user)):
    block_write_if_readonly(user)
    db = get_db()
    e = await db.estimates.find_one({"id": eid})
    if not e:
        raise HTTPException(status_code=404, detail="Estimate not found")
    if user["role"] != "super_admin" and e["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    await db.estimates.delete_one({"id": eid})
    await audit_log(user["id"], "estimation.delete", "estimate", eid, request)
    return {"message": "Estimate deleted"}
