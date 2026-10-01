"""
LLM service — google.genai (service account or API key).

PIPELINE OVERVIEW
─────────────────
  1. Pre-flight     Every oversized PDF is split losslessly into page-range
                    chunks, then all files are grouped (in drawing order) into
                    small batches of at most MAX_PAGES_PER_BATCH pages. Small
                    batches are what make the report DETAILED: a model that
                    reads 900 sheets in one call can only skim them, a model
                    that reads ~40 sheets can report every one of them.
  2. Fan-out        Batches are analysed CONCURRENTLY (MAX_PARALLEL_BATCHES)
                    and each batch's files are uploaded in parallel.
  3. Per-batch      Each batch walks the model chain on its own. Transient
     resilience     errors (429 / 5xx / timeouts) are retried with exponential
                    backoff on the SAME model first. A failure in batch 7 never
                    throws away batches 1-6 — the old code restarted the whole
                    job on the next model, which was the main source of lag.
  4. Continuation   If a response hits MAX_TOKENS, the model is asked to
                    continue exactly where it stopped and pieces are stitched.
  5. Consolidation  When there is more than one batch, a final pass fuses the
                    partial analyses into ONE report (one set of headings,
                    unified tables, reconciled totals). The result is checked
                    for silent data loss; if the merge dropped content it is
                    retried on the next model, and as a last resort the
                    partials are merged deterministically section-by-section.

MODELS
──────
  Default chain (override with GEMINI_MODEL_CHAIN="m1,m2,..."):
      gemini-2.5-pro          primary — most consistent on drawing take-offs
                              (low temperature, deterministic). Retired by
                              Google on GEMINI_25_PRO_SUNSET; after that date
                              it is dropped from the chain automatically.
      gemini-3.1-pro-preview  most capable 3.x reasoning model.
      gemini-3.5-flash        GA 3.x Flash.
      gemini-2.5-flash        last resort.
  Any model that returns 404 / NOT_FOUND is remembered as unavailable for the
  life of the process so later calls skip it instantly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Iterable

import google.genai as genai
from google.genai import types
from google.oauth2 import service_account
from google.auth.transport.requests import Request

from config import settings

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Model chain & per-model generation settings
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MODEL_CHAIN: list[str] = [
    "gemini-2.5-pro",
    "gemini-3.1-pro-preview",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
]

# Models Google has announced a shutdown date for. Past this date they are
# removed from the chain so we never waste a round-trip on a dead model.
MODEL_SUNSET: dict[str, date] = {
    "gemini-2.5-pro": date(2026, 10, 16),
}

ENGINE_LABELS: dict[str, str] = {
    "gemini-2.5-pro":         "STRUCTMIND CORE · PRO",
    "gemini-3.1-pro-preview": "STRUCTMIND CORE · PRO",
    "gemini-3.5-flash":       "STRUCTMIND CORE · FAST",
    "gemini-2.5-flash":       "STRUCTMIND CORE · FAST",
    "gemini-3.1-flash-lite":  "STRUCTMIND CORE · LITE",
}


def _build_model_chain() -> list[str]:
    raw = os.environ.get("GEMINI_MODEL_CHAIN", "").strip()
    chain = [m.strip() for m in raw.split(",") if m.strip()] if raw else list(DEFAULT_MODEL_CHAIN)
    today = date.today()
    active = [m for m in chain if not (m in MODEL_SUNSET and today >= MODEL_SUNSET[m])]
    return active or chain


MODEL_CHAIN: list[str] = _build_model_chain()

# Models that answered 404 / NOT_FOUND in this process — skipped from then on.
_UNAVAILABLE_MODELS: set[str] = set()


def _active_models() -> list[str]:
    models = [m for m in MODEL_CHAIN if m not in _UNAVAILABLE_MODELS]
    return models or list(MODEL_CHAIN)


def _is_gemini3(model_name: str) -> bool:
    return model_name.startswith("gemini-3")


def _media_resolution() -> types.MediaResolution | None:
    """High resolution is what lets the model read small dimension strings,
    member marks and weld symbols on drawings. Override with
    GEMINI_MEDIA_RESOLUTION=low|medium|high|default."""
    value = os.environ.get("GEMINI_MEDIA_RESOLUTION", "high").strip().lower()
    return {
        "low":    types.MediaResolution.MEDIA_RESOLUTION_LOW,
        "medium": types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
        "high":   types.MediaResolution.MEDIA_RESOLUTION_HIGH,
    }.get(value)


def _generation_config(
    model_name: str,
    system_prompt: str,
    *,
    max_output_tokens: int,
    temperature: float | None,
    with_media: bool,
    json_output: bool = False,
) -> types.GenerateContentConfig:
    """
    Build the request config for a model family.

    Gemini 2.5: low temperature (deterministic take-offs) + an explicit
        thinking budget so reasoning never eats the whole output budget.
    Gemini 3.x: thinking_level instead of thinking_budget (mixing them is a
        400), and temperature left at the 1.0 default per Google's guidance.
    """
    kwargs: dict = {
        "system_instruction": system_prompt,
        "max_output_tokens": max_output_tokens,
    }
    if _is_gemini3(model_name):
        level = types.ThinkingLevel.HIGH if "pro" in model_name else types.ThinkingLevel.MEDIUM
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=level)
    else:
        budget = 16_384 if "pro" in model_name else 8_192
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=budget)
        kwargs["temperature"] = 0.1 if temperature is None else temperature

    if json_output:
        kwargs["response_mime_type"] = "application/json"
    if with_media:
        res = _media_resolution()
        if res is not None:
            kwargs["media_resolution"] = res
    return types.GenerateContentConfig(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Tunable limits (all overridable via env)
# ─────────────────────────────────────────────────────────────────────────────

MAX_BATCH_MB         = float(os.environ.get("GEMINI_MAX_BATCH_MB", "45"))
MAX_FILES_PER_BATCH  = _env_int("GEMINI_MAX_FILES_PER_BATCH", 6)
# Pages analysed per request. Kept deliberately small so every sheet gets
# covered in detail; batches run in parallel so this does not cost wall time.
MAX_PAGES_PER_BATCH  = _env_int("GEMINI_MAX_PAGES_PER_BATCH", 40)
MAX_PDF_PAGES_PER_CHUNK = MAX_PAGES_PER_BATCH
MAX_PARALLEL_BATCHES = _env_int("GEMINI_MAX_PARALLEL_BATCHES", 4)

MAX_OUTPUT_TOKENS = 65_536
MAX_CONTINUATIONS = _env_int("GEMINI_MAX_CONTINUATIONS", 6)

# Retries on the SAME model for transient failures before falling back.
MAX_TRANSIENT_RETRIES = _env_int("GEMINI_MAX_RETRIES", 3)
REQUEST_TIMEOUT_S     = _env_int("GEMINI_REQUEST_TIMEOUT_S", 900)
UPLOAD_TIMEOUT_S      = _env_int("GEMINI_UPLOAD_TIMEOUT_S", 300)

# A consolidated report shorter than this fraction of the combined partials
# is treated as lossy (the model summarised instead of merging).
MIN_CONSOLIDATION_RATIO = float(os.environ.get("GEMINI_MIN_CONSOLIDATION_RATIO", "0.55"))

# Section groups for MASTER_INTAKE chunking (opt-in via chunk_sections=True).
SECTION_GROUPS: list[tuple[str, str]] = [
    ("PART-A · Sections 1–6",  "SECTIONS 1, 2, 3, 4, 5, AND 6 ONLY"),
    ("PART-B · Sections 7–12", "SECTIONS 7, 8, 9, 10, 11, AND 12 ONLY"),
]

# Thread pool for blocking SDK calls. Sized for parallel batches × uploads.
_EXECUTOR = ThreadPoolExecutor(max_workers=max(16, MAX_PARALLEL_BATCHES * 6))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def engine_label(internal_model: str) -> str:
    return ENGINE_LABELS.get(internal_model, "STRUCTMIND CORE")


def _get_credentials():
    """Return fresh service-account credentials, or None."""
    if os.environ.get("GEMINI_FORCE_API_KEY", "").lower() in ("1", "true", "yes"):
        logger.info("service_account_skipped reason=GEMINI_FORCE_API_KEY")
        return None
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_json:
        return None
    try:
        sa_info = json.loads(sa_json)
        credentials = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/generative-language"],
        )
        credentials.refresh(Request())
        logger.info("service_account_credentials=refreshed")
        return credentials
    except Exception as exc:
        logger.warning("service_account_auth_failed error=%s", exc)
        return None


def _get_client() -> genai.Client:
    """Return an authenticated Gemini client (created once per session)."""
    credentials = _get_credentials()
    if credentials:
        logger.info("gemini_client=service_account")
        return genai.Client(credentials=credentials)
    if settings.llm_key:
        logger.info("gemini_client=api_key")
        return genai.Client(api_key=settings.llm_key)
    raise RuntimeError("No Gemini credentials configured")


def _error_code(exc: Exception) -> int | None:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None


def _is_model_missing(exc: Exception) -> bool:
    msg = str(exc).upper()
    return _error_code(exc) == 404 or "NOT_FOUND" in msg or "IS NOT FOUND" in msg


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    code = _error_code(exc)
    if code in (408, 429, 500, 502, 503, 504):
        return True
    msg = str(exc).upper()
    return any(s in msg for s in (
        "RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE_EXCEEDED", "OVERLOADED",
        "INTERNAL", "TIMED OUT", "TIMEOUT", "CONNECTION RESET", "EMPTY RESPONSE",
    ))


async def _run_blocking(fn, *args, timeout: float | None = None):
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(_EXECUTOR, fn, *args)
    return await asyncio.wait_for(fut, timeout=timeout) if timeout else await fut


# ─────────────────────────────────────────────────────────────────────────────
# PDF page splitting
# ─────────────────────────────────────────────────────────────────────────────

def _pdf_page_count(file_path: str) -> int:
    """Return the page count of a PDF, or 0 if it can't be read."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(file_path).pages)
    except Exception as exc:
        logger.warning("pdf_page_count_failed path=%s error=%s", file_path, exc)
        return 0


