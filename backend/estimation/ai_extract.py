"""AI-driven drawing analysis for estimation.

Given uploaded drawings + a role, asks STRUCTMIND CORE to extract the structural
quantities needed for cost estimation.

Returns a deterministic dict that the calculator can consume.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from typing import Iterable

from google.genai import types

from config import settings
from gemini_service import (
    MODEL_CHAIN,
    _cleanup_files,
    _get_client,
    _upload_files,
    engine_label,
    prepare_file_batches,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────────

FABRICATOR_EXTRACT_PROMPT = """
You are STRUCTMIND CORE, a senior structural-steel fabricator's estimator.

Your task: read EVERY attached structural drawing, BOM, schedule and document and
compute the total fabricated tonnage with a disciplined member-by-member take-off.

METHOD (perform internally, do not narrate):
  1. Scan every sheet and every document. Use the BOM / member schedule where present;
     otherwise quantify members from framing plans and details.
  2. For each member: identify profile, quantity and length, then apply the published
     AISC / standard unit weight (kg/m) for that profile. Plates and bars: compute from
     volume × 7,850 kg/m³. Convert all weights to metric tons.
  3. Add a 3.0% allowance for bolts, welds, connection plates and accessories.
  4. SUM every member. Do not sample, round members away, or estimate a bulk figure —
     the tonnage must be the sum of the actual take-off.
  5. Be exhaustive: include secondary steel, miscellaneous, embeds and anchors.

Round the final tonnage to exactly two decimal places.

Return ONLY valid JSON (no markdown, no commentary):

{
  "tonnage": 184.52,
  "members_counted": 250,
  "primary_material": "A992 W-shapes",
  "drawings_seen": 12,
  "accessory_allowance_pct": 3.0,
  "notes": "Member-by-member take-off from BOM and framing plans; AISC unit weights applied."
}
"""

DETAILER_EXTRACT_PROMPT = """
You are STRUCTMIND CORE, a senior structural-steel detailing lead.

Your ONLY task:
Read the attached structural drawings and estimate the detailing workload in HOURS.

Estimate total_hours as the realistic effort for a competent detailer to produce
the full fabrication-ready model and shop drawings for this scope, including:
  - production/shop drawings (modelling + drawing time),
  - connection detailing,
  - checking/QC, and
  - a reasonable revision allowance.

Use the drawing count, connection count and complexity to derive total_hours.
A typical band is 1.5-8 hours per production drawing depending on complexity.

Return ONLY valid JSON.

{
  "total_hours": 540.0,
  "drawings": 120,
  "connections": 450,
  "complexity": "High",
  "complexity_multiplier": 1.35,
  "drawings_seen": 18,
  "confidence": "medium",
  "notes": "Heavy welded moment connections detected"
}
"""


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """
    Extract JSON object from Gemini response.
    """

    if not text:
        raise ValueError("Empty model response")

    cleaned = text.strip()

    # Remove markdown fences
    cleaned = cleaned.replace("```json", "")
    cleaned = cleaned.replace("```", "").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("No JSON found in response")

    json_blob = cleaned[start:end + 1]

    return json.loads(json_blob)


# Numeric fields are additive across batches (each batch covers a different
# subset of the drawing set); everything else is taken from the first batch.
_SUM_FIELDS = (
    "tonnage", "members_counted", "drawings_seen",
    "total_hours", "drawings", "connections",
)


def _combine_extractions(dicts: list[dict]) -> dict:
    """Deterministically fold per-batch extraction JSON into one result.

    No LLM merge pass — these are locked numeric figures, so batches are
    summed directly (never sampled, never dropped) to preserve accuracy.
    """
    if len(dicts) == 1:
        return dicts[0]

    combined = dict(dicts[0])
    for key in _SUM_FIELDS:
        if any(key in d for d in dicts):
            combined[key] = round(sum(float(d.get(key, 0) or 0) for d in dicts), 2)

    notes = [d.get("notes") for d in dicts if d.get("notes")]
    if notes:
        combined["notes"] = " | ".join(notes)

    return combined


# ─────────────────────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────────────────────

async def extract_quantities(
    *,
    role: str,
    session_id: str,
    file_paths: Iterable[tuple[str, str]],
) -> tuple[dict, str]:

    """
    Extract quantities from drawings using Gemini.

    Large drawing sets are split into page/size-safe batches (same logic as
    the main analysis pipeline) so a single oversized PDF can't blow past
    Gemini's per-request document limit. Batch results are summed
    deterministically into one locked figure.

    Returns:
        (data, engine_label)
    """
    file_paths_list = list(file_paths)
    if not file_paths_list:
        raise ValueError(
            "Upload at least one drawing to run AI estimation."
        )

    if role == "fabricator":
        system_prompt = FABRICATOR_EXTRACT_PROMPT

    elif role == "detailer":
        system_prompt = DETAILER_EXTRACT_PROMPT

    else:
        raise ValueError(
            f"AI estimation only supports detailer or fabricator (got '{role}')"
        )

    user_prompt = """
Analyze all uploaded drawings/files in this batch.

Return ONLY the JSON object requested in the system prompt.

No markdown.
No explanation.
No extra text.
"""

    batches, scratch_dir = prepare_file_batches(file_paths_list)
    last_err: Exception | None = None

    try:
        for model_name in MODEL_CHAIN:
            try:
                logger.info(
                    "AI estimate extraction · tier=%s · session=%s · batches=%d",
                    model_name, session_id, len(batches),
                )
                client = _get_client()
                batch_results: list[dict] = []

                for i, batch in enumerate(batches, 1):
                    uploaded_files = await _upload_files(client, batch) if batch else []
                    try:
                        file_parts = [
                            types.Part(
                                file_data=types.FileData(
                                    file_uri=f.uri, mime_type=f.mime_type,
                                )
                            )
                            for f in uploaded_files
                        ]
                        contents = [
                            types.Content(
                                role="user",
                                parts=[types.Part(text=user_prompt)] + file_parts,
                            )
                        ]
                        response = client.models.generate_content(
                            model=model_name,
                            contents=contents,
                            config=types.GenerateContentConfig(
                                system_instruction=system_prompt,
                                temperature=0.0,
                                max_output_tokens=8192,
                            ),
                        )
                        response_text = (response.text or "").strip()
                        batch_results.append(_extract_json(response_text))
                    finally:
                        if uploaded_files:
                            _cleanup_files(client, uploaded_files)

                data = _combine_extractions(batch_results)
                return data, engine_label(model_name)

            except Exception as e:
                last_err = e
                logger.warning(
                    "AI extract tier %s failed: %s",
                    model_name,
                    e,
                )
                continue

        raise RuntimeError(
            f"STRUCTMIND CORE could not extract quantities. Last error: {last_err}"
        )
    finally:
        if scratch_dir:
            shutil.rmtree(scratch_dir, ignore_errors=True)