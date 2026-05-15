"""Configuration loader for CodeMaker.

Reads from .env file and exposes a frozen Config dataclass with all
service parameters validated and parsed.
"""

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .providers import ProviderConfig

logger = logging.getLogger("codemaker.config")


@dataclass(frozen=True)
class Config:
    """Immutable service configuration."""

    system_prompt: str
    trigger_sequence: list[str]
    screenshot_tool: str
    kill_combo: frozenset[str]
    reset_combo: frozenset[str]
    keyboard_device: Optional[str]
    providers: list[ProviderConfig] = field(default_factory=list)

    # Legacy fields kept for backward compat
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    def __post_init__(self):
        if not self.providers:
            print(
                "[CodeMaker] ERROR: No AI providers configured. "
                "Set up at least one provider in .env.",
                file=sys.stderr,
            )
            sys.exit(1)

        if not self.trigger_sequence:
            print(
                "[CodeMaker] ERROR: TRIGGER_SEQUENCE is empty.",
                file=sys.stderr,
            )
            sys.exit(1)


def _parse_providers() -> list[ProviderConfig]:
    """Parse provider configs from environment variables.

    Reads PROVIDER_1_TYPE through PROVIDER_5_TYPE, plus LOCAL_MODEL
    for Ollama. Returns them ordered by PROVIDER_PRIORITY.
    """
    providers: dict[str, ProviderConfig] = {}

    # ── Parse the 5 API provider slots ──
    for i in range(1, 6):
        prefix = f"PROVIDER_{i}"
        ptype = os.getenv(f"{prefix}_TYPE", "").strip().lower()
        if not ptype:
            continue

        cfg = ProviderConfig(
            name=f"provider_{i}",
            provider_type=ptype,
            api_key=os.getenv(f"{prefix}_KEY", "").strip(),
            model=os.getenv(f"{prefix}_MODEL", "").strip(),
            base_url=os.getenv(f"{prefix}_BASE_URL", "").strip(),
        )

        if cfg.is_configured:
            providers[str(i)] = cfg
            logger.debug(
                "Provider %d: type=%s model=%s", i, ptype, cfg.model
            )
        else:
            logger.debug(
                "Provider %d (%s): skipped (incomplete config)", i, ptype
            )

    # ── Parse local Ollama provider ──
    local_model = os.getenv("LOCAL_MODEL", "").strip()
    local_vision_model = os.getenv("LOCAL_VISION_MODEL", "").strip()
    local_code_model = os.getenv("LOCAL_CODE_MODEL", "").strip()
    local_vision_prompt = os.getenv("LOCAL_VISION_PROMPT", "").strip()
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").strip()

    if local_model or (local_vision_model and local_code_model):
        local_cfg = ProviderConfig(
            name="local",
            provider_type="ollama",
            model=local_model,
            base_url=ollama_url,
            vision_model=local_vision_model,
            code_model=local_code_model,
            vision_prompt=local_vision_prompt,
        )
        providers["local"] = local_cfg
        if local_vision_model and local_code_model:
            logger.debug(
                "Local pipeline: vision=%s code=%s url=%s",
                local_vision_model, local_code_model, ollama_url,
            )
        else:
            logger.debug("Local provider: model=%s url=%s", local_model, ollama_url)

    # ── Legacy fallback: if no providers, try old GEMINI_API_KEY ──
    if not providers:
        old_key = os.getenv("GEMINI_API_KEY", "").strip()
        old_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
        if old_key and old_key != "your_api_key_here":
            providers["1"] = ProviderConfig(
                name="provider_1",
                provider_type="gemini",
                api_key=old_key,
                model=old_model,
            )
            logger.info("Using legacy GEMINI_API_KEY config")

    # ── Apply priority ordering ──
    priority_raw = os.getenv("PROVIDER_PRIORITY", "").strip()
    if priority_raw:
        priority_order = [p.strip() for p in priority_raw.split(",") if p.strip()]
    else:
        # Default: 1,2,3,4,5,local
        priority_order = [str(i) for i in range(1, 6)] + ["local"]

    ordered = []
    for key in priority_order:
        if key in providers:
            ordered.append(providers.pop(key))

    # Append any remaining providers not in priority list
    for cfg in providers.values():
        ordered.append(cfg)

    return ordered


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

    reset_raw = os.getenv("RESET_COMBO", "ctrl+shift+r")
    reset_combo = frozenset(k.strip().lower() for k in reset_raw.split("+") if k.strip())

    keyboard_device = os.getenv("KEYBOARD_DEVICE", "").strip() or None

    providers = _parse_providers()

    return Config(
        system_prompt=os.getenv(
            "SYSTEM_PROMPT", "Solve this in c and have no comments at all."
        ),
        trigger_sequence=trigger_sequence,
        screenshot_tool=os.getenv("SCREENSHOT_TOOL", "auto"),
        kill_combo=kill_combo,
        reset_combo=reset_combo,
        keyboard_device=keyboard_device,
        providers=providers,
    )


def _find_env_file() -> Optional[str]:
    """Walk up from CWD looking for a .env file."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        candidate = parent / ".env"
        if candidate.is_file():
            return str(candidate)
    return None