def _split_pdf_if_needed(
    file_path: str, mime_type: str, scratch_dir: str,
) -> list[tuple[str, str]]:
    """Split a PDF larger than MAX_PDF_PAGES_PER_CHUNK pages into contiguous,
    lossless page-range chunks. Non-PDFs and small PDFs pass through."""
    if mime_type != "application/pdf":
        return [(file_path, mime_type)]

    page_count = _pdf_page_count(file_path)
    if page_count <= MAX_PDF_PAGES_PER_CHUNK:
        return [(file_path, mime_type)]

    try:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(file_path)
        base = os.path.splitext(os.path.basename(file_path))[0]
        chunks: list[tuple[str, str]] = []
        for start in range(0, page_count, MAX_PDF_PAGES_PER_CHUNK):
            end = min(start + MAX_PDF_PAGES_PER_CHUNK, page_count)
            writer = PdfWriter()
            for p in range(start, end):
                writer.add_page(reader.pages[p])
            chunk_path = os.path.join(scratch_dir, f"{base}_p{start + 1:05d}-{end:05d}.pdf")
            with open(chunk_path, "wb") as fh:
                writer.write(fh)
            chunks.append((chunk_path, mime_type))
        logger.info(
            "pdf_split path=%s total_pages=%d chunks=%d chunk_size=%d",
            file_path, page_count, len(chunks), MAX_PDF_PAGES_PER_CHUNK,
        )
        return chunks
    except Exception as exc:
        logger.warning(
            "pdf_split_failed path=%s pages=%d error=%s — sending unsplit",
            file_path, page_count, exc,
        )
        return [(file_path, mime_type)]


