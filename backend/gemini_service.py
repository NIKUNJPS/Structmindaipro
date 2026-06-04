"""LLM service using google.genai with service account authentication."""
from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

import google.genai as genai
from google.genai import types
from google.oauth2 import service_account
from google.auth.transport.requests import Request

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model chain — ordered by preference (best → fastest fallback)
# ---------------------------------------------------------------------------
MODEL_CHAIN: list[str] = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]

ENGINE_LABELS: dict[str, str] = {
    "gemini-2.5-pro":   "STRUCTMIND CORE · PRO",
    "gemini-2.5-flash": "STRUCTMIND CORE · FAST",
    "gemini-2.0-flash": "STRUCTMIND CORE · LITE",
}

# ---------------------------------------------------------------------------
# Real Gemini Files API limits (as of 2025)
# ---------------------------------------------------------------------------
# • Max size per individual file   : 2 GB
# • Max project storage at once    : 20 GB
# • File TTL                       : 48 hours
# • Context window (both models)   : 1,000,000 tokens
# • Practical token budget for files (leaving room for prompt + output):
#     ~900,000 tokens ≈ ~3,000 PDF pages ≈ varies by file density
#
# We guard on estimated TOKEN budget — the real bottleneck — not raw MB/count.
# The MB/count caps below are wide safety nets only.
MAX_FILES_PER_REQUEST    = 50       # no hard API limit; context window is the cap
MAX_FILE_SIZE_MB         = 1900     # per-file (real limit = 2 GB = 2048 MB)
MAX_TOTAL_MB_PER_REQUEST = 2000     # ~50 × 40 MB avg; well within 20 GB storage
WARN_TOKEN_THRESHOLD     = 800_000  # warn in logs if estimated tokens exceed this

# Upload tuning
UPLOAD_POLL_INTERVAL_S = 3
UPLOAD_POLL_TIMEOUT_S  = 300        # large files can take time to process
UPLOAD_CONCURRENCY     = 5          # parallel uploads for faster batches

# Conservative token estimators for PDF/drawing files
TOKENS_PER_PDF_PAGE = 300           # ~250-350 tokens per dense page
BYTES_PER_PDF_PAGE  = 100_000       # ~100 KB per page for typical drawings


