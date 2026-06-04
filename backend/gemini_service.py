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
    if sa_json:
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
    Upload files to Gemini Files API.
    Returns list of uploaded file references.
    Large files are uploaded to Google servers — no RAM spike.
    """
    uploaded = []
    for file_path, mime_type in file_paths:
        if not os.path.exists(file_path):
            logger.warning("File not found, skipping: %s", file_path)
            continue
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        logger.info("Uploading file %s (%.1f MB) to Gemini Files API", file_path, file_size_mb)
        try:
            uploaded_file = client.files.upload(
                path=file_path,
                config=types.UploadFileConfig(mime_type=mime_type),
            )
            # Wait for file to be processed
            max_wait = 60
            waited = 0
            while waited < max_wait:
                file_info = client.files.get(name=uploaded_file.name)
                if file_info.state.name == "ACTIVE":
                    logger.info("File %s is ready", uploaded_file.name)
                    uploaded.append(file_info)
                    break
                elif file_info.state.name == "FAILED":
                    logger.error("File processing failed: %s", uploaded_file.name)
                    break
                time.sleep(2)
                waited += 2
            else:
                logger.warning("File %s timed out waiting for processing", uploaded_file.name)
        except Exception as e:
            logger.warning("File upload failed for %s: %s", file_path, e)
    return uploaded


def _cleanup_files(client: genai.Client, uploaded_files: list) -> None:
    """Delete uploaded files from Gemini Files API after use."""
    for f in uploaded_files:
        try:
            client.files.delete(name=f.name)
            logger.info("Deleted Gemini file: %s", f.name)
        except Exception as e:
            logger.warning("Could not delete Gemini file %s: %s", f.name, e)


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

    prompt = f"""SYSTEM PROMPT:
{system_prompt}

USER INPUT:
{user_text}
"""

    for model_name in MODEL_CHAIN:
        uploaded_files = []
        try:
            logger.info(
                "STRUCTMIND CORE LLM call · tier=%s · session=%s",
                model_name,
                session_id,
            )

            # Fresh client per call (handles token expiry)
            client = _get_client()

            # Upload files to Gemini Files API (memory efficient)
            if file_paths_list:
                uploaded_files = _upload_files_to_gemini(client, file_paths_list)

            # Build contents
            if uploaded_files:
                contents = [prompt] + uploaded_files
            else:
                contents = [prompt]
                if file_paths_list:
                    logger.warning(
                        "No files uploaded successfully for session %s — running text-only",
                        session_id,
                    )

            # Generate response
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
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

            raise RuntimeError("Empty response received from model")

        except Exception as e:
            last_err = e
            logger.warning("Engine tier %s failed: %s", model_name, e)
            continue

        finally:
            # Always cleanup uploaded files
            if uploaded_files:
                try:
                    _cleanup_files(client, uploaded_files)
                except Exception:
                    pass

    raise RuntimeError(
        f"All STRUCTMIND CORE tiers failed. Last error: {last_err}"
    )