# ─────────────────────────────────────────────────────────────────────────────
# File batching
# ─────────────────────────────────────────────────────────────────────────────

def _build_batches(
    file_paths: list[tuple[str, str]],
) -> list[list[tuple[str, str]]]:
    """
    Group files into batches that each stay under MAX_BATCH_MB,
    MAX_FILES_PER_BATCH and MAX_PAGES_PER_BATCH.

    Files are kept in their original (drawing-set) order so each batch covers
    a contiguous run of sheets and split-PDF chunks stay in sequence — this
    keeps sheet numbering coherent in the final report.
    """
    batches: list[list[tuple[str, str]]] = []
    batch_sizes: list[float] = []
    batch_pages: list[int] = []

    for fp, mime in file_paths:
        if not os.path.exists(fp):
            logger.warning("file_not_found path=%s", fp)
            continue
        size_mb = os.path.getsize(fp) / (1_024 * 1_024)
        pages = _pdf_page_count(fp) if mime == "application/pdf" else 1

        if batches and (
            len(batches[-1]) < MAX_FILES_PER_BATCH
            and batch_sizes[-1] + size_mb <= MAX_BATCH_MB
            and batch_pages[-1] + pages <= MAX_PAGES_PER_BATCH
        ):
            batches[-1].append((fp, mime))
            batch_sizes[-1] += size_mb
            batch_pages[-1] += pages
        else:
            batches.append([(fp, mime)])
            batch_sizes.append(size_mb)
            batch_pages.append(pages)

    for i, (batch, sz, pg) in enumerate(zip(batches, batch_sizes, batch_pages)):
        logger.info(
            "file_batch batch=%d/%d files=%d size_mb=%.1f pages=%d",
            i + 1, len(batches), len(batch), sz, pg,
        )
    return batches or [[]]


def prepare_file_batches(
    file_paths: list[tuple[str, str]],
) -> tuple[list[list[tuple[str, str]]], str | None]:
    """
    Split oversized PDFs into page-safe chunks, then group everything into
    upload-safe batches.

    Returns (batches, scratch_dir). If scratch_dir is not None the caller
    MUST shutil.rmtree it (ignore_errors=True) when done.
    """
    if not file_paths:
        return [[]], None

    scratch_dir = tempfile.mkdtemp(prefix="structmind_split_")
    expanded: list[tuple[str, str]] = []
    for fp, mime in file_paths:
        expanded.extend(_split_pdf_if_needed(fp, mime, scratch_dir))

    return _build_batches(expanded), scratch_dir


# ─────────────────────────────────────────────────────────────────────────────
# File upload
# ─────────────────────────────────────────────────────────────────────────────

def _upload_one_sync(client: genai.Client, file_path: str, mime_type: str):
    """Upload a single file and poll until ACTIVE. Returns the file or None."""
    if not os.path.exists(file_path):
        logger.warning("upload_skip_missing path=%s", file_path)
        return None
    size_mb = os.path.getsize(file_path) / (1_024 * 1_024)
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        try:
            with open(file_path, "rb") as fh:
                uploaded_file = client.files.upload(
                    file=fh,
                    config=types.UploadFileConfig(
                        mime_type=mime_type,
                        display_name=os.path.basename(file_path)[:120],
                    ),
                )
            deadline = time.monotonic() + UPLOAD_TIMEOUT_S
            delay = 0.5
            while time.monotonic() < deadline:
                info = client.files.get(name=uploaded_file.name)
                state = info.state.name
                if state == "ACTIVE":
                    logger.info("upload_ready name=%s size_mb=%.1f", uploaded_file.name, size_mb)
                    return info
                if state == "FAILED":
                    raise RuntimeError(f"Gemini rejected file {os.path.basename(file_path)}")
                time.sleep(delay)
                delay = min(delay * 1.5, 4.0)
            raise TimeoutError(f"upload processing timed out for {os.path.basename(file_path)}")
        except Exception as exc:  # noqa: BLE001
            if attempt < MAX_TRANSIENT_RETRIES and _is_transient(exc):
                wait = 2 ** attempt + random.random()
                logger.warning("upload_retry path=%s attempt=%d wait=%.1fs error=%s",
                               file_path, attempt + 1, wait, exc)
                time.sleep(wait)
                continue
            logger.error("upload_error path=%s error=%s", file_path, exc)
            return None
    return None