def engine_label(internal_model: str) -> str:
    return ENGINE_LABELS.get(internal_model, "STRUCTMIND CORE")


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def _estimate_tokens_for_files(file_paths: list[tuple[str, str]]) -> int:
    """
    Rough token estimate for a list of files.
    Uses file size / bytes-per-page × tokens-per-page for PDFs.
    Other types use a flat bytes-per-token ratio.
    """
    total = 0
    for file_path, mime_type in file_paths:
        if not os.path.exists(file_path):
            continue
        size_bytes = os.path.getsize(file_path)
        if "pdf" in mime_type:
            estimated_pages = max(1, size_bytes // BYTES_PER_PDF_PAGE)
            total += estimated_pages * TOKENS_PER_PDF_PAGE
        else:
            # Generic fallback: ~4 bytes per token
            total += size_bytes // 4
    return total


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_credentials():
    """Build and refresh service-account credentials (returns None on failure)."""
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
        logger.info("Service account credentials refreshed successfully")
        return credentials
    except Exception as exc:
        logger.warning("Service account auth failed: %s", exc)
        return None


def _get_client() -> genai.Client:
    """Return an authenticated Gemini client (service-account > API key)."""
    credentials = _get_credentials()
    if credentials:
        logger.info("Gemini client created with service account")
        return genai.Client(credentials=credentials)
    if settings.llm_key:
        logger.info("Gemini client created with API key")
        return genai.Client(api_key=settings.llm_key)
    raise RuntimeError("No Gemini credentials configured")


# ---------------------------------------------------------------------------
# File upload helpers
# ---------------------------------------------------------------------------

def _upload_single_file(
    client: genai.Client,
    file_path: str,
    mime_type: str,
) -> types.File | None:
    """
    Upload one file to the Gemini Files API and poll until ACTIVE.
    Returns the File object on success, None on any failure.
    """
    if not os.path.exists(file_path):
        logger.warning("File not found, skipping: %s", file_path)
        return None

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

    # Per-file size guard
    if file_size_mb > MAX_FILE_SIZE_MB:
        logger.error(
            "File %s is %.1f MB — exceeds per-file cap of %d MB, skipping",
            file_path, file_size_mb, MAX_FILE_SIZE_MB,
        )
        return None

    logger.info("Uploading %.1f MB to Gemini Files API: %s", file_size_mb, file_path)

    try:
        with open(file_path, "rb") as fh:
            uploaded_file = client.files.upload(
                file=fh,
                config=types.UploadFileConfig(mime_type=mime_type),
            )

        # Poll until ACTIVE
        waited = 0
        while waited < UPLOAD_POLL_TIMEOUT_S:
            file_info = client.files.get(name=uploaded_file.name)
            state = file_info.state.name
            if state == "ACTIVE":
                logger.info("File ready: %s (%.1f MB)", file_info.name, file_size_mb)
                return file_info
            if state == "FAILED":
                logger.error("Gemini file processing failed: %s", uploaded_file.name)
                return None
            logger.debug("File %s state=%s — waiting…", uploaded_file.name, state)
            time.sleep(UPLOAD_POLL_INTERVAL_S)
            waited += UPLOAD_POLL_INTERVAL_S

        logger.warning("File %s timed out waiting for ACTIVE", uploaded_file.name)
        return None

    except Exception as exc:
        logger.warning("Upload failed for %s: %s", file_path, exc)
        return None


def _upload_files(
    client: genai.Client,
    file_paths: list[tuple[str, str]],
) -> list[types.File]:
    """
    Upload files concurrently, enforcing count/size caps and logging token estimates.
    Individual failures are skipped — the batch continues.
    """
    if not file_paths:
        return []

    # ── Pre-flight checks ────────────────────────────────────────────────────
    total_mb = sum(
        os.path.getsize(p) / (1024 * 1024)
        for p, _ in file_paths
        if os.path.exists(p)
    )
    estimated_tokens = _estimate_tokens_for_files(file_paths)

    logger.info(
        "Pre-flight: %d file(s) · %.1f MB total · ~%s estimated tokens",
        len(file_paths),
        total_mb,
        f"{estimated_tokens:,}",
    )

    if len(file_paths) > MAX_FILES_PER_REQUEST:
        logger.warning(
            "%d files requested — capping at %d (context-window safety)",
            len(file_paths), MAX_FILES_PER_REQUEST,
        )
        file_paths = file_paths[:MAX_FILES_PER_REQUEST]

    if total_mb > MAX_TOTAL_MB_PER_REQUEST:
        logger.warning(
            "Total size %.1f MB exceeds cap of %d MB — some files may be skipped",
            total_mb, MAX_TOTAL_MB_PER_REQUEST,
        )

    if estimated_tokens > WARN_TOKEN_THRESHOLD:
        logger.warning(
            "Estimated token usage ~%s exceeds warning threshold %s — "
            "response quality may degrade near context limit",
            f"{estimated_tokens:,}", f"{WARN_TOKEN_THRESHOLD:,}",
        )

    # ── Concurrent uploads ───────────────────────────────────────────────────
    uploaded: list[types.File] = []
    running_mb = 0.0

    with ThreadPoolExecutor(max_workers=UPLOAD_CONCURRENCY) as pool:
        future_to_path = {
            pool.submit(_upload_single_file, client, fp, mt): (fp, mt)
            for fp, mt in file_paths
        }
        for future in as_completed(future_to_path):
            fp, _ = future_to_path[future]
            result = future.result()
            if result is not None:
                file_mb = os.path.getsize(fp) / (1024 * 1024) if os.path.exists(fp) else 0
                if running_mb + file_mb > MAX_TOTAL_MB_PER_REQUEST:
                    logger.warning(
                        "Running total would exceed %d MB cap — skipping %s",
                        MAX_TOTAL_MB_PER_REQUEST, fp,
                    )
                    # Delete the already-uploaded file we won't use
                    try:
                        client.files.delete(name=result.name)
                    except Exception:
                        pass
                    continue
                uploaded.append(result)
                running_mb += file_mb

    logger.info(
        "Upload complete: %d/%d file(s) ready · %.1f MB uploaded",
        len(uploaded), len(file_paths), running_mb,
    )
    return uploaded


def _cleanup_files(client: genai.Client, uploaded_files: list[types.File]) -> None:
    """Best-effort deletion of files from Gemini after use."""
    for f in uploaded_files:
        try:
            client.files.delete(name=f.name)
            logger.info("Deleted Gemini file: %s", f.name)
        except Exception as exc:
            logger.warning("Could not delete file %s: %s", f.name, exc)


# ---------------------------------------------------------------------------
# Content builder — THE fix for the original INVALID_ARGUMENT error
# ---------------------------------------------------------------------------

def _build_contents(
    system_prompt: str,
    user_text: str,
    uploaded_files: list[types.File],
) -> list[types.Content]:
    """
    Build a well-formed contents list for client.models.generate_content().

    The Gemini SDK requires contents to be a list[Content], each containing
    list[Part].  Mixing raw strings with File objects at the top level causes
    400 INVALID_ARGUMENT — which was the original bug.

    Structure produced:
        [
          Content(role="user", parts=[
              Part(text="SYSTEM PROMPT:\\n…\\nUSER INPUT:\\n…"),
              Part(file_data=FileData(file_uri=…, mime_type=…)),  # per file
              …
          ])
        ]
    """
    parts: list[types.Part] = []

    # ① System + user text as a single text Part
    combined_text = (
        f"SYSTEM PROMPT:\n{system_prompt}\n\n"
        f"USER INPUT:\n{user_text}"
    )
    parts.append(types.Part(text=combined_text))

    # ② One Part per uploaded file — must use FileData(uri), not the File object
    for gemini_file in uploaded_files:
        parts.append(
            types.Part(
                file_data=types.FileData(
                    file_uri=gemini_file.uri,
                    mime_type=gemini_file.mime_type,
                )
            )
        )

    return [types.Content(role="user", parts=parts)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_analysis(
    *,
    session_id: str,
    system_prompt: str,
    user_text: str,
    file_paths: Iterable[tuple[str, str]] = (),
) -> tuple[str, str]:
    """
    Execute a Gemini analysis call with automatic model fallback.

    Parameters
    ----------
    session_id    : used for log correlation only
    system_prompt : task instructions
    user_text     : user's query / data
    file_paths    : iterable of (absolute_path, mime_type)
                    Supports up to 50 files, up to ~1.9 GB each,
                    up to ~2 GB total per analysis run.

    Returns
    -------
    (output_markdown, engine_display_label)
    """
    file_paths_list = list(file_paths)
    last_err: Exception | None = None

    for model_name in MODEL_CHAIN:
        uploaded_files: list[types.File] = []
        client: genai.Client | None = None

        try:
            logger.info(
                "STRUCTMIND CORE LLM call · tier=%s · session=%s · files=%d",
                model_name, session_id, len(file_paths_list),
            )

            client = _get_client()

            # Upload files concurrently (individual failures are skipped)
            if file_paths_list:
                uploaded_files = _upload_files(client, file_paths_list)
                if not uploaded_files:
                    logger.warning(
                        "No files uploaded for session %s — running text-only",
                        session_id,
                    )

            # Build properly structured contents (the core fix)
            contents = _build_contents(system_prompt, user_text, uploaded_files)

            logger.info(
                "Calling %s · parts=%d · files=%d",
                model_name,
                sum(len(c.parts) for c in contents),
                len(uploaded_files),
            )

            # Call the model
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                ),
            )

            # Validate response
            if not response or not response.text or not response.text.strip():
                raise RuntimeError("Empty response from model")

            logger.info(
                "Analysis complete · tier=%s · session=%s · output_chars=%d",
                model_name, session_id, len(response.text),
            )
            return response.text, engine_label(model_name)

        except Exception as exc:
            last_err = exc
            logger.warning("Engine tier %s failed: %s", model_name, exc)
            # Fall through to next model in chain

        finally:
            # Always clean up uploaded files, even on failure
            if uploaded_files and client:
                try:
                    _cleanup_files(client, uploaded_files)
                except Exception:
                    pass

    raise RuntimeError(
        f"All STRUCTMIND CORE tiers failed. Last error: {last_err}"
    )
