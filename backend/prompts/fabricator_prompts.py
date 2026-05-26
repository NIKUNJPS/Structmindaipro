"""
fabricator_prompts.py
All AI analysis mode prompts for the FABRICATOR role.
Each mode key must match exactly what is stored in the database
feature_permissions.allowedModes for Fabricator users.

HOW TO ADD A MODE:
  1. Add a new key to FABRICATOR_MODES dict below
  2. Set label, group, description, icon, time, prompt
  3. Go to Super Admin panel → Feature Manager → enable for desired users

HOW TO DISABLE A MODE:
  Either remove it from this dict OR disable it per-user in Super Admin panel.
"""

from prompts.shared_rules import GLOBAL_FORMAT_RULES, WEIGHT_TABLE  # noqa: F401

FABRICATOR_SYSTEM = """
# ── PASTE FABRICATOR ROLE SYSTEM PERSONA HERE ────────────────────────────────
# This is the system-level persona sent to the AI before every Fabricator analysis.
# Example: "You are SteelSight — a senior steel fabrication specialist..."
# ─────────────────────────────────────────────────────────────────────────────
"""

FABRICATOR_MODES: dict[str, dict] = {

    # ── MODE 1 ──────────────────────────────────────────────────────────────
    "FABRICATOR_MODE_1": {
        "label":       "Mode 1 — Paste Your Label",
        "group":       "Group Name",
        "description": "Paste your mode description here.",
        "icon":        "Hammer",
        "time":        "~X min",
        "prompt": f"""
# ── PASTE YOUR FABRICATOR MODE 1 PROMPT HERE ─────────────────────────────────
{GLOBAL_FORMAT_RULES}
# ─────────────────────────────────────────────────────────────────────────────
""",
    },

    # ── MODE 2 ──────────────────────────────────────────────────────────────
    "FABRICATOR_MODE_2": {
        "label":       "Mode 2 — Paste Your Label",
        "group":       "Group Name",
        "description": "Paste your mode description here.",
        "icon":        "Cpu",
        "time":        "~X min",
        "prompt": f"""
# ── PASTE YOUR FABRICATOR MODE 2 PROMPT HERE ─────────────────────────────────
{GLOBAL_FORMAT_RULES}
# ─────────────────────────────────────────────────────────────────────────────
""",
    },

    # ── MODE 3 ──────────────────────────────────────────────────────────────
    "FABRICATOR_MODE_3": {
        "label":       "Mode 3 — Paste Your Label",
        "group":       "Group Name",
        "description": "Paste your mode description here.",
        "icon":        "ShoppingCart",
        "time":        "~X min",
        "prompt": f"""
# ── PASTE YOUR FABRICATOR MODE 3 PROMPT HERE ─────────────────────────────────
{GLOBAL_FORMAT_RULES}
# ─────────────────────────────────────────────────────────────────────────────
""",
    },

    # ── MODE 4 ──────────────────────────────────────────────────────────────
    "FABRICATOR_MODE_4": {
        "label":       "Mode 4 — Paste Your Label",
        "group":       "Group Name",
        "description": "Paste your mode description here.",
        "icon":        "Package",
        "time":        "~X min",
        "prompt": f"""
# ── PASTE YOUR FABRICATOR MODE 4 PROMPT HERE ─────────────────────────────────
{GLOBAL_FORMAT_RULES}
# ─────────────────────────────────────────────────────────────────────────────
""",
    },

    # ── MODE 5 ──────────────────────────────────────────────────────────────
    "FABRICATOR_MODE_5": {
        "label":       "Mode 5 — Paste Your Label",
        "group":       "Group Name",
        "description": "Paste your mode description here.",
        "icon":        "MessagesSquare",
        "time":        "real-time",
        "prompt": f"""
# ── PASTE YOUR FABRICATOR MODE 5 PROMPT HERE ─────────────────────────────────
{GLOBAL_FORMAT_RULES}
# ─────────────────────────────────────────────────────────────────────────────
""",
    },

    # ── ADD MORE MODES AS NEEDED — COPY THE BLOCK ABOVE ─────────────────────
}
