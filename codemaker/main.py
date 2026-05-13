"""CodeMaker entry point and orchestrator.

Wires together all modules: config, state machine, trigger detector,
platform hook, screenshot capture, AI providers, and playback buffer.

Usage:
    sudo python -m codemaker.main
    # or
    sudo python -m codemaker
"""

import logging
import sys
import threading
from typing import Optional

from .config import load_config, Config
from .state import ServiceState, StateManager
from .trigger import TriggerDetector
from .playback import PlaybackBuffer
from .capture import capture_screenshot
from .providers import process_screenshot
from .utils import setup_logging
from .platform.base import KeyAction, KeyEventType, PlatformHook

logger = logging.getLogger("codemaker.main")


def _detect_platform(config: Config) -> PlatformHook:
    """Instantiate the correct platform hook for the current OS."""
    if sys.platform == "linux":
        from .platform.linux import LinuxHook
        return LinuxHook(keyboard_device_path=config.keyboard_device)
    elif sys.platform == "win32":
        from .platform.windows import WindowsHook
        return WindowsHook()
    else:
        print(
            f"[CodeMaker] Unsupported platform: {sys.platform}",
            file=sys.stderr,
        )
        sys.exit(1)


def main(env_path: Optional[str] = None) -> None:
    """Main entry point for the CodeMaker service."""
    setup_logging(logging.DEBUG)

    config = load_config(env_path)
    state = StateManager(
        on_change=lambda old, new: logger.info(
            "=== STATE: %s → %s ===", old.value, new.value
        ),
    )
    trigger = TriggerDetector(config.trigger_sequence)
    platform = _detect_platform(config)

    # Mutable state shared between the callback and the capture thread
    playback_buf: Optional[PlaybackBuffer] = None
    buf_lock = threading.Lock()

    def capture_and_process():
        """Background thread: screenshot → Gemini → enter Playback mode."""
        nonlocal playback_buf
        try:
            logger.info("Capturing screenshot...")
            image_bytes = capture_screenshot(config.screenshot_tool)
            logger.info(
                "Screenshot captured: %d bytes", len(image_bytes)
            )

            logger.info("Sending to AI provider...")
            code = process_screenshot(
                image_bytes=image_bytes,
                system_prompt=config.system_prompt,
                providers=config.providers,
            )

            with buf_lock:
                playback_buf = PlaybackBuffer(code)

            state.transition(ServiceState.PLAYBACK)
            logger.info("Playback ready: %d characters", len(code))

        except Exception as ex:
            logger.error("Capture/API failed: %s", ex)
            state.reset()  # Back to OBSERVER on error
            trigger.reset()

    def on_key_event(key_name: str, event_type: KeyEventType) -> KeyAction:
        """Central key event handler — the brain of the service."""
        nonlocal playback_buf

        # ─── Emergency Kill (always active) ───
        if hasattr(platform, 'get_held_modifiers'):
            held = platform.get_held_modifiers()
            # Include current key in check
            check_keys = held | {key_name}
            if config.kill_combo and config.kill_combo.issubset(check_keys):
                logger.info("KILL COMBO detected! Shutting down.")
                platform.stop()
                return KeyAction.PASS_THROUGH

        # ─── Only process KEY_DOWN events for state logic ───
        if event_type != KeyEventType.KEY_DOWN:
            return KeyAction.PASS_THROUGH

        current = state.current

        # ─── OBSERVER Mode ───
        if current == ServiceState.OBSERVER:
            matched = trigger.feed(key_name)
            logger.debug(
                "KEY: %-12s | buffer: %s | match: %s",
                key_name, trigger.current_buffer, matched,
            )
            if matched:
                logger.info("TRIGGER SEQUENCE MATCHED!")
                state.transition(ServiceState.CAPTURE)
                thread = threading.Thread(
                    target=capture_and_process, daemon=True
                )
                thread.start()
                return KeyAction.BLOCK  # Suppress the last trigger key
            return KeyAction.PASS_THROUGH

        # ─── CAPTURE Mode (waiting for API) ───
        if current == ServiceState.CAPTURE:
            return KeyAction.PASS_THROUGH

        # ─── PLAYBACK Mode ───
        if current == ServiceState.PLAYBACK:
            with buf_lock:
                buf = playback_buf

            if buf is None:
                return KeyAction.PASS_THROUGH

            # Handle backspace
            if key_name == "backspace":
                should_send = buf.backspace()
                if should_send:
                    # Let the real backspace through (deletes injected char)
                    return KeyAction.PASS_THROUGH
                else:
                    # Block — we're at position 0, tracking negative offset
                    return KeyAction.BLOCK

            # Skip modifier/function keys — let them pass through
            if key_name in (
                "shift", "ctrl", "alt", "meta", "capslock",
                "escape", "tab", "enter", "delete",
                "up", "down", "left", "right",
                "home", "end", "pageup", "pagedown",
            ) or key_name.startswith("f") and key_name[1:].isdigit():
                return KeyAction.PASS_THROUGH

            # Get the next character from the buffer
            char = buf.next_char()

            if char is None:
                if buf.exhausted:
                    logger.info("Playback complete!")
                    state.transition(ServiceState.OBSERVER)
                    with buf_lock:
                        playback_buf = None
                    trigger.reset()
                    return KeyAction.PASS_THROUGH
                # During negative_offset recovery — swallow the key
                return KeyAction.BLOCK

            # Inject the buffer character instead of the real one
            platform.inject_char(char)
            return KeyAction.BLOCK

        return KeyAction.PASS_THROUGH

    # Build provider chain display
    provider_chain = " → ".join(
        f"{p.name}({p.provider_type}:{p.model.split('/')[-1][:15]})"
        for p in config.providers if p.is_configured
    )

    # Print startup banner
    print(
        "╔══════════════════════════════════════════╗\n"
        "║         CodeMaker v0.1.0 Active          ║\n"
        "║                                          ║\n"
        f"║  Trigger: {','.join(config.trigger_sequence):<29}║\n"
        f"║  Kill:    {'+'.join(sorted(config.kill_combo)):<29}║\n"
        "║                                          ║\n"
        "║  Waiting for trigger sequence...          ║\n"
        "╚══════════════════════════════════════════╝\n"
        f"  Providers: {provider_chain}",
        file=sys.stderr,
    )

    # Start the hook (blocks)
    platform.start(on_key_event)


if __name__ == "__main__":
    main()
