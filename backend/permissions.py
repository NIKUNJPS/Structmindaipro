"""Feature-permissions document — per-user granular access matrix (managed by super_admin)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db import get_db


# Default permissions returned when none exists yet for the user
def default_permissions(role: str) -> dict[str, Any]:
    base = {
        "analysesPerMonth":   10,
        "maxFileSizeMb":      25,
        "maxFilesPerAnalysis": 3,
        "allowedModes":       [],          # admin enables modes manually
        "allowedExports":     ["markdown", "pdf"],
        "canUploadFiles":     True,
        "canCreateProjects":  True if role == "detailer" else False,
        "canViewHistory":     True,
        "canDownloadReports": True,
        "canSendRfis":        False,
        "canViewAuditLog":    False,
        "blockchainAnchoring": False,
        "canRunEstimation":   role == "fabricator",
        "estimationCountries": ["USA"],
        "showDashboardStats": True,
        "showActivityChart":  False,
    }
    return base


async def get_permissions(user_id: str, role: str) -> dict[str, Any]:
    """Fetch (or auto-create with defaults) the feature_permissions document for a user."""
    db = get_db()
    doc = await db.feature_permissions.find_one({"userId": user_id}, {"_id": 0})
    if doc:
        return doc

    if role == "super_admin":
        # Super admin has no caps — return wide-open permissions (not persisted)
        return {
            "userId": user_id,
            "role": "super_admin",
            "analysesPerMonth": -1,
            "maxFileSizeMb": 500,
            "maxFilesPerAnalysis": 50,
            "allowedModes": ["*"],          # wildcard — all modes
            "allowedExports": ["pdf","word","excel","csv","markdown","json"],
            "canUploadFiles": True,
            "canCreateProjects": True,
            "canViewHistory": True,
            "canDownloadReports": True,
            "canSendRfis": True,
            "canViewAuditLog": True,
            "blockchainAnchoring": True,
            "canRunEstimation": True,
            "estimationCountries": ["USA","Canada","UK","UAE","Australia","India","Europe","Saudi Arabia","Singapore"],
            "showDashboardStats": True,
            "showActivityChart": True,
        }

    # Persist default permissions on first access
    now = datetime.now(timezone.utc).isoformat()
    doc = {"userId": user_id, "role": role, **default_permissions(role),
           "lastUpdatedBy": None, "updatedAt": now, "createdAt": now}
    await db.feature_permissions.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def update_permissions(user_id: str, updates: dict, admin_id: str) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    updates = {k: v for k, v in updates.items() if v is not None}
    updates["lastUpdatedBy"] = admin_id
    updates["updatedAt"] = now
    await db.feature_permissions.update_one(
        {"userId": user_id}, {"$set": updates}, upsert=True,
    )
    fresh = await db.feature_permissions.find_one({"userId": user_id}, {"_id": 0})
    return fresh


def mode_allowed(perms: dict, mode_id: str) -> bool:
    allowed = perms.get("allowedModes", [])
    return "*" in allowed or mode_id in allowed


def export_allowed(perms: dict, fmt: str) -> bool:
    allowed = perms.get("allowedExports", [])
    return "*" in allowed or fmt in allowed
