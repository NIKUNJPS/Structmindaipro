"""Notifications + usage + dashboard + admin + blockchain verify endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from db import get_db
from security import get_current_admin, get_current_user, sha256_hex

router = APIRouter(tags=["platform"])


# -------- NOTIFICATIONS --------
@router.get("/api/notifications")
async def list_notifications(user=Depends(get_current_user)):
    db = get_db()
    items = await db.notifications.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    unread = sum(1 for n in items if not n.get("is_read"))
    return {"items": items, "unread": unread}


@router.put("/api/notifications/{nid}/read")
async def mark_read(nid: str, user=Depends(get_current_user)):
    db = get_db()
    await db.notifications.update_one(
        {"id": nid, "user_id": user["id"]}, {"$set": {"is_read": True}}
    )
    return {"message": "ok"}


@router.put("/api/notifications/read-all")
async def mark_all_read(user=Depends(get_current_user)):
    db = get_db()
    await db.notifications.update_many(
        {"user_id": user["id"], "is_read": False}, {"$set": {"is_read": True}}
    )
    return {"message": "ok"}


# -------- USAGE --------
@router.get("/api/usage/me")
async def usage_me(user=Depends(get_current_user)):
    db = get_db()
    full = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return {
        "analyses_used": full.get("usage_this_month", {}).get("analyses", 0),
        "analyses_limit": full.get("limits", {}).get("analyses_per_month", 5),
        "files_processed": full.get("usage_this_month", {}).get("files_processed", 0),
        "total_file_size_mb": full.get("usage_this_month", {}).get("total_file_size_mb", 0),
        "subscription_tier": full.get("subscription_tier", "free"),
        "period_start": datetime.now(timezone.utc).replace(day=1).isoformat(),
        "period_end": (datetime.now(timezone.utc).replace(day=1) + timedelta(days=32)).replace(day=1).isoformat(),
    }


# -------- DASHBOARD STATS --------
@router.get("/api/dashboard/stats")
async def dashboard_stats(user=Depends(get_current_user)):
    db = get_db()
    scope = {"owner_id": user["id"]} if user["role"] != "admin" else {}
    req_scope = {"requested_by": user["id"]} if user["role"] != "admin" else {}

    total_projects = await db.projects.count_documents({**scope, "status": {"$ne": "archived"}})
    active_analyses = await db.analyses.count_documents({**req_scope, "status": {"$in": ["queued", "processing"]}})
    open_rfis = await db.rfis.count_documents(
        {**({"created_by": user["id"]} if user["role"] != "admin" else {}), "status": {"$in": ["draft", "sent"]}}
    )
    files_processed = await db.files.count_documents(
        {**({"uploaded_by": user["id"]} if user["role"] != "admin" else {})}
    )

    # 30-day activity
    now = datetime.now(timezone.utc)
    activity = []
    for i in range(29, -1, -1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        c = await db.analyses.count_documents(
            {**req_scope, "created_at": {"$regex": f"^{day}"}}
        )
        activity.append({"date": day, "analyses": c})

    # Mode usage
    pipeline = [
        {"$match": req_scope},
        {"$group": {"_id": "$mode", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 7},
    ]
    mode_usage = []
    async for doc in db.analyses.aggregate(pipeline):
        mode_usage.append({"mode": doc["_id"], "count": doc["count"]})

    # Recent analyses
    recent = await db.analyses.find(
        req_scope,
        {"_id": 0, "id": 1, "mode": 1, "mode_label": 1, "status": 1, "created_at": 1, "issues_found": 1, "project_id": 1, "quality_score": 1},
    ).sort("created_at", -1).to_list(8)

    return {
        "stats": {
            "total_projects": total_projects,
            "active_analyses": active_analyses,
            "open_rfis": open_rfis,
            "files_processed": files_processed,
        },
        "activity": activity,
        "mode_usage": mode_usage,
        "recent_analyses": recent,
    }


# -------- BLOCKCHAIN VERIFY (SHA-256 MVP) --------
@router.post("/api/blockchain/verify")
async def verify_hash(payload: dict):
    """Verify a SHA-256 hash against stored records (analyses, files)."""
    db = get_db()
    h = (payload.get("hash") or "").lower().strip()
    if not h:
        raise HTTPException(status_code=400, detail="Provide 'hash' field")
    a = await db.analyses.find_one(
        {"blockchain_hash": h},
        {"_id": 0, "id": 1, "mode_label": 1, "created_at": 1, "completed_at": 1},
    )
    f = await db.files.find_one(
        {"blockchain_hash": h},
        {"_id": 0, "id": 1, "original_name": 1, "created_at": 1, "size_mb": 1},
    )
    return {
        "verified": bool(a or f),
        "hash": h,
        "analysis": a,
        "file": f,
        "anchor": "SHA-256 · MongoDB ledger · Polygon anchoring deferred to v2",
    }


# -------- ADMIN --------
@router.get("/api/admin/users")
async def admin_users(user=Depends(get_current_admin)):
    db = get_db()
    items = await db.users.find(
        {}, {"_id": 0, "password_hash": 0, "otp_hash": 0, "otp_expiry": 0, "otp_purpose": 0}
    ).sort("created_at", -1).to_list(500)
    return {"items": items, "total": len(items)}


@router.put("/api/admin/users/{uid}")
async def admin_update_user(uid: str, payload: dict, user=Depends(get_current_admin)):
    db = get_db()
    allowed = {"role", "is_active", "subscription_tier", "is_verified"}
    updates = {k: v for k, v in payload.items() if k in allowed and v is not None}
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.users.update_one({"id": uid}, {"$set": updates})
    fresh = await db.users.find_one(
        {"id": uid}, {"_id": 0, "password_hash": 0, "otp_hash": 0}
    )
    return fresh


@router.delete("/api/admin/users/{uid}")
async def admin_disable_user(uid: str, user=Depends(get_current_admin)):
    db = get_db()
    await db.users.update_one({"id": uid}, {"$set": {"is_active": False}})
    return {"message": "User disabled"}


@router.get("/api/admin/analytics")
async def admin_analytics(user=Depends(get_current_admin)):
    db = get_db()
    total_users = await db.users.count_documents({})
    active_users = await db.users.count_documents({"is_active": True})
    total_projects = await db.projects.count_documents({})
    total_analyses = await db.analyses.count_documents({})
    complete = await db.analyses.count_documents({"status": "complete"})
    failed = await db.analyses.count_documents({"status": "failed"})
    total_files = await db.files.count_documents({})
    total_rfis = await db.rfis.count_documents({})

    by_role_pipeline = [{"$group": {"_id": "$role", "c": {"$sum": 1}}}]
    by_role = []
    async for d in db.users.aggregate(by_role_pipeline):
        by_role.append({"role": d["_id"], "count": d["c"]})

    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_projects": total_projects,
        "total_analyses": total_analyses,
        "complete_analyses": complete,
        "failed_analyses": failed,
        "total_files": total_files,
        "total_rfis": total_rfis,
        "users_by_role": by_role,
    }


@router.get("/api/admin/audit-log")
async def admin_audit_log(limit: int = 100, user=Depends(get_current_admin)):
    db = get_db()
    items = await db.audit_log.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return {"items": items, "total": len(items)}


# -------- OUTPUTS (list all generated exports for user) --------
@router.get("/api/outputs")
async def list_outputs(user=Depends(get_current_user)):
    db = get_db()
    q = {"status": "complete"}
    if user["role"] != "admin":
        q["requested_by"] = user["id"]
    items = await db.analyses.find(
        q,
        {"_id": 0, "id": 1, "mode": 1, "mode_label": 1, "project_id": 1, "exports": 1,
         "blockchain_hash": 1, "completed_at": 1, "issues_found": 1, "quality_score": 1, "model_used": 1},
    ).sort("completed_at", -1).to_list(200)
    # attach project names
    pids = list({i["project_id"] for i in items if i.get("project_id")})
    projs = {}
    if pids:
        async for p in db.projects.find({"id": {"$in": pids}}, {"_id": 0, "id": 1, "name": 1}):
            projs[p["id"]] = p["name"]
    for i in items:
        i["project_name"] = projs.get(i.get("project_id") or "", "Quick Analysis")
    return {"items": items}
