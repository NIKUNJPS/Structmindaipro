"""Seed super-admin account(s) on startup (idempotent)."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from config import settings
from db import get_db
from security import hash_password, sha256_hex

logger = logging.getLogger(__name__)


async def _upsert_admin(email: str, password: str, first: str, last: str) -> None:
    if not (email and password):
        return
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    enterprise_limits = {
        "analyses_per_month": 10000,
        "max_file_size_mb": 500,
        "modes_available": ["*"],
    }
    existing = await db.users.find_one({"email": email.lower()})
    if existing:
        await db.users.update_one(
            {"email": email.lower()},
            {
                "$set": {
                    "role": "admin",
                    "is_verified": True,
                    "is_active": True,
                    "subscription_tier": "enterprise",
                    "limits": enterprise_limits,
                    "updated_at": now,
                }
            },
        )
        logger.info("Seed admin · refreshed %s", email)
        return

    uid = sha256_hex(f"admin:{email}:{now}")[:32]
    doc = {
        "id": uid,
        "email": email.lower(),
        "password_hash": hash_password(password),
        "first_name": first,
        "last_name": last,
        "company": "4XStruct Inc.",
        "country": "India",
        "role": "admin",
        "phone": "",
        "avatar_url": "",
        "is_verified": True,
        "is_active": True,
        "subscription_tier": "enterprise",
        "usage_this_month": {"analyses": 0, "files_processed": 0, "total_file_size_mb": 0},
        "limits": enterprise_limits,
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(doc)
    logger.info("Seed admin · created %s", email)


async def seed_admin() -> None:
    await _upsert_admin(
        settings.admin_email,
        settings.admin_password,
        settings.admin_first_name,
        settings.admin_last_name,
    )
    await _upsert_admin(
        os.environ.get("ADMIN_EMAIL_2", ""),
        os.environ.get("ADMIN_PASSWORD_2", ""),
        os.environ.get("ADMIN_FIRST_NAME_2", "Admin"),
        os.environ.get("ADMIN_LAST_NAME_2", "User"),
    )
