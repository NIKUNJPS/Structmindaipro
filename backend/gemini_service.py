"""Gemini LLM service using emergentintegrations with 4-model fallback chain."""
from __future__ import annotations

import logging
from typing import Iterable

from emergentintegrations.llm.chat import (
    FileContentWithMimeType,
    LlmChat,
    UserMessage,
)

from config import settings

logger = logging.getLogger(__name__)

# Production fallback chain as per spec
MODEL_CHAIN: list[str] = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]


async def run_analysis(
    *,
    session_id: str,
    system_prompt: str,
    user_text: str,
    file_paths: Iterable[tuple[str, str]] = (),
) -> tuple[str, str]:
    """
    Execute LLM call with full Gemini fallback chain.
    file_paths: iterable of (absolute_path, mime_type)
    Returns (output_markdown, model_used).
    Raises RuntimeError only if every model in the chain fails.
    """
    file_contents = [
        FileContentWithMimeType(file_path=p, mime_type=mt) for p, mt in file_paths
    ]

    last_err: Exception | None = None
    for model in MODEL_CHAIN:
        try:
            chat = LlmChat(
                api_key=settings.llm_key,
                session_id=session_id,
                system_message=system_prompt,
            ).with_model("gemini", model)
            msg = UserMessage(text=user_text, file_contents=file_contents or None)
            logger.info("LLM call · model=%s · session=%s", model, session_id)
            response = await chat.send_message(msg)
            if response and isinstance(response, str) and response.strip():
                return response, model
            raise RuntimeError("Empty response from model")
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("Model %s failed: %s", model, e)
            continue

    raise RuntimeError(f"All Gemini models failed. Last error: {last_err}")
