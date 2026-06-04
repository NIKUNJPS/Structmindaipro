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


def _upload_files_to_gemini(
    client: genai.Client,
    file_paths: list[tuple[str, str]],
) -> list:
    """
    Upload files to Gemini Files API using file object (not path).
    Memory efficient — files go to Google servers, not RAM.
    """
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

            # Poll until ACTIVE
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


async def run_analysis(
    *,
    session_id: str,
    system_prompt: str,
    user_text: str,
    file_paths: Iterable[tuple[str, str]] = (),
) -> tuple[str, str]:
    """
    Execute Gemini call with fallback chain.
    file_paths: iterable of (absolute_path, mime_type)
    Returns: (output_markdown, engine_display_label)
    """
    last_err: Exception | None = None
    file_paths_list = list(file_paths)

    for model_name in MODEL_CHAIN:
        uploaded_files = []
        client = None
        try:
            logger.info(
                "STRUCTMIND CORE LLM call · tier=%s · session=%s",
                model_name,
                session_id,
            )

            client = _get_client()

            # Upload files to Gemini Files API
            if file_paths_list:
                uploaded_files = _upload_files_to_gemini(client, file_paths_list)
                if not uploaded_files:
                    logger.warning(
                        "No files uploaded for session %s — running text-only",
                        session_id,
                    )

            # Build user parts: text first, then file references
            parts: list[types.Part] = [types.Part(text=user_text)]
            for f in uploaded_files:
                parts.append(
                    types.Part(
                        file_data=types.FileData(
                            file_uri=f.uri,
                            mime_type=f.mime_type,
                        )
                    )
                )

            # system_prompt goes in system_instruction (NOT in contents)
            # This is the correct Gemini API structure and avoids 400 errors
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
                logger.info(
                    "Analysis complete · tier=%s · session=%s",
                    model_name,
                    session_id,
                )
                return response.text, engine_label(model_name)

            raise RuntimeError("Empty response from model")

        except Exception as e:
            last_err = e
            logger.warning("Engine tier %s failed: %s", model_name, e)
            continue

        finally:
            # Always cleanup uploaded files from Gemini
            if uploaded_files and client:
                try:
                    _cleanup_files(client, uploaded_files)
                except Exception:
                    pass

    raise RuntimeError(
        f"All STRUCTMIND CORE tiers failed. Last error: {last_err}"
    )
