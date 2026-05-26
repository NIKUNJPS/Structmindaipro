"""AI-driven drawing analysis for estimation.

Given uploaded drawings + a role, asks STRUCTMIND CORE to extract the structural
quantities needed for cost estimation:
  • Fabricator → total fabricated tonnage (in tons)
  • Detailer   → drawing count, weighted complexity factor

Returns a deterministic dict that the calculator can consume to apply the
user-supplied LOW / HIGH rate band. No prices, no rates, no guesses.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Iterable

from emergentintegrations.llm.chat import (
    FileContentWithMimeType,
    LlmChat,
    UserMessage,
)

from config import settings
from gemini_service import MODEL_CHAIN, engine_label

logger = logging.getLogger(__name__)

# ─── PROMPTS ───────────────────────────────────────────────────────────
FABRICATOR_EXTRACT_PROMPT = """You are STRUCTMIND CORE, a senior structural-steel fabricator's estimator.

Your ONLY task: read the attached structural drawings, BOM, or schedule and extract the **total fabricated tonnage** required for the scope.

How to compute tonnage:
 1. Identify every member, plate, angle, channel, HSS, gusset, stiffener listed in the drawings or BOMs.
 2. Use AISC or local steel section weights (kg/m or lb/ft).
 3. Add bolt/weld/connection accessories at 3–4% of base steel weight.
 4. Convert to **metric tons** (1 ton = 1000 kg).

If multiple sheets exist, sum across all sheets — do NOT report per-sheet.
If a BOM is present, use it as the primary source.
If only plan-views are given without member sizes, give your best estimate using typical AISC W-shapes for the spans/loads shown.

DO NOT estimate cost. DO NOT apply a rate. Quantities only.

Return ONLY a single JSON object — no markdown, no commentary — with this exact shape:
{
  "tonnage": <number, metric tons, e.g. 184.5>,
  "members_counted": <int, number of distinct steel members identified>,
  "primary_material": "<short string, e.g. 'A992 W-shapes' or 'HSS + plate'>",
  "drawings_seen": <int>,
  "confidence": "<one of: low | medium | high>",
  "notes": "<one short sentence (≤120 chars) about how you arrived at the tonnage and any caveats>"
}
"""

DETAILER_EXTRACT_PROMPT = """You are STRUCTMIND CORE, a senior structural-steel detailing lead.

Your ONLY task: read the attached structural drawings and quantify the **detailing workload**.

How to quantify:
 1. Count the **number of distinct production drawings** that will need to be produced for shop fabrication (every beam mark, column mark, brace, stair, embed, etc. that needs its own sheet).
 2. Count the **number of connections** (every bolted or welded splice, moment connection, base plate, brace gusset, etc.).
 3. Assess overall **complexity**: Low (simple bolted bay, regular grid), Medium (mixed bolted/welded), High (heavy moment frames or transfer trusses), AESS (architecturally exposed), Critical (seismic-critical or curved/skewed).

DO NOT estimate cost. DO NOT apply a rate. Quantities only.

Return ONLY a single JSON object — no markdown, no commentary — with this exact shape:
{
  "drawings": <int, total production drawings to be issued>,
  "connections": <int, total connections requiring detail>,
  "complexity": "<one of: Low | Medium | High | AESS | Critical>",
  "complexity_multiplier": <float, derived from complexity: Low=0.85, Medium=1.0, High=1.35, AESS=1.8, Critical=2.1>,
  "drawings_seen": <int>,
  "confidence": "<one of: low | medium | high>",
  "notes": "<one short sentence (≤120 chars) about how you arrived at the count and any caveats>"
}
"""


def _extract_json(text: str) -> dict:
    """Pull the first valid JSON object from the model's response."""
    if not text:
        raise ValueError("Empty model response.")
    # Strip code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    # Find first {...} block
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in model output: {cleaned[:200]}")
    blob = cleaned[start : end + 1]
    return json.loads(blob)


async def extract_quantities(
    *,
    role: str,
    session_id: str,
    file_paths: Iterable[tuple[str, str]],
) -> tuple[dict, str]:
    """Call the LLM with the role-specific extraction prompt.

    Returns (extracted_dict, engine_label). Raises ValueError if no files are
    supplied or the model returns malformed JSON on every fallback tier.
    """
    file_contents = [
        FileContentWithMimeType(file_path=p, mime_type=mt) for p, mt in file_paths
    ]
    if not file_contents:
        raise ValueError("Upload at least one drawing to run AI estimation.")

    if role == "fabricator":
        system_prompt = FABRICATOR_EXTRACT_PROMPT
    elif role == "detailer":
        system_prompt = DETAILER_EXTRACT_PROMPT
    else:
        raise ValueError(f"AI estimation only supports detailer or fabricator (got '{role}').")

    user_text = (
        "Analyze every attached file (drawings, BOMs, schedules). Return the JSON object "
        "described in the system prompt. No prose. No markdown. Just the JSON."
    )

    last_err: Exception | None = None
    for model in MODEL_CHAIN:
        try:
            chat = LlmChat(
                api_key=settings.llm_key,
                session_id=session_id,
                system_message=system_prompt,
            ).with_model("gemini", model)
            response = await chat.send_message(
                UserMessage(text=user_text, file_contents=file_contents or None)
            )
            logger.info("AI estimate extraction · tier=%s · session=%s", model, session_id)
            data = _extract_json(response)
            return data, engine_label(model)
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("AI extract tier %s failed: %s", model, e)
            continue

    raise RuntimeError(f"STRUCTMIND CORE could not extract quantities. Last error: {last_err}")
