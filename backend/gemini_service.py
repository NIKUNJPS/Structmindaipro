"""LLM service using google.genai with service account authentication."""
from __future__ import annotations

import json
import logging
import os
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


def _get_client() -> genai.Client:
    """Get authenticated Gemini client."""
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        try:
            sa_info = json.loads(sa_json)
            credentials = service_account.Credentials.from_service_account_info(
                sa_info,
                scopes=["https://www.googleapis.com/auth/generative-language"],
            )
            credentials.refresh(Request())
            logger.info("Gemini client created with service account")
            return genai.Client(credentials=credentials)
        except Exception as e:
            logger.warning("Service account auth failed: %s — trying API key", e)

    if settings.llm_key:
        logger.info("Gemini client created with API key")
        return genai.Client(api_key=settings.llm_key)

    raise RuntimeError("No Gemini credentials configured")


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

    prompt = f"""SYSTEM PROMPT:
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

            # Fresh client per call (handles token expiry)
            client = _get_client()

            # Upload files
            uploaded_parts = []
            for file_path, mime_type in file_paths:
                try:
                    with open(file_path, "rb") as f:
                        file_data = f.read()
                    uploaded_parts.append(
                        types.Part.from_bytes(data=file_data, mime_type=mime_type)
                    )
                except Exception as file_error:
                    logger.warning(
                        "File read failed for %s: %s", file_path, file_error
                    )

            # Build contents
            contents = [prompt] + uploaded_parts if uploaded_parts else [prompt]

            response = client.models.generate_content(
                model=model_name,
                contents=contents,
            )

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
