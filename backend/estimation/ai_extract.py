"""AI-driven drawing analysis for estimation.

Given uploaded drawings + a role, asks STRUCTMIND CORE to extract the structural
quantities needed for cost estimation.

Returns a deterministic dict that the calculator can consume.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Iterable

from google import genai

from config import settings
from gemini_service import MODEL_CHAIN, engine_label

logger = logging.getLogger(__name__)

# Gemini Client
client = genai.Client(api_key=settings.llm_key)

# ─────────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────────

FABRICATOR_EXTRACT_PROMPT = """
You are STRUCTMIND CORE, a senior structural-steel fabricator's estimator.

Your ONLY task:
Read the attached structural drawings, BOM, or schedule and extract the total fabricated tonnage required for the scope.

Return ONLY valid JSON.

{
  "tonnage": 184.5,
  "members_counted": 250,
  "primary_material": "A992 W-shapes",
  "drawings_seen": 12,
  "confidence": "high",
  "notes": "Estimated using BOM and steel member schedules"
}
"""

DETAILER_EXTRACT_PROMPT = """
You are STRUCTMIND CORE, a senior structural-steel detailing lead.

Your ONLY task:
Read the attached structural drawings and quantify the detailing workload.

Return ONLY valid JSON.

{
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

    Returns:
        (data, engine_label)
    """

    if not file_paths:
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
Analyze all uploaded drawings/files.

Return ONLY the JSON object requested in the system prompt.

No markdown.
No explanation.
No extra text.
"""

    last_err: Exception | None = None

    for model_name in MODEL_CHAIN:

        try:
            logger.info(
                "AI estimate extraction · tier=%s · session=%s",
                model_name,
                session_id,
            )

            uploaded_files = []

            # Upload files to Gemini
            for file_path, mime_type in file_paths:

                try:
                    uploaded_file = client.files.upload(
                        file=file_path,
                    )

                    uploaded_files.append(uploaded_file)

                except Exception as file_error:
                    logger.warning(
                        "File upload failed for %s: %s",
                        file_path,
                        file_error,
                    )

            # Build content
            contents = [
                system_prompt,
                user_prompt,
            ]

            contents.extend(uploaded_files)

            # Generate response
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
            )

            response_text = response.text.strip()

            data = _extract_json(response_text)

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