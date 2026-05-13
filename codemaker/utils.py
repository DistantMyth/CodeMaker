"""Logging setup and shared utility functions."""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging for the service.

    Logs to stderr so they don't interfere with any stdout usage.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(name)s %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger("codemaker")
    root.setLevel(level)
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)


def strip_code_fences(text: str) -> str:
    """Remove markdown code fences from Gemini API responses.

    Handles patterns like:
        ```c
        code here
        ```

        ```
        code here
        ```

    Args:
        text: Raw API response text.

    Returns:
        Cleaned code string with leading/trailing whitespace trimmed.
    """
    text = text.strip()

    # Remove opening fence with optional language tag
    if text.startswith("```"):
        # Find end of first line (the opening fence)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]

    # Remove closing fence
    if text.endswith("```"):
        text = text[:-3]

    return text.strip()


def strip_indentation(code: str) -> str:
    """Remove all leading whitespace from every line of code.

    This allows the editor's auto-indent to handle formatting
    instead of conflicting with the AI's indentation style.

    Args:
        code: Code string with indentation.

    Returns:
        Code with all leading whitespace stripped from each line.
    """
    lines = code.split("\n")
    stripped = [line.lstrip() for line in lines]
    return "\n".join(stripped)