async def _upload_files(
    client: genai.Client,
    file_paths: list[tuple[str, str]],
) -> list:
    """Upload all files of a batch concurrently, preserving order.

    Raises if any file failed to upload — analysing a batch with missing
    sheets would silently produce an incomplete report."""
    results = await asyncio.gather(*[
        _run_blocking(_upload_one_sync, client, fp, mime) for fp, mime in file_paths
    ])
    uploaded = [r for r in results if r is not None]
    if len(uploaded) != len(file_paths):
        _cleanup_files(client, uploaded)
        missing = [os.path.basename(fp) for (fp, _), r in zip(file_paths, results) if r is None]
        raise RuntimeError(f"File upload failed for: {', '.join(missing)}")
    return uploaded


def _cleanup_files(client: genai.Client, uploaded_files: list) -> None:
    """Delete uploaded files from Gemini Files API."""
    for f in uploaded_files:
        try:
            client.files.delete(name=f.name)
            logger.info("file_deleted name=%s", f.name)
        except Exception as exc:
            logger.warning("file_delete_error name=%s error=%s", f.name, exc)


async def _cleanup_files_async(client: genai.Client, uploaded_files: list) -> None:
    if uploaded_files:
        try:
            await _run_blocking(_cleanup_files, client, uploaded_files)
        except Exception as exc:  # noqa: BLE001
            logger.warning("file_cleanup_failed error=%s", exc)


