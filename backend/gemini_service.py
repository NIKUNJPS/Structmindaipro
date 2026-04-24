"""LLM service with 4X Core model fallback chain (powered by emergentintegrations)."""
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

# Internal model chain (not exposed to users — UI always says "STRUCTMIND CORE")
MODEL_CHAIN: list[str] = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]

# Public display label for each internal model tier
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
    Execute LLM call with full 4X Core fallback chain.
    file_paths: iterable of (absolute_path, mime_type).
    Returns (output_markdown, engine_display_label).
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
            logger.info("4X Core LLM call · tier=%s · session=%s", model, session_id)
            response = await chat.send_message(msg)
            if response and isinstance(response, str) and response.strip():
                return response, engine_label(model)
            raise RuntimeError("Empty response")
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("Engine tier %s failed: %s", model, e)
            continue

    raise RuntimeError(f"All STRUCTMIND CORE tiers failed. Last error: {last_err}")

