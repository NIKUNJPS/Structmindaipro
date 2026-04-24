"""Analysis routes: queue, status, list, export, rerun, result."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse

from ai_modes import MODES, list_modes_for_role, mode_label
from config import settings
from db import get_db
from export_service import EXPORT_DIR, generate_all_exports
from gemini_service import run_analysis
from models import AnalysisCreate
from security import get_current_user, sha256_hex

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analyses", tags=["analyses"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run_analysis_task(analysis_id: str):
    """Background task to call Gemini, update analysis, generate exports."""
    db = get_db()
    started = time.time()
    analysis = await db.analyses.find_one({"id": analysis_id})
    if not analysis:
        logger.error("Analysis %s not found", analysis_id)
        return

    mode = MODES.get(analysis["mode"])
    if not mode:
        await db.analyses.update_one(
            {"id": analysis_id},
            {"$set": {"status": "failed", "error_message": "Unknown mode", "completed_at": _now_iso()}},
        )
        return

    await db.analyses.update_one(
        {"id": analysis_id}, {"$set": {"status": "processing", "stage": "analyzing"}}
    )

    # Collect files
    file_docs = []
    if analysis.get("file_ids"):
        file_docs = await db.files.find({"id": {"$in": analysis["file_ids"]}}).to_list(50)
    file_pairs: list[tuple[str, str]] = []
    for f in file_docs:
        path = Path(settings.upload_dir) / f["storage_key"]
        if path.exists() and f.get("mime_type"):
            # gemini supports pdf / image / csv / text
            mt = f["mime_type"]
            if mt in {
                "application/pdf",
                "text/plain",
                "text/csv",
                "image/png",
                "image/jpeg",
                "image/webp",
            }:
                file_pairs.append((str(path), mt))

    try:
        if not settings.llm_key:
            raise RuntimeError(
                "No LLM key configured. Set GEMINI_API_KEY or EMERGENT_LLM_KEY in /app/backend/.env"
            )
        text_prompt = analysis.get("input_text") or (
            "Analyse the attached project package per your system instructions."
            if file_pairs
            else "Generate a high-quality analysis using realistic structural steel detailing assumptions for a representative mid-size US fabrication scope (~180 tons, 3-storey steel-framed building)."
        )
        output, model_used = await run_analysis(
            session_id=analysis_id,
            system_prompt=mode["prompt"],
            user_text=text_prompt,
            file_paths=file_pairs,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Analysis failed")
        await db.analyses.update_one(
            {"id": analysis_id},
            {
                "$set": {
                    "status": "failed",
                    "error_message": str(e),
                    "completed_at": _now_iso(),
                }
            },
        )
        return

    elapsed = round(time.time() - started, 2)
    output_hash = sha256_hex(output)

    # Heuristic issue counting (based on severity keywords in output)
    crit = output.upper().count("CRITICAL")
    major = output.upper().count("MAJOR")
    minor = output.upper().count("MINOR") + output.upper().count("OBSERVATION")
    issues = {"critical": crit, "major": major, "minor": minor, "total": crit + major + minor}
    quality = max(0, min(100, 100 - crit * 8 - major * 3 - minor * 1))

    # Generate exports
    proj = await db.projects.find_one({"id": analysis.get("project_id")}) if analysis.get("project_id") else None
    meta = {
        "id": analysis_id,
        "mode_label": mode["label"],
        "project_name": proj["name"] if proj else "Quick Analysis",
        "completed_at": _now_iso(),
        "model_used": model_used,
        "blockchain_hash": output_hash,
    }
    exports = generate_all_exports(output, meta)

    await db.analyses.update_one(
        {"id": analysis_id},
        {
            "$set": {
                "status": "complete",
                "stage": "complete",
                "output_markdown": output,
                "model_used": model_used,
                "processing_time_seconds": elapsed,
                "issues_found": issues,
                "quality_score": quality,
                "blockchain_hash": output_hash,
                "exports": [
                    {
                        "format": e["format"],
                        "url": f"/api/analyses/{analysis_id}/export/{e['format']}",
                        "generated_at": _now_iso(),
                    }
                    for e in exports
                    if e.get("path")
                ],
                "completed_at": _now_iso(),
            }
        },
    )

    # Notify user
    user_id = analysis["requested_by"]
    await db.notifications.insert_one(
        {
            "id": sha256_hex(f"notif:{analysis_id}:{_now_iso()}"),
            "user_id": user_id,
            "type": "analysis_complete",
            "title": "Analysis complete",
            "message": f"{mode['label']} completed in {elapsed}s",
            "is_read": False,
            "action_url": f"/analyses/{analysis_id}",
            "created_at": _now_iso(),
        }
    )

    # Increment usage
    await db.users.update_one(
        {"id": user_id}, {"$inc": {"usage_this_month.analyses": 1}}
    )


@router.get("/modes")
async def list_modes(user=Depends(get_current_user)):
    return {"modes": list_modes_for_role(user["role"]), "groups": [
        "Project Intake", "Quality Control", "Quantification", "Commercial",
        "Scheduling", "Specialist", "Assistant",
    ]}


@router.post("")
async def create_analysis(
    data: AnalysisCreate,
    background: BackgroundTasks,
    user=Depends(get_current_user),
):
    db = get_db()
    if data.mode not in MODES:
        raise HTTPException(status_code=400, detail="Unknown analysis mode")
    mode = MODES[data.mode]
    if user["role"] != "admin" and user["role"] not in mode["roles"]:
        raise HTTPException(status_code=403, detail="Your role cannot run this mode")

    # Usage enforcement
    full = await db.users.find_one({"id": user["id"]})
    limit = full.get("limits", {}).get("analyses_per_month", 5)
    used = full.get("usage_this_month", {}).get("analyses", 0)
    if used >= limit and user["role"] != "admin":
        raise HTTPException(status_code=402, detail=f"Monthly analysis limit reached ({limit}). Upgrade plan.")

    # Project access check
    if data.project_id:
        p = await db.projects.find_one({"id": data.project_id})
        if not p:
            raise HTTPException(status_code=404, detail="Project not found")
        if user["role"] != "admin" and p["owner_id"] != user["id"] and not any(
            t.get("user_id") == user["id"] for t in p.get("team_members", [])
        ):
            raise HTTPException(status_code=403, detail="Access denied to project")

    now = _now_iso()
    aid = sha256_hex(f"analysis:{user['id']}:{data.mode}:{now}")[:24]
    doc = {
        "id": aid,
        "project_id": data.project_id,
        "file_ids": data.file_ids,
        "requested_by": user["id"],
        "requested_by_name": f"{full.get('first_name','')} {full.get('last_name','')}".strip(),
        "mode": data.mode,
        "mode_label": mode["label"],
        "status": "queued",
        "stage": "queued",
        "model_used": "",
        "input_text": data.input_text,
        "output_markdown": "",
        "processing_time_seconds": 0,
        "issues_found": {"critical": 0, "major": 0, "minor": 0, "total": 0},
        "quality_score": 0,
        "blockchain_hash": "",
        "exports": [],
        "error_message": "",
        "created_at": now,
        "completed_at": None,
    }
    await db.analyses.insert_one(doc)
    background.add_task(_run_analysis_task, aid)
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_analyses(
    project_id: str | None = None,
    limit: int = 50,
    user=Depends(get_current_user),
):
    db = get_db()
    q: dict = {}
    if project_id:
        q["project_id"] = project_id
    if user["role"] != "admin":
        q["requested_by"] = user["id"]
    items = await db.analyses.find(q, {"_id": 0, "output_markdown": 0}).sort("created_at", -1).to_list(limit)
    return {"items": items, "total": len(items)}


@router.get("/{aid}")
async def get_analysis(aid: str, user=Depends(get_current_user)):
    db = get_db()
    a = await db.analyses.find_one({"id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if user["role"] != "admin" and a["requested_by"] != user["id"]:
        # allow teammates
        if a.get("project_id"):
            p = await db.projects.find_one({"id": a["project_id"]})
            if not p or (p["owner_id"] != user["id"] and not any(
                t.get("user_id") == user["id"] for t in p.get("team_members", [])
            )):
                raise HTTPException(status_code=403, detail="Access denied")
        else:
            raise HTTPException(status_code=403, detail="Access denied")
    return a


@router.get("/{aid}/status")
async def get_status(aid: str, user=Depends(get_current_user)):
    db = get_db()
    a = await db.analyses.find_one(
        {"id": aid},
        {"_id": 0, "status": 1, "stage": 1, "processing_time_seconds": 1, "model_used": 1, "error_message": 1},
    )
    if not a:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return a


@router.post("/{aid}/rerun")
async def rerun_analysis(
    aid: str, background: BackgroundTasks, user=Depends(get_current_user)
):
    db = get_db()
    a = await db.analyses.find_one({"id": aid})
    if not a:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if user["role"] != "admin" and a["requested_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    await db.analyses.update_one(
        {"id": aid},
        {
            "$set": {
                "status": "queued",
                "stage": "queued",
                "output_markdown": "",
                "error_message": "",
                "exports": [],
                "completed_at": None,
            }
        },
    )
    background.add_task(_run_analysis_task, aid)
    return {"message": "Analysis re-queued"}


@router.get("/{aid}/export/{fmt}")
async def download_export(aid: str, fmt: str, user=Depends(get_current_user)):
    db = get_db()
    a = await db.analyses.find_one({"id": aid})
    if not a:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if user["role"] != "admin" and a["requested_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    ext_map = {"pdf": "pdf", "docx": "docx", "xlsx": "xlsx", "csv": "csv", "markdown": "md"}
    ext = ext_map.get(fmt)
    if not ext:
        raise HTTPException(status_code=400, detail="Unsupported format")
    path = EXPORT_DIR / f"{aid}.{ext}"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Export not generated yet")
    media = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
        "md": "text/markdown",
    }
    filename = f"{a.get('mode_label','report').replace(' ', '_')}.{ext}"
    return FileResponse(str(path), filename=filename, media_type=media.get(ext, "application/octet-stream"))


@router.delete("/{aid}")
async def delete_analysis(aid: str, user=Depends(get_current_user)):
    db = get_db()
    a = await db.analyses.find_one({"id": aid})
    if not a:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if user["role"] != "admin" and a["requested_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    await db.analyses.delete_one({"id": aid})
    return {"message": "Analysis deleted"}
