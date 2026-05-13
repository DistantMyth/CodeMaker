"""Screenshot capture with universal compositor support.

Fallback chain: grim → gnome-screenshot → XDG Portal → Pillow (X11/fallback)
Each method is tried in order until one succeeds.
"""

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("codemaker.capture")


def capture_screenshot(preferred_tool: str = "auto") -> bytes:
    """Capture the primary monitor and return PNG bytes.

    Args:
        preferred_tool: "grim", "portal", "gnome-screenshot", "pillow",
                        or "auto" (tries each in order).

    Returns:
        PNG image bytes.

    Raises:
        RuntimeError: If no capture method succeeds.
    """
    if preferred_tool != "auto":
        func = _TOOLS.get(preferred_tool)
        if func is None:
            raise ValueError(f"Unknown screenshot tool: {preferred_tool}")
        result = func()
        if result is not None:
            return result
        raise RuntimeError(f"Screenshot tool '{preferred_tool}' failed")

    # Auto: try each method in order
    for name, func in _TOOLS.items():
        try:
            result = func()
            if result is not None:
                logger.info("Screenshot captured via %s", name)
                return result
        except Exception as ex:
            logger.debug("Screenshot method '%s' failed: %s", name, ex)
            continue

    raise RuntimeError(
        "All screenshot methods failed. Install 'grim' (wlroots), "
        "or ensure gnome-screenshot/xdg-desktop-portal is available."
    )


def _capture_grim() -> Optional[bytes]:
    """Capture using grim (wlroots: Hyprland, Sway, river, etc.)."""
    if not shutil.which("grim"):
        return None
    result = subprocess.run(
        ["grim", "-"],  # Output PNG to stdout
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        logger.debug("grim stderr: %s", result.stderr.decode(errors="replace"))
        return None
    if not result.stdout:
        return None
    return result.stdout


def _capture_gnome_screenshot() -> Optional[bytes]:
    """Capture using gnome-screenshot (GNOME)."""
    if not shutil.which("gnome-screenshot"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["gnome-screenshot", "-f", tmp_path],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        p = Path(tmp_path)
        if not p.exists() or p.stat().st_size == 0:
            return None
        return p.read_bytes()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _capture_spectacle() -> Optional[bytes]:
    """Capture using spectacle (KDE Plasma)."""
    if not shutil.which("spectacle"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["spectacle", "-b", "-n", "-o", tmp_path],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        p = Path(tmp_path)
        if not p.exists() or p.stat().st_size == 0:
            return None
        return p.read_bytes()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _capture_pillow() -> Optional[bytes]:
    """Capture using Pillow's ImageGrab (X11 or Windows fallback)."""
    try:
        from PIL import ImageGrab
        import io
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as ex:
        logger.debug("Pillow ImageGrab failed: %s", ex)
        return None


if sys.platform == "win32":
    def _capture_windows() -> Optional[bytes]:
        """Windows screenshot via Pillow ImageGrab."""
        return _capture_pillow()

    _TOOLS = {
        "windows": _capture_windows,
        "pillow": _capture_pillow,
    }
else:
    _TOOLS = {
        "grim": _capture_grim,
        "gnome-screenshot": _capture_gnome_screenshot,
        "spectacle": _capture_spectacle,
        "pillow": _capture_pillow,
    }