def _file_parts(uploaded_files: list) -> list[types.Part]:
    return [
        types.Part(file_data=types.FileData(file_uri=f.uri, mime_type=f.mime_type))
        for f in uploaded_files
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Core generation
# ─────────────────────────────────────────────────────────────────────────────

def _is_truncated(response) -> bool:
    """True if Gemini stopped because it hit the output token limit."""
    try:
        reason = response.candidates[0].finish_reason
        return str(reason) in ("FinishReason.MAX_TOKENS", "MAX_TOKENS", "2")
    except Exception:
        return False


def _generate(
    client: genai.Client,
    model_name: str,
    contents: list,
    config: types.GenerateContentConfig,
) -> tuple[str, bool]:
    """One blocking generate_content call → (text, was_truncated)."""
    response = client.models.generate_content(
        model=model_name, contents=contents, config=config,
    )
    # Not stripped: continuation pieces must join exactly at the cut point.
    text = response.text or ""
    if not text.strip():
        reason = None
        try:
            reason = response.candidates[0].finish_reason
        except Exception:
            pass
        raise RuntimeError(f"Empty response from model (finish_reason={reason})")
    return text, _is_truncated(response)


async def generate_once(
    *,
    client: genai.Client,
    model_name: str,
    system_prompt: str,
    contents: list,
    max_output_tokens: int = MAX_OUTPUT_TOKENS,
    temperature: float | None = None,
    with_media: bool = True,
    json_output: bool = False,
    label: str = "",
) -> tuple[str, bool]:
    """
    Run one generation with transient-error retries (exponential backoff) on
    the same model. Non-transient errors propagate so the caller can fall
    back to the next model. Never blocks the event loop.
    """
    config = _generation_config(
        model_name, system_prompt,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        with_media=with_media,
        json_output=json_output,
    )
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        try:
            return await _run_blocking(
                _generate, client, model_name, contents, config,
                timeout=REQUEST_TIMEOUT_S,
            )
        except Exception as exc:  # noqa: BLE001
            if _is_model_missing(exc):
                _UNAVAILABLE_MODELS.add(model_name)
                logger.warning("model_unavailable model=%s — skipping from now on", model_name)
                raise
            if attempt < MAX_TRANSIENT_RETRIES and _is_transient(exc):
                wait = min(60.0, 2 ** (attempt + 1)) + random.random() * 2
                logger.warning(
                    "generate_retry model=%s label=%s attempt=%d wait=%.1fs error=%s",
                    model_name, label, attempt + 1, wait, exc,
                )
                await asyncio.sleep(wait)
                continue
            raise
    raise RuntimeError("unreachable")


_CONTINUATION_INSTRUCTION = (
    "Your previous response was cut off at the output limit. Continue EXACTLY "
    "from where you stopped — do NOT restart, do NOT repeat any heading, row "
    "or sentence already written. If you stopped inside a table, continue the "
    "table rows directly (no new header row). Complete all remaining sections "
    "in full detail."
)


async def _generate_with_continuation(
    *,
    client: genai.Client,
    model_name: str,
    system_prompt: str,
    initial_parts: list[types.Part],
    session_id: str,
    label: str = "",
    with_media: bool = True,
) -> str:
    """
    Generate; if the model hits MAX_TOKENS, keep asking it to continue (up to
    MAX_CONTINUATIONS times) with the FULL conversation so far, so it always
    knows exactly what has already been written. Returns stitched text.
    """
    history: list[types.Content] = [types.Content(role="user", parts=initial_parts)]
    accumulated: list[str] = []

    for attempt in range(MAX_CONTINUATIONS + 1):
        logger.info("generate attempt=%d model=%s session=%s label=%s",
                    attempt, model_name, session_id, label)
        text, truncated = await generate_once(
            client=client, model_name=model_name, system_prompt=system_prompt,
            contents=history, with_media=with_media, label=label,
        )
        accumulated.append(text)
        if not truncated:
            break
        if attempt == MAX_CONTINUATIONS:
            logger.warning("max_continuations_reached model=%s session=%s label=%s",
                           model_name, session_id, label)
            break
        history = history + [
            types.Content(role="model", parts=[types.Part(text=text)]),
            types.Content(role="user", parts=[types.Part(text=_CONTINUATION_INSTRUCTION)]),
        ]

    return _stitch(accumulated)


_BLOCK_START_RE = re.compile(r"^\s*(#|\||[-*+]\s|\d+[.)]\s|>)")


def _stitch(pieces: list[str]) -> str:
    """Join continuation pieces. Pieces are raw (unstripped), so a cut
    mid-word or mid-sentence joins seamlessly; a piece that starts a new
    markdown block (heading, table row, list item) gets its own line."""
    out = pieces[0] if pieces else ""
    for piece in pieces[1:]:
        if out and not out.endswith("\n") and _BLOCK_START_RE.match(piece):
            out += "\n"
        out += piece
    return out.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Per-batch runner (with its own model fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _batch_user_text(user_text: str, batch_num: int, total_batches: int, files: list[tuple[str, str]]) -> str:
    if total_batches <= 1:
        return (
            f"{user_text}\n\n"
            "Analyse EVERY sheet, page, view, detail, schedule and note in the "
            "attached files. Report every member, connection, dimension and "
            "finding individually — do not summarise, sample or skip any drawing."
        )
    names = ", ".join(os.path.basename(fp) for fp, _ in files)
    return (
        f"{user_text}\n\n"
        f"CONTEXT: The project drawing set is large and is being reviewed in "
        f"{total_batches} consecutive parts. You are reviewing part {batch_num} "
        f"of {total_batches} (files: {names}). A separate step will merge all "
        f"parts into one final report, so:\n"
        "- Analyse EVERY sheet in these files completely and in full detail — "
        "every member, mark, size, length, quantity, connection, dimension, "
        "note and issue. Never summarise, sample or skip a sheet.\n"
        "- Always cite the drawing/sheet number for every row and finding so "
        "the merge can de-duplicate correctly.\n"
        "- Follow the mode's full section structure and table formats exactly.\n"
        "- Give subtotals for this part only; do not guess the rest of the project.\n"
        "- Do not mention parts, batches or splitting in your output."
    )


async def _run_single_batch(
    *,
    client: genai.Client,
    system_prompt: str,
    user_text: str,
    batch_files: list[tuple[str, str]],
    batch_num: int,
    total_batches: int,
    session_id: str,
    chunk_sections: bool = False,
) -> tuple[str, str]:
    """
    Analyse one batch. Files are uploaded ONCE and reused across every model
    in the fallback chain. Returns (markdown, model_used).
    """
    uploaded_files: list = await _upload_files(client, batch_files) if batch_files else []
    file_parts = _file_parts(uploaded_files)
    base_text = _batch_user_text(user_text, batch_num, total_batches, batch_files)
    last_err: Exception | None = None

    try:
        for model_name in _active_models():
            try:
                if chunk_sections:
                    async def run_group(group_label: str, spec: str) -> str:
                        text = (
                            base_text
                            + f"\n\nCRITICAL INSTRUCTION: Output {spec}. Do NOT output "
                            "any other sections. Begin immediately with the first section in this group."
                        )
                        return await _generate_with_continuation(
                            client=client, model_name=model_name, system_prompt=system_prompt,
                            initial_parts=[types.Part(text=text)] + file_parts,
                            session_id=session_id, label=f"{group_label} batch={batch_num}",
                        )
                    parts = await asyncio.gather(*[run_group(g, s) for g, s in SECTION_GROUPS])
                    output = "\n\n".join(parts)
                else:
                    output = await _generate_with_continuation(
                        client=client, model_name=model_name, system_prompt=system_prompt,
                        initial_parts=[types.Part(text=base_text)] + file_parts,
                        session_id=session_id, label=f"batch={batch_num}/{total_batches}",
                    )
                logger.info("batch_complete batch=%d/%d model=%s session=%s chars=%d",
                            batch_num, total_batches, model_name, session_id, len(output))
                return output, model_name
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("batch_model_failed batch=%d/%d model=%s session=%s error=%s",
                               batch_num, total_batches, model_name, session_id, exc)
                continue
        raise RuntimeError(f"batch {batch_num}/{total_batches} failed on every model: {last_err}")
    finally:
        await _cleanup_files_async(client, uploaded_files)


# ─────────────────────────────────────────────────────────────────────────────
# Consolidation
# ─────────────────────────────────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*\S)\s*$", re.MULTILINE)


def _normalise_heading(h: str) -> str:
    h = re.sub(r"[*_`]", "", h).strip().lower()
    h = re.sub(r"\(.*?(part|batch|sheets?).*?\)", "", h)
    return re.sub(r"\s+", " ", h).strip()


def _split_sections(outputs: list[str]):
    """Group partial reports by their shared top-level section headings.

    Returns (level, preamble, order, titles, bodies) or None when the partials
    do not share a heading structure."""
    outputs = [o.strip() for o in outputs if o and o.strip()]
    def section_level(o: str) -> int | None:
        # Shallowest heading level used more than once; a single "# Title"
        # heading is the report title, not a section.
        levels = [len(m.group(1)) for m in _HEADING_RE.finditer(o)]
        for lv in sorted(set(levels)):
            if levels.count(lv) >= 2:
                return lv
        return min(levels) if levels else None

    per_partial = [section_level(o) for o in outputs]
    if not outputs or any(lv is None for lv in per_partial):
        return None
    level = max(per_partial)
    split_re = re.compile(rf"^#{{{level}}}\s+(.*\S)\s*$", re.MULTILINE)

    order: list[str] = []
    titles: dict[str, str] = {}
    bodies: dict[str, list[str]] = {}
    preamble: list[str] = []
    for out in outputs:
        matches = list(split_re.finditer(out))
        head = out[: matches[0].start()].strip() if matches else out
        if head and head not in preamble:
            preamble.append(head)
        for i, m in enumerate(matches):
            key = _normalise_heading(m.group(1))
            end = matches[i + 1].start() if i + 1 < len(matches) else len(out)
            body = out[m.end():end].strip()
            if key not in bodies:
                order.append(key)
                titles[key] = m.group(1)
                bodies[key] = []
            if body:
                bodies[key].append(body)
    return level, preamble, order, titles, bodies


def _table_header_key(line: str) -> str:
    return re.sub(r"[\s*_`]", "", line).lower()


def _merge_section_bodies(bodies: list[str]) -> str:
    """Deterministically merge one section's content from several partials:
    tables with the same header become ONE table (all rows, exact duplicate
    rows removed); repeated identical text blocks appear once."""
    if len(bodies) <= 1:
        return bodies[0] if bodies else ""
    blocks: list[list] = []          # ["text", str] | ["table", header, sep, rows]
    table_at: dict[str, int] = {}
    seen_text: set[str] = set()
    for body in bodies:
        lines = body.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            if (line.strip().startswith("|") and i + 1 < len(lines)
                    and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1])):
                header, sep = line.strip(), lines[i + 1].strip()
                rows = []
                i += 2
                while i < len(lines) and lines[i].strip().startswith("|"):
                    rows.append(lines[i].strip())
                    i += 1
                key = _table_header_key(header)
                if key in table_at:
                    target = blocks[table_at[key]][3]
                    target.extend(r for r in rows if r not in target)
                else:
                    table_at[key] = len(blocks)
                    blocks.append(["table", header, sep, rows])
                continue
            text = []
            while i < len(lines) and not (
                lines[i].strip().startswith("|") and i + 1 < len(lines)
                and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1])
            ):
                text.append(lines[i])
                i += 1
            chunk = "\n".join(text).strip()
            if chunk and chunk not in seen_text:
                seen_text.add(chunk)
                blocks.append(["text", chunk])
    out = []
    for blk in blocks:
        if blk[0] == "text":
            out.append(blk[1])
        else:
            out.append("\n".join([blk[1], blk[2], *blk[3]]))
    return "\n\n".join(out)


