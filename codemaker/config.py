"""Configuration loader for CodeMaker.

Reads from .env file and exposes a frozen Config dataclass with all
service parameters validated and parsed.
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Immutable service configuration."""

    gemini_api_key: str
    system_prompt: str
    trigger_sequence: list[str]
    gemini_model: str
    screenshot_tool: str
    kill_combo: frozenset[str]
    keyboard_device: Optional[str]

    def __post_init__(self):
        if not self.gemini_api_key or self.gemini_api_key == "your_api_key_here":
            print(
                "[CodeMaker] ERROR: GEMINI_API_KEY is not set. "
                "Copy .env.example to .env and fill in your API key.",
                file=sys.stderr,
            )
            sys.exit(1)

        if not self.trigger_sequence:
            print(
                "[CodeMaker] ERROR: TRIGGER_SEQUENCE is empty.",
                file=sys.stderr,
            )
            sys.exit(1)


def load_config(env_path: Optional[str] = None) -> Config:
    """Load configuration from .env file.

    Args:
        env_path: Explicit path to .env file. If None, searches
                  current directory and parent directories.

    Returns:
        Validated Config instance.
    """
    if env_path:
        load_dotenv(env_path)
    else:
        # Search from CWD upward for .env
        env_file = _find_env_file()
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()  # Try default locations

    trigger_raw = os.getenv(
        "TRIGGER_SEQUENCE", "tab,tab,tab,backspace,backspace,backspace"
    )
    trigger_sequence = [k.strip().lower() for k in trigger_raw.split(",") if k.strip()]

    kill_raw = os.getenv("KILL_COMBO", "ctrl+shift+escape")
    kill_combo = frozenset(k.strip().lower() for k in kill_raw.split("+") if k.strip())

    keyboard_device = os.getenv("KEYBOARD_DEVICE", "").strip() or None

    return Config(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        system_prompt=os.getenv(
            "SYSTEM_PROMPT", "Solve this in c and have no comments at all."
        ),
        trigger_sequence=trigger_sequence,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        screenshot_tool=os.getenv("SCREENSHOT_TOOL", "auto"),
        kill_combo=kill_combo,
        keyboard_device=keyboard_device,
    )


def _find_env_file() -> Optional[str]:
    """Walk up from CWD looking for a .env file."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            return str(candidate)
    return None
