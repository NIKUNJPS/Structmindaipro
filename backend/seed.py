"""Seed the super-admin account on startup (idempotent)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import settings
from db import get_db
from security import hash_password, sha256_hex

logger = logging.getLogger(__name__)


async def seed_admin() -> None:
    if not (settings.admin_email and settings.admin_password):
        logger.info("Seed admin: no credentials configured")
        return

    db = get_db()
    existing = await db.users.find_one({"email": settings.admin_email.lower()})
    now = datetime.now(timezone.utc).isoformat()
    if existing:
        # Ensure admin role + verified + active
        await db.users.update_one(
            {"email": settings.admin_email.lower()},
            {
                "$set": {
                    "role": "admin",
                    "is_verified": True,
                    "is_active": True,
                    "subscription_tier": "enterprise",
                    "limits": {
                        "analyses_per_month": 10000,
                        "max_file_size_mb": 500,
                        "modes_available": ["*"],
                    },
                    "updated_at": now,
                }
            },
        )
        logger.info("Seed admin: updated existing %s to admin", settings.admin_email)
        return

    uid = sha256_hex(f"admin:{settings.admin_email}:{now}")[:32]
    doc = {
        "id": uid,
        "email": settings.admin_email.lower(),
        "password_hash": hash_password(settings.admin_password),
        "first_name": settings.admin_first_name,
        "last_name": settings.admin_last_name,
        "company": "4XStruct Inc.",
        "country": "India",
        "role": "admin",
        "phone": "",
        "avatar_url": "",
        "is_verified": True,
        "is_active": True,
        "subscription_tier": "enterprise",
        "usage_this_month": {"analyses": 0, "files_processed": 0, "total_file_size_mb": 0},
        "limits": {"analyses_per_month": 10000, "max_file_size_mb": 500, "modes_available": ["*"]},
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(doc)
    logger.info("Seed admin: created %s", settings.admin_email)