def _merge_batch_outputs(outputs: list[str], total_batches: int = 0) -> str:
    """Deterministic, lossless fallback merge: one heading per section, and
    tables with matching headers combined into a single table."""
    outputs = [o.strip() for o in outputs if o and o.strip()]
    if len(outputs) <= 1:
        return outputs[0] if outputs else ""
    split = _split_sections(outputs)
    if split is None:
        return "\n\n---\n\n".join(outputs)
    level, preamble, order, titles, bodies = split
    parts = list(preamble[:1])
    for key in order:
        parts.append(f"{'#' * level} {titles[key]}\n\n" + _merge_section_bodies(bodies[key]))
    return "\n\n".join(parts)


_SECTION_MERGE_INSTRUCTION = (
    "Below are {n} versions of the report section \"{title}\". Each version was "
    "written from a different, consecutive part of the SAME project's drawing set. "
    "Merge them into the ONE final version of this section.\n\n"
    "STRICT REQUIREMENTS:\n"
    "1. Every table becomes ONE unified table containing EVERY row from every "
    "version, with all detail kept (marks, sizes, lengths, quantities, weights, "
    "sheet references, notes). Remove only exact duplicates of the same item on "
    "the same sheet.\n"
    "2. Re-compute every total, subtotal, count, tonnage and cost from the merged "
    "rows so the figures cover the whole project.\n"
    "3. Keep every distinct finding, issue, RFI, risk and recommendation. This is a "
    "MERGE, not a summary — the result must be at least as detailed as all "
    "versions combined, except for genuine duplicates.\n"
    "4. Narrative text must describe the whole project in one voice.\n"
    "5. Keep the section's required table formats and sub-headings.\n"
    "6. Never mention versions, parts, batches or splitting.\n"
    "7. Output ONLY the section body — do NOT repeat the heading \"{title}\".\n\n"
    "{body}"
)


