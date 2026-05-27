"""LLM service with direct Gemini fallback chain."""
from __future__ import annotations

import logging
from typing import Iterable

import google.generativeai as genai

from config import settings

logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=settings.llm_key)

# Internal model chain
MODEL_CHAIN: list[str] = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]

# Public display label
ENGINE_LABELS: dict[str, str] = {
    "gemini-2.5-pro": "STRUCTMIND CORE · PRO",
    "gemini-2.5-flash": "STRUCTMIND CORE · FAST",
    "gemini-2.0-flash": "STRUCTMIND CORE · LITE",
}


def engine_label(internal_model: str) -> str:
    return ENGINE_LABELS.get(internal_model, "STRUCTMIND CORE")


async def run_analysis(
    *,
    session_id: str,
    system_prompt: str,
    user_text: str,
    file_paths: Iterable[tuple[str, str]] = (),
) -> tuple[str, str]:
    """
    Execute Gemini call with fallback chain.

    file_paths:
        iterable of (absolute_path, mime_type)

    Returns:
        (output_markdown, engine_display_label)
    """

    last_err: Exception | None = None

    # Build prompt
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

            # File support
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
                response = model.generate_content(
                    [prompt, *uploaded_files]
                )
            else:
                response = model.generate_content(prompt)

            if response and response.text.strip():
                return response.text, engine_label(model_name)

            raise RuntimeError("Empty response received")

        except Exception as e:
            last_err = e
            logger.warning(
                "Engine tier %s failed: %s",
                model_name,
                e,
            )
            continue

    raise RuntimeError(
        f"All STRUCTMIND CORE tiers failed. Last error: {last_err}"
    )