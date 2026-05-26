"""
detailer_prompts.py
All AI analysis mode prompts for the DETAILER role.
Each mode key must match exactly what is stored in the database
feature_permissions.allowedModes for Detailer users.

HOW TO ADD A MODE:
  1. Add a new key to DETAILER_MODES dict below
  2. Set "label" (display name shown in UI)
  3. Set "group" (category grouping in mode selector)
  4. Set "description" (shown as tooltip/subtitle)
  5. Paste your full prompt into "prompt" field
  6. Go to Super Admin panel → Feature Manager → enable for desired users

HOW TO EDIT A MODE:
  Simply update the "prompt" value — changes take effect immediately.

HOW TO DISABLE A MODE:
  Either remove it from this dict OR disable it per-user in Super Admin panel.
"""

from prompts.shared_rules import GLOBAL_FORMAT_RULES, WEIGHT_TABLE  # noqa: F401

DETAILER_SYSTEM = """
# ── PASTE DETAILER ROLE SYSTEM PERSONA HERE ──────────────────────────────────
# This is the system-level persona sent to the AI before every Detailer analysis.
# Example: "You are SteelSight — a senior structural steel shop drawing specialist..."
# ─────────────────────────────────────────────────────────────────────────────
"""

DETAILER_MODES: dict[str, dict] = {

    # ── MODE 1 ──────────────────────────────────────────────────────────────
    "DETAILER_MODE_1": {
        "label":       "Mode 1 — Paste Your Label",
        "group":       "Group Name",
        "description": "Paste your mode description here.",
        "icon":        "FileText",
        "time":        "~X min",
        "prompt": f"""
# ── PASTE YOUR DETAILER MODE 1 PROMPT HERE ───────────────────────────────────
# The line below automatically appends your global formatting rules.
{GLOBAL_FORMAT_RULES}
# ─────────────────────────────────────────────────────────────────────────────
""",
    },

    # ── MODE 2 ──────────────────────────────────────────────────────────────
    "DETAILER_MODE_2": {
        "label":       "Mode 2 — Paste Your Label",
        "group":       "Group Name",
        "description": "Paste your mode description here.",
        "icon":        "ClipboardCheck",
        "time":        "~X min",
        "prompt": f"""
# ── PASTE YOUR DETAILER MODE 2 PROMPT HERE ───────────────────────────────────
{GLOBAL_FORMAT_RULES}
# ─────────────────────────────────────────────────────────────────────────────
""",
    },

    # ── MODE 3 ──────────────────────────────────────────────────────────────
    "DETAILER_MODE_3": {
        "label":       "Mode 3 — Paste Your Label",
        "group":       "Group Name",
        "description": "Paste your mode description here.",
        "icon":        "LayoutList",
        "time":        "~X min",
        "prompt": f"""
# ── PASTE YOUR DETAILER MODE 3 PROMPT HERE ───────────────────────────────────
{GLOBAL_FORMAT_RULES}
# ─────────────────────────────────────────────────────────────────────────────
""",
    },

    # ── MODE 4 ──────────────────────────────────────────────────────────────
    "DETAILER_MODE_4": {
        "label":       "Mode 4 — Paste Your Label",
        "group":       "Group Name",
        "description": "Paste your mode description here.",
        "icon":        "AlertTriangle",
        "time":        "~X min",
        "prompt": f"""
# ── PASTE YOUR DETAILER MODE 4 PROMPT HERE ───────────────────────────────────
{GLOBAL_FORMAT_RULES}
# ─────────────────────────────────────────────────────────────────────────────
""",
    },

    # ── MODE 5 ──────────────────────────────────────────────────────────────
    "DETAILER_MODE_5": {
        "label":       "Mode 5 — Paste Your Label",
        "group":       "Group Name",
        "description": "Paste your mode description here.",
        "icon":        "Package",
        "time":        "~X min",
        "prompt": f"""
# ── PASTE YOUR DETAILER MODE 5 PROMPT HERE ───────────────────────────────────
{GLOBAL_FORMAT_RULES}
# ─────────────────────────────────────────────────────────────────────────────
""",
    },

    # ── MODE 6 ──────────────────────────────────────────────────────────────
    "DETAILER_MODE_6": {
        "label":       "Mode 6 — Paste Your Label",
        "group":       "Group Name",
        "description": "Paste your mode description here.",
        "icon":        "MessagesSquare",
        "time":        "real-time",
        "prompt": f"""
# ── PASTE YOUR DETAILER MODE 6 PROMPT HERE ───────────────────────────────────
{GLOBAL_FORMAT_RULES}
# ─────────────────────────────────────────────────────────────────────────────
""",
    },

    # ── ADD MORE MODES AS NEEDED — COPY THE BLOCK ABOVE ─────────────────────
}