async def _merge_one_section(
    *,
    client: genai.Client,
    system_prompt: str,
    title: str,
    bodies: list[str],
    models: list[str],
    session_id: str,
) -> tuple[str, bool]:
    """Merge one section with the model; reject lossy results. Returns
    (body, used_model). Falls back to the deterministic section merge."""
    if len(bodies) <= 1:
        return (bodies[0] if bodies else ""), False
    total = sum(len(b) for b in bodies)
    has_table = any(re.search(r"^\s*\|.*\|\s*$", b, re.MULTILINE) for b in bodies)
    # Tables must keep their rows; prose legitimately shrinks when de-duplicated.
    threshold = MIN_CONSOLIDATION_RATIO if has_table else 0.3
    joined = "\n\n".join(
        f"<<<VERSION {i} OF {len(bodies)}>>>\n{b}\n<<<END VERSION {i}>>>"
        for i, b in enumerate(bodies, 1)
    )
    instruction = _SECTION_MERGE_INSTRUCTION.format(n=len(bodies), title=title, body=joined)
    for model_name in models:
        if model_name in _UNAVAILABLE_MODELS:
            continue
        try:
            merged = await _generate_with_continuation(
                client=client, model_name=model_name, system_prompt=system_prompt,
                initial_parts=[types.Part(text=instruction)], session_id=session_id,
                label=f"merge section={title[:40]}", with_media=False,
            )
            merged = _HEADING_RE.sub(
                lambda m: "" if _normalise_heading(m.group(2)) == _normalise_heading(title) else m.group(0),
                merged, count=1,
            ).strip()
            ratio = len(merged) / max(1, total)
            if ratio >= threshold:
                return merged, True
            logger.warning("section_merge_lossy section=%s model=%s ratio=%.2f",
                           title[:40], model_name, ratio)
        except Exception as exc:  # noqa: BLE001
            logger.warning("section_merge_failed section=%s model=%s error=%s",
                           title[:40], model_name, exc)
    logger.warning("section_merge_fallback=deterministic section=%s", title[:40])
    return _merge_section_bodies(bodies), False


async def _consolidate_sectionwise(
    *,
    client: genai.Client,
    system_prompt: str,
    outputs: list[str],
    session_id: str,
    preferred_model: str,
) -> str | None:
    """Merge partial reports section-by-section, in parallel. Each call only
    rewrites one section, so the model keeps every row instead of
    summarising the whole report. Returns None if partials share no
    section structure."""
    split = _split_sections(outputs)
    if split is None:
        return None
    level, preamble, order, titles, bodies = split
    if len(order) < 2:
        return None
    models = [preferred_model] + [m for m in _active_models() if m != preferred_model][:1]
    sem = asyncio.Semaphore(max(2, MAX_PARALLEL_BATCHES))

    async def run(key: str) -> tuple[str, bool]:
        async with sem:
            return await _merge_one_section(
                client=client, system_prompt=system_prompt, title=titles[key],
                bodies=bodies[key], models=models, session_id=session_id,
            )

    results = await asyncio.gather(*[run(k) for k in order])
    merged_by_model = sum(1 for _, used in results if used)
    logger.info("consolidation_sectionwise session=%s sections=%d model_merged=%d",
                session_id, len(order), merged_by_model)
    parts = list(preamble[:1])
    for key, (body, _) in zip(order, results):
        parts.append(f"{'#' * level} {titles[key]}\n\n{body}")
    return "\n\n".join(parts)


_CONSOLIDATION_INSTRUCTION = (
    "Below are {n} PARTIAL analyses. Each one covers a different, consecutive "
    "part of the SAME project's drawing set (the set was split only because of "
    "upload limits). Merge them into ONE single, complete, professional report.\n\n"
    "STRICT REQUIREMENTS:\n"
    "1. One set of section headings in the exact order and format the mode "
    "requires — never repeat a section per partial.\n"
    "2. Every table, register, schedule and list becomes ONE unified table "
    "containing EVERY row from every partial. Keep every row's detail "
    "(marks, sizes, lengths, quantities, weights, sheet references, notes). "
    "Remove only exact duplicates of the same item on the same sheet.\n"
    "3. Re-compute every total, subtotal, count, tonnage and cost from the "
    "merged rows to give single project-level figures. Show the arithmetic "
    "is consistent (row sums = totals).\n"
    "4. Preserve every distinct drawing, member, finding, RFI, issue and "
    "recommendation — this is a MERGE, not a summary. The final report must "
    "be at least as detailed as all partials combined.\n"
    "5. Executive summary / overview sections must describe the WHOLE project.\n"
    "6. Never mention 'batch', 'part', 'partial', 'subset' or that the work was split.\n"
    "7. If the output is long, keep writing — you will be asked to continue.\n"
    "Output ONLY the final merged report.\n\n{body}"
)


