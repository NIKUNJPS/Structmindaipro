"""LLM service with service account authentication for Gemini."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Iterable

import google.generativeai as genai
from google.oauth2 import service_account
from google.auth.transport.requests import Request

from config import settings

logger = logging.getLogger(__name__)

# ── Authentication ──────────────────────────────────────────────────────────
def _configure_genai() -> None:
    """Configure Gemini with service account or API key."""
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        try:
            sa_info = json.loads(sa_json)
            credentials = service_account.Credentials.from_service_account_info(
                sa_info,
                scopes=["https://www.googleapis.com/auth/generative-language"],
            )
            # Refresh to get access token
            credentials.refresh(Request())
            # Configure genai with the access token
            genai.configure(api_key=credentials.token)
            logger.info("Gemini configured with service account credentials")
            return
        except Exception as e:
            logger.warning("Service account auth failed: %s — falling back to API key", e)
    
    # Fallback to regular API key
    if settings.llm_key:
        genai.configure(api_key=settings.llm_key)
        logger.info("Gemini configured with API key")
    else:
        raise RuntimeError("No Gemini credentials configured")


_configure_genai()

# ── Model chain ─────────────────────────────────────────────────────────────
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


def _refresh_token_if_needed() -> None:
    """Re-configure genai with a fresh token (tokens expire in 1hr)."""
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_json:
        return
    try:
        sa_info = json.loads(sa_json)
        credentials = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/generative-language"],
        )
        credentials.refresh(Request())
        genai.configure(api_key=credentials.token)
    except Exception as e:
        logger.warning("Token refresh failed: %s", e)


# ── Main function ────────────────────────────────────────────────────────────
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
    # Refresh token before each analysis call
    _refresh_token_if_needed()

    last_err: Exception | None = None
    prompt = f"""
SYSTEM PROMPT:
{system_prompt}

USER INPUT:
{user_text}
"""
    for model_name in MODEL_CHAIN:
        try:
            logger.info(
                "STRUCTMIND CORE LLM call · tier=%s · session=%s",
                model_name,
                session_id,
            )
            model = genai.GenerativeModel(model_name)

            # Upload files
            uploaded_files = []
            for file_path, mime_type in file_paths:
                try:
                    uploaded_file = genai.upload_file(
                        path=file_path,
                        mime_type=mime_type,
                    )
                    uploaded_files.append(uploaded_file)
                except Exception as file_error:
                    logger.warning(
                        "File upload failed for %s: %s",
                        file_path,
                        file_error,
                    )

            # Generate response
            if uploaded_files:
                response = model.generate_content([prompt, *uploaded_files])
            else:
                response = model.generate_content(prompt)

            if response and response.text.strip():
                return response.text, engine_label(model_name)

            raise RuntimeError("Empty response received")

        except Exception as e:
            last_err = e
            logger.warning("Engine tier %s failed: %s", model_name, e)
            continue

    raise RuntimeError(
        f"All STRUCTMIND CORE tiers failed. Last error: {last_err}"
    )
