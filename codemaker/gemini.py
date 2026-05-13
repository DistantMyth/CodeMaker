"""Gemini API integration for screenshot → code generation.

Sends a screenshot to Gemini Vision with the configured system prompt
and returns the cleaned code response.
"""

import logging
import time
from typing import Optional

from google import genai
from google.genai import types

from .utils import strip_code_fences

logger = logging.getLogger("codemaker.gemini")

_MAX_RETRIES = 2
_RETRY_DELAY = 1.0  # seconds


def process_screenshot(
    image_bytes: bytes,
    api_key: str,
    system_prompt: str,
    model: str = "gemini-2.0-flash",
) -> str:
    """Send a screenshot to Gemini and get the code response.

    Args:
        image_bytes: PNG screenshot bytes.
        api_key: Gemini API key.
        system_prompt: Prompt sent with the image.
        model: Gemini model name.

    Returns:
        Cleaned code string (no markdown fences).

    Raises:
        RuntimeError: If API call fails after retries.
    """
    client = genai.Client(api_key=api_key)

    last_error: Optional[Exception] = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            logger.info(
                "Sending screenshot to Gemini (%s), attempt %d/%d",
                model, attempt + 1, _MAX_RETRIES + 1,
            )

            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/png",
                    ),
                    system_prompt,
                ],
            )

            raw_text = response.text
            if not raw_text:
                raise RuntimeError("Gemini returned empty response")

            code = strip_code_fences(raw_text)
            logger.info(
                "Gemini response: %d chars of code", len(code)
            )
            logger.debug("Code preview: %s...", code[:100])

            return code

        except Exception as ex:
            last_error = ex
            logger.warning(
                "Gemini API error (attempt %d): %s", attempt + 1, ex
            )
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY * (attempt + 1))

    raise RuntimeError(
        f"Gemini API failed after {_MAX_RETRIES + 1} attempts: {last_error}"
    )
