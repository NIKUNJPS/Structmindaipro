"""LLM service using google.genai with service account authentication."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Iterable

import google.genai as genai
from google.genai import types
from google.oauth2 import service_account
from google.auth.transport.requests import Request

from config import settings

logger = logging.getLogger(__name__)

MODEL_CHAIN: list[str] = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]

ENGINE_LABELS: dict[str, str] = {
    "gemini-2.5-pro":   "STRUCTMIND CORE · PRO",
    "gemini-2.5-flash": "STRUCTMIND CORE · FAST",
    "gemini-2.0-flash": "STRUCTMIND CORE · LITE",
}

# Gemini safe limits — stay well under the context window
MAX_BATCH_MB = 45.0      # max total MB per Gemini request
MAX_FILES_PER_BATCH = 6  # max files per Gemini request


def engine_label(internal_model: str) -> str:
    return ENGINE_LABELS.get(internal_model, "STRUCTMIND CORE")


def _get_credentials():
    """Get fresh service account credentials."""
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
    except Exception as e:
        logger.warning("Service account auth failed: %s", e)
        return None


def _get_client() -> genai.Client:
    """Get authenticated Gemini client."""
    credentials = _get_credentials()
    if credentials:
        logger.info("Gemini client created with service account")
        return genai.Client(credentials=credentials)
    if settings.llm_key:
        logger.info("Gemini client created with API key")
        return genai.Client(api_key=settings.llm_key)
    raise RuntimeError("No Gemini credentials configured")


def _build_batches(
    file_paths: list[tuple[str, str]],
) -> list[list[tuple[str, str]]]:
    """
    Split file_paths into batches that each stay under MAX_BATCH_MB and
    MAX_FILES_PER_BATCH. Largest files first so we don't waste slots on
    small files after a large one already fills the batch.
    """
    # Sort largest first so big files open their own batch
    sorted_files = sorted(
        file_paths,
        key=lambda x: os.path.getsize(x[0]) if os.path.exists(x[0]) else 0,
        reverse=True,
    )

    batches: list[list[tuple[str, str]]] = []
    batch_sizes: list[float] = []

    for fp, mime in sorted_files:
        if not os.path.exists(fp):
            logger.warning("File not found, skipping: %s", fp)
            continue
        size_mb = os.path.getsize(fp) / (1024 * 1024)

        placed = False
        for i, batch in enumerate(batches):
            if (
                len(batch) < MAX_FILES_PER_BATCH
                and batch_sizes[i] + size_mb <= MAX_BATCH_MB
            ):
                batch.append((fp, mime))
                batch_sizes[i] += size_mb
                placed = True
                break

        if not placed:
            batches.append([(fp, mime)])
            batch_sizes.append(size_mb)

    for i, (batch, sz) in enumerate(zip(batches, batch_sizes)):
        logger.info(
            "Batch %d/%d: %d files, %.1f MB",
            i + 1, len(batches), len(batch), sz,
        )
    return batches


def _upload_files_to_gemini(
    client: genai.Client,
    file_paths: list[tuple[str, str]],
) -> list:
    """Upload files to Gemini Files API. Memory efficient — streamed to Google."""
    uploaded = []
    for file_path, mime_type in file_paths:
        if not os.path.exists(file_path):
            logger.warning("File not found, skipping: %s", file_path)
            continue
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        logger.info("Uploading %.1f MB to Gemini Files API: %s", file_size_mb, file_path)
        try:
            with open(file_path, "rb") as f:
                uploaded_file = client.files.upload(
                    file=f,
                    config=types.UploadFileConfig(mime_type=mime_type),
                )

            max_wait = 120
            waited = 0
            while waited < max_wait:
                file_info = client.files.get(name=uploaded_file.name)
                state = file_info.state.name
                if state == "ACTIVE":
                    logger.info("File ready: %s (%.1f MB)", uploaded_file.name, file_size_mb)
                    uploaded.append(file_info)
                    break
                elif state == "FAILED":
                    logger.error("File processing failed: %s", uploaded_file.name)
                    break
                else:
                    logger.info("File state: %s — waiting...", state)
                    time.sleep(3)
                    waited += 3
            else:
                logger.warning("File timed out: %s", uploaded_file.name)

        except Exception as e:
            logger.warning("File upload failed for %s: %s", file_path, e)

    return uploaded


def _cleanup_files(client: genai.Client, uploaded_files: list) -> None:
    """Delete uploaded files from Gemini after use."""
    for f in uploaded_files:
        try:
            client.files.delete(name=f.name)
            logger.info("Deleted Gemini file: %s", f.name)
        except Exception as e:
            logger.warning("Could not delete file %s: %s", f.name, e)


async def _run_single_batch(
    *,
    client: genai.Client,
    model_name: str,
    system_prompt: str,
    user_text: str,
    batch_files: list[tuple[str, str]],
    batch_num: int,
    total_batches: int,
    session_id: str,
) -> str:
    """Run one Gemini request for a single batch of files. Returns text output."""
    uploaded_files = []
    try:
        if batch_files:
            uploaded_files = _upload_files_to_gemini(client, batch_files)

        batch_user_text = user_text
        if total_batches > 1:
            batch_user_text = (
                f"[Batch {batch_num} of {total_batches}]\n\n"
                f"{user_text}\n\n"
                f"Note: You are analysing file batch {batch_num} of {total_batches}. "
                f"Analyse only the files in this batch thoroughly."
            )

        parts: list[types.Part] = [types.Part(text=batch_user_text)]
        for f in uploaded_files:
            parts.append(
                types.Part(
                    file_data=types.FileData(
                        file_uri=f.uri,
                        mime_type=f.mime_type,
                    )
                )
            )

        response = client.models.generate_content(
            model=model_name,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
                max_output_tokens=8192,
            ),
        )

        if response and response.text and response.text.strip():
            return response.text.strip()

        raise RuntimeError("Empty response from model")

    finally:
        if uploaded_files and client:
            try:
                _cleanup_files(client, uploaded_files)
            except Exception:
                pass


def _merge_batch_outputs(outputs: list[str], total_batches: int) -> str:
    """Merge multiple batch outputs into one coherent report."""
    if len(outputs) == 1:
        return outputs[0]

    merged = f"# COMBINED ANALYSIS REPORT ({total_batches} file batches)\n\n"
    for i, out in enumerate(outputs, 1):
        merged += f"\n\n---\n## BATCH {i} OF {total_batches}\n\n{out}"
    return merged


async def run_analysis(
    *,
    session_id: str,
    system_prompt: str,
    user_text: str,
    file_paths: Iterable[tuple[str, str]] = (),
) -> tuple[str, str]:
    """
    Execute Gemini call with batching + fallback chain.
    Large file sets are split into safe-sized batches and results merged.
    Returns: (output_markdown, engine_display_label)
    """
    last_err: Exception | None = None
    file_paths_list = list(file_paths)

    # Build batches upfront (same batches reused across model fallbacks)
    if file_paths_list:
        batches = _build_batches(file_paths_list)
    else:
        batches = [[]]  # text-only: one empty batch

    logger.info(
        "session=%s total_files=%d total_batches=%d",
        session_id, len(file_paths_list), len(batches),
    )

    for model_name in MODEL_CHAIN:
        try:
            logger.info(
                "STRUCTMIND CORE LLM call · tier=%s · session=%s · batches=%d",
                model_name, session_id, len(batches),
            )
            client = _get_client()
            batch_outputs: list[str] = []

            for i, batch in enumerate(batches, 1):
                logger.info(
                    "Processing batch %d/%d · tier=%s · session=%s",
                    i, len(batches), model_name, session_id,
                )
                output = await _run_single_batch(
                    client=client,
                    model_name=model_name,
                    system_prompt=system_prompt,
                    user_text=user_text,
                    batch_files=batch,
                    batch_num=i,
                    total_batches=len(batches),
                    session_id=session_id,
                )
                batch_outputs.append(output)

            final_output = _merge_batch_outputs(batch_outputs, len(batches))

            logger.info(
                "Analysis complete · tier=%s · session=%s · batches=%d",
                model_name, session_id, len(batches),
            )
            return final_output, engine_label(model_name)

        except Exception as e:
            last_err = e
            logger.warning("Engine tier %s failed: %s", model_name, e)
            continue

    raise RuntimeError(
        f"All STRUCTMIND CORE tiers failed. Last error: {last_err}"
    )
