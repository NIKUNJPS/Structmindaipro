"""AI-driven drawing analysis for estimation.

Given uploaded drawings + a role, asks STRUCTMIND CORE to extract the structural
quantities needed for cost estimation.

Returns a deterministic dict that the calculator can consume.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from typing import Iterable

from google.genai import types

from config import settings
from estimation.takeoff import build_takeoff
from gemini_service import (
    MAX_PARALLEL_BATCHES,
    _active_models,
    _cleanup_files_async,
    _file_parts,
    _get_client,
    _upload_files,
    engine_label,
    generate_once,
    prepare_file_batches,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────────

FABRICATOR_EXTRACT_PROMPT = """
You are STRUCTMIND CORE, a principal structural-steel estimator performing a
quantity take-off. Your ONLY job is to READ the drawings and LIST every steel
member exactly as drawn. Do NOT calculate weights or tonnage — a verified
engine weighs every line from the section tables. Accuracy of profile,
quantity and length is everything.

READ EVERY SHEET: plans, elevations, sections, details, schedules, BOMs, cut
lists, general notes. Do not skip or sample any sheet.

WHAT TO LIST (one JSON object per member line):
  - Columns, beams, girders, rafters, trusses (chords + webs), bracing,
    purlins, girts, eave struts, joists (as steel sections), lintels,
    stairs (stringers, landings), handrails, ladders, platforms, grating
    frames, embeds, base plates, cap plates, gusset / shear / end plates,
    stiffeners, and any other fabricated steel shown.
  - Connection plates ONLY when sized on the drawings (thickness × width and
    length). Do not invent connection material.

COUNTING RULES — never double count:
  1. If a BOM / member schedule / cut list exists, it is authoritative: list
     its rows with their TOTAL quantity and source "bom". Then list plan-only
     members that are NOT in the schedule.
  2. Without a schedule, count members on framing PLANS (source "plan") —
     one line per mark per sheet with the count shown on that sheet. Use
     elevations / sections only to read lengths, never to count again.
  3. A typical member repeated on several floors/plans is listed once per
     sheet it appears on, with that sheet's count.
  4. "TYP." / "SIM." members: count every occurrence that is drawn or
     dimensioned; state the basis in "note".

LENGTH: copy the length exactly as dimensioned on the drawing — e.g.
  "24'-6 1/2\"" or "7468" (mm). Use the member's centre-to-centre / grid
  dimension when no cut length is shown. Never leave length empty if any
  dimension, grid spacing or level difference lets you determine it; when
  derived, say how in "note".

PROFILE: copy the designation exactly — W18x35, HSS6x6x3/8, L4x4x1/2,
  C10x15.3, PIPE6STD, PL1/2x10, W310x97, UB457x191x67, 460UB67.1, IPE300,
  HEB200, ISMB300, SHS100x100x6, CHS168.3x6. Plates: "PL<thk>x<width>" with
  length = plate length.

Return ONLY this JSON (no markdown):
{
  "units": "imperial" | "metric",
  "drawings_seen": 12,
  "sheets": ["S-101", "S-201"],
  "primary_material": "ASTM A992 W-shapes",
  "members": [
    {"mark": "B1", "profile": "W18x35", "qty": 4, "length": "24'-6\"",
     "sheet": "S-201", "category": "beam", "source": "plan",
     "grade": "A992", "unit_weight_kg_m": null, "note": ""}
  ],
  "notes": "scope observations, missing information, assumptions"
}

category is one of: column, beam, girder, rafter, truss, brace, purlin, girt,
strut, joist, lintel, stair, handrail, ladder, platform, grating, embed,
anchor, plate, connection, stiffener, base plate, misc.
source is one of: bom, schedule, plan, elevation, section, detail.
unit_weight_kg_m: fill ONLY for non-standard sections (built-up, cold-formed
Z/C purlins, proprietary) using the value printed on the drawings, else null.
For items measured by area (grating, checker plate, deck) add "weight_kg"
when the drawings give enough data to compute it, and explain in "note".
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

