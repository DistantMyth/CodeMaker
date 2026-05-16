"""Logging setup and shared utility functions."""

import logging
import re
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging for the service.

    Logs to stderr so they don't interfere with any stdout usage,
    and also writes to codemaker.log in the project root.
    """
    import os
    
    formatter = logging.Formatter(
        "[%(asctime)s] %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)

    # File handler (writes to CodeMaker/codemaker.log)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_file = os.path.join(project_root, "codemaker.log")
    
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    root = logging.getLogger("codemaker")
    root.setLevel(level)
    # Clear any existing handlers to prevent duplicates if called multiple times
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


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


# Regex that matches: string literals (preserve), single-line comments, multi-line comments
_C_COMMENT_RE = re.compile(
    r'("(?:[^"\\]|\\.)*"'       # Double-quoted string (group 1) — preserve
    r"|'(?:[^'\\]|\\.)*'"       # Single-quoted char literal — preserve
    r"|//[^\n]*"                # Single-line comment — remove
    r"|/\*.*?\*/)",             # Multi-line comment — remove
    re.DOTALL,
)


def _c_comment_replacer(match: re.Match) -> str:
    """Keep string/char literals, remove comments."""
    text = match.group(0)
    if text.startswith(("//")):
        return ""
    if text.startswith("/*"):
        return ""
    return text  # It's a string or char literal — keep it


def strip_c_comments(code: str) -> str:
    """Remove C/C++ comments while preserving string literals.

    Handles:
        - Single-line comments: // ...
        - Multi-line comments:  /* ... */
        - Preserves // and /* inside string literals

    Args:
        code: C or C++ source code.

    Returns:
        Code with all comments removed and blank lines collapsed.
    """
    result = _C_COMMENT_RE.sub(_c_comment_replacer, code)
    return strip_blank_lines(result)


def strip_blank_lines(code: str) -> str:
    """Collapse multiple consecutive blank lines into at most one.

    Also removes trailing whitespace from each line.

    Args:
        code: Source code string.

    Returns:
        Cleaned code string.
    """
    lines = code.split("\n")
    cleaned = []
    prev_blank = False
    for line in lines:
        stripped = line.rstrip()
        is_blank = not stripped
        if is_blank and prev_blank:
            continue  # Skip consecutive blank lines
        cleaned.append(stripped)
        prev_blank = is_blank
    return "\n".join(cleaned).strip()