async def _consolidate_outputs(
    *,
    client: genai.Client,
    model_name: str,
    system_prompt: str,
    outputs: list[str],
    session_id: str,
) -> str:
    """Fuse per-batch outputs into ONE coherent report via a model pass."""
    clean = [o.strip() for o in outputs if o and o.strip()]
    joined = "\n\n".join(
        f"<<<PARTIAL ANALYSIS {i} OF {len(clean)}>>>\n{out}\n<<<END PARTIAL {i}>>>"
        for i, out in enumerate(clean, 1)
    )
    instruction = _CONSOLIDATION_INSTRUCTION.format(n=len(clean), body=joined)
    return await _generate_with_continuation(
        client=client,
        model_name=model_name,
        system_prompt=system_prompt,
        initial_parts=[types.Part(text=instruction)],
        session_id=session_id,
        label="consolidation",
        with_media=False,
    )


async def _consolidate_with_fallback(
    *,
    client: genai.Client,
    system_prompt: str,
    outputs: list[str],
    session_id: str,
    preferred_model: str,
) -> tuple[str, str | None]:
    """Merge partial reports into one. Section-by-section merging is used
    whenever the partials share a section structure; otherwise a whole-report
    merge (lossy results rejected), then the deterministic merge."""
    try:
        sectionwise = await _consolidate_sectionwise(
            client=client, system_prompt=system_prompt, outputs=outputs,
            session_id=session_id, preferred_model=preferred_model,
        )
        if sectionwise:
            return sectionwise, preferred_model
    except Exception as exc:  # noqa: BLE001
        logger.warning("consolidation_sectionwise_failed session=%s error=%s", session_id, exc)

    total_chars = sum(len(o) for o in outputs if o)
    models = [preferred_model] + [m for m in _active_models() if m != preferred_model]
    for model_name in models:
        if model_name in _UNAVAILABLE_MODELS:
            continue
        try:
            merged = await _consolidate_outputs(
                client=client, model_name=model_name, system_prompt=system_prompt,
                outputs=outputs, session_id=session_id,
            )
            ratio = len(merged) / max(1, total_chars)
            if ratio < MIN_CONSOLIDATION_RATIO:
                logger.warning(
                    "consolidation_lossy model=%s session=%s ratio=%.2f — retrying",
                    model_name, session_id, ratio,
                )
                continue
            logger.info("consolidation_complete model=%s session=%s ratio=%.2f",
                        model_name, session_id, ratio)
            return merged, model_name
        except Exception as exc:  # noqa: BLE001
            logger.warning("consolidation_failed model=%s session=%s error=%s",
                           model_name, session_id, exc)
    logger.warning("consolidation_fallback=deterministic session=%s", session_id)
    return _merge_batch_outputs(outputs), None


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

async def run_analysis(
    *,
    session_id: str,
    system_prompt: str,
    user_text: str,
    file_paths: Iterable[tuple[str, str]] = (),
    chunk_sections: bool = False,
) -> tuple[str, str]:
    """
    Execute a full drawing analysis and return ONE consolidated report.

    Returns (output_markdown, engine_display_label).
    """
    file_paths_list = list(file_paths)
    started = time.monotonic()
    batches, scratch_dir = await _run_blocking(prepare_file_batches, file_paths_list)
    total = len(batches)

    logger.info(
        "run_analysis_start session=%s total_files=%d batches=%d parallel=%d "
        "chunk_sections=%s model_chain=%s",
        session_id, len(file_paths_list), total, MAX_PARALLEL_BATCHES,
        chunk_sections, _active_models(),
    )

    try:
        client = _get_client()
        sem = asyncio.Semaphore(max(1, MAX_PARALLEL_BATCHES))

        async def run(i: int, batch: list[tuple[str, str]]) -> tuple[str, str]:
            async with sem:
                return await _run_single_batch(
                    client=client, system_prompt=system_prompt, user_text=user_text,
                    batch_files=batch, batch_num=i, total_batches=total,
                    session_id=session_id, chunk_sections=chunk_sections,
                )

        results = await asyncio.gather(
            *[run(i, b) for i, b in enumerate(batches, 1)], return_exceptions=True,
        )
        failures = [(i, r) for i, r in enumerate(results, 1) if isinstance(r, BaseException)]
        if failures:
            # Never deliver a report that silently omits drawings.
            detail = "; ".join(f"part {i}: {r}" for i, r in failures[:3])
            raise RuntimeError(
                f"STRUCTMIND CORE could not analyse {len(failures)} of {total} "
                f"drawing part(s) for session={session_id}. {detail}"
            )

        outputs = [r[0] for r in results]
        models_used = [r[1] for r in results]
        # Report the weakest tier that contributed, so the label is honest.
        chain = _active_models() + [m for m in MODEL_CHAIN if m not in _active_models()]
        primary_model = max(models_used, key=lambda m: chain.index(m) if m in chain else 99)

        if total == 1:
            final_output = outputs[0]
        else:
            best = min(models_used, key=lambda m: chain.index(m) if m in chain else 99)
            final_output, _ = await _consolidate_with_fallback(
                client=client, system_prompt=system_prompt, outputs=outputs,
                session_id=session_id, preferred_model=best,
            )

        logger.info(
            "run_analysis_complete session=%s batches=%d models=%s elapsed=%.1fs chars=%d",
            session_id, total, sorted(set(models_used)),
            time.monotonic() - started, len(final_output),
        )
        return final_output, engine_label(primary_model)
    finally:
        if scratch_dir:
            shutil.rmtree(scratch_dir, ignore_errors=True)