def _salvage_members(text: str) -> dict:
    """Recover every complete member object from a truncated JSON response."""
    start = text.find('"members"')
    if start == -1:
        raise ValueError("No JSON found in response")
    arr = text.find("[", start)
    decoder = json.JSONDecoder()
    members, i = [], arr + 1
    while i < len(text):
        while i < len(text) and text[i] in " \r\n\t,":
            i += 1
        if i >= len(text) or text[i] != "{":
            break
        try:
            obj, end = decoder.raw_decode(text, i)
        except ValueError:
            break
        members.append(obj)
        i = end
    head = {}
    for key in ("units", "primary_material"):
        m = re.search(rf'"{key}"\s*:\s*"([^"]*)"', text)
        if m:
            head[key] = m.group(1)
    m = re.search(r'"drawings_seen"\s*:\s*(\d+)', text)
    if m:
        head["drawings_seen"] = int(m.group(1))
    return {**head, "members": members, "_truncated": True}


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
        if '"members"' in cleaned:
            return _salvage_members(cleaned)
        raise ValueError("No JSON found in response")

    json_blob = cleaned[start:end + 1]

    try:
        return json.loads(json_blob)
    except ValueError:
        if '"members"' in cleaned:
            return _salvage_members(cleaned)
        raise


# Numeric fields are additive across batches (each batch covers a different
# subset of the drawing set); everything else is taken from the first batch.
_SUM_FIELDS = (
    "tonnage", "members_counted", "drawings_seen",
    "total_hours", "drawings", "connections",
)


def _combine_extractions(dicts: list[dict]) -> dict:
    if any("members" in d for d in dicts):
        return build_takeoff(dicts)
    return _sum_extractions(dicts)


def _sum_extractions(dicts: list[dict]) -> dict:
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
    client = _get_client()
    sem = asyncio.Semaphore(max(1, MAX_PARALLEL_BATCHES))

    async def run_batch(i: int, batch: list[tuple[str, str]]) -> tuple[dict, str]:
        """Extract one batch, walking the model chain. Files upload once and
        are reused across models; the SDK call never blocks the event loop."""
        async with sem:
            uploaded_files = await _upload_files(client, batch) if batch else []
            try:
                contents = [
                    types.Content(
                        role="user",
                        parts=[types.Part(text=user_prompt)] + _file_parts(uploaded_files),
                    )
                ]
                last: Exception | None = None
                for model_name in _active_models():
                    try:
                        text, truncated = await generate_once(
                            client=client,
                            model_name=model_name,
                            system_prompt=system_prompt,
                            contents=contents,
                            max_output_tokens=65_536,
                            temperature=0.0,
                            json_output=True,
                            label=f"extract batch={i}/{len(batches)}",
                        )
                        data = _extract_json(text)
                        if truncated:
                            data["_truncated"] = True
                        return data, model_name
                    except Exception as e:  # noqa: BLE001
                        last = e
                        logger.warning(
                            "AI extract batch %d tier %s failed: %s", i, model_name, e,
                        )
                raise RuntimeError(f"batch {i} failed on every tier: {last}")
            finally:
                await _cleanup_files_async(client, uploaded_files)

    try:
        logger.info(
            "AI estimate extraction · session=%s · batches=%d · chain=%s",
            session_id, len(batches), _active_models(),
        )
        results = await asyncio.gather(
            *[run_batch(i, b) for i, b in enumerate(batches, 1)],
            return_exceptions=True,
        )
        failed = [r for r in results if isinstance(r, BaseException)]
        if failed:
            # A partial sum would under-report tonnage — refuse instead.
            raise RuntimeError(
                f"STRUCTMIND CORE could not extract quantities "
                f"({len(failed)}/{len(batches)} parts failed). Last error: {failed[-1]}"
            )
        data = _combine_extractions([r[0] for r in results])
        return data, engine_label(results[0][1])
    finally:
        if scratch_dir:
            shutil.rmtree(scratch_dir, ignore_errors=True)
