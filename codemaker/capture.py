"""Screenshot capture with universal compositor support.

Fallback chain: grim → gnome-screenshot → spectacle → Pillow
Each method is tried in order until one succeeds.

When running as root (via sudo), we automatically recover the
original user's Wayland/X11 environment so screenshot tools can
connect to the compositor.
"""

import logging
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("codemaker.capture")


def _get_wayland_env() -> dict[str, str]:
    """Build an environment dict that lets screenshot tools connect to the compositor.

    When running as root via sudo, tools like grim/gnome-screenshot fail because
    XDG_RUNTIME_DIR and WAYLAND_DISPLAY are not set. We recover them from the
    original user's environment.
    """
    env = os.environ.copy()

    # If XDG_RUNTIME_DIR is already set and valid, use as-is
    xdg = env.get("XDG_RUNTIME_DIR", "")
    if xdg and Path(xdg).is_dir():
        return env

    # Recover from sudo context
    sudo_user = os.environ.get("SUDO_USER")
    sudo_uid = os.environ.get("SUDO_UID")

    if sudo_uid:
        uid = sudo_uid
    elif sudo_user:
        try:
            uid = str(pwd.getpwnam(sudo_user).pw_uid)
        except KeyError:
            uid = None
    else:
        uid = None

    if uid:
        runtime_dir = f"/run/user/{uid}"
        if Path(runtime_dir).is_dir():
            env["XDG_RUNTIME_DIR"] = runtime_dir
            logger.debug("Recovered XDG_RUNTIME_DIR=%s", runtime_dir)

    # Recover WAYLAND_DISPLAY if not set
    if "WAYLAND_DISPLAY" not in env:
        # Try common wayland socket names
        xdg_dir = env.get("XDG_RUNTIME_DIR", "")
        if xdg_dir:
            for name in ("wayland-1", "wayland-0"):
                sock = Path(xdg_dir) / name
                if sock.exists():
                    env["WAYLAND_DISPLAY"] = name
                    logger.debug("Recovered WAYLAND_DISPLAY=%s", name)
                    break

    # Recover DISPLAY for X11/XWayland fallback
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":0"

    # Recover HOME for tools that need ~/.config
    if sudo_user and env.get("HOME") == "/root":
        try:
            env["HOME"] = pwd.getpwnam(sudo_user).pw_dir
        except KeyError:
            pass

    return env


def capture_screenshot(preferred_tool: str = "auto") -> bytes:
    """Capture the primary monitor and return PNG bytes.

    Args:
        preferred_tool: "grim", "gnome-screenshot", "spectacle", "pillow",
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
        "or ensure gnome-screenshot/xdg-desktop-portal is available.\n"
        "If running via sudo, try: sudo -E .venv/bin/python -m codemaker"
    )


def _capture_grim() -> Optional[bytes]:
    """Capture using grim (wlroots: Hyprland, Sway, river, etc.)."""
    if not shutil.which("grim"):
        return None
    env = _get_wayland_env()
    result = subprocess.run(
        ["grim", "-"],  # Output PNG to stdout
        capture_output=True,
        timeout=10,
        env=env,
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
    env = _get_wayland_env()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["gnome-screenshot", "-f", tmp_path],
            capture_output=True,
            timeout=10,
            env=env,
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
    env = _get_wayland_env()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            ["spectacle", "-b", "-n", "-o", tmp_path],
            capture_output=True,
            timeout=10,
            env=env,
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
