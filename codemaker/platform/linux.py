"""Linux (Wayland/X11) keyboard hook using evdev + uinput.

Strategy:
    Physical KB ──evdev grab──► Process ──uinput──► Virtual KB ──► Compositor

Works on ALL display servers (Wayland, X11, TTY).
Requires: python-evdev >= 1.7, 'input' group or root.
"""

import atexit
import logging
import signal
import sys
from typing import Optional

import evdev
from evdev import UInput, ecodes as e, InputDevice

from .base import PlatformHook, KeyAction, KeyEventType, KeyCallback

logger = logging.getLogger("codemaker.platform.linux")

# Char → (keycode, needs_shift) for US-QWERTY
CHAR_TO_KEY: dict[str, tuple[int, bool]] = {}
for c in range(ord('a'), ord('z') + 1):
    CHAR_TO_KEY[chr(c)] = (getattr(e, f"KEY_{chr(c).upper()}"), False)
    CHAR_TO_KEY[chr(c).upper()] = (getattr(e, f"KEY_{chr(c).upper()}"), True)
for d in range(10):
    CHAR_TO_KEY[str(d)] = (getattr(e, f"KEY_{d}"), False)

_SYMBOLS = {
    '!': (e.KEY_1, True), '@': (e.KEY_2, True), '#': (e.KEY_3, True),
    '$': (e.KEY_4, True), '%': (e.KEY_5, True), '^': (e.KEY_6, True),
    '&': (e.KEY_7, True), '*': (e.KEY_8, True), '(': (e.KEY_9, True),
    ')': (e.KEY_0, True), '-': (e.KEY_MINUS, False), '=': (e.KEY_EQUAL, False),
    '_': (e.KEY_MINUS, True), '+': (e.KEY_EQUAL, True),
    '[': (e.KEY_LEFTBRACE, False), ']': (e.KEY_RIGHTBRACE, False),
    '{': (e.KEY_LEFTBRACE, True), '}': (e.KEY_RIGHTBRACE, True),
    '\\': (e.KEY_BACKSLASH, False), '|': (e.KEY_BACKSLASH, True),
    ';': (e.KEY_SEMICOLON, False), ':': (e.KEY_SEMICOLON, True),
    "'": (e.KEY_APOSTROPHE, False), '"': (e.KEY_APOSTROPHE, True),
    ',': (e.KEY_COMMA, False), '<': (e.KEY_COMMA, True),
    '.': (e.KEY_DOT, False), '>': (e.KEY_DOT, True),
    '/': (e.KEY_SLASH, False), '?': (e.KEY_SLASH, True),
    '`': (e.KEY_GRAVE, False), '~': (e.KEY_GRAVE, True),
    ' ': (e.KEY_SPACE, False), '\n': (e.KEY_ENTER, False),
    '\t': (e.KEY_TAB, False),
}
CHAR_TO_KEY.update(_SYMBOLS)

# Keycode → name for trigger detection
KEYCODE_TO_NAME: dict[int, str] = {
    e.KEY_TAB: "tab", e.KEY_BACKSPACE: "backspace", e.KEY_ENTER: "enter",
    e.KEY_SPACE: "space", e.KEY_ESC: "escape",
    e.KEY_LEFTSHIFT: "shift", e.KEY_RIGHTSHIFT: "shift",
    e.KEY_LEFTCTRL: "ctrl", e.KEY_RIGHTCTRL: "ctrl",
    e.KEY_LEFTALT: "alt", e.KEY_RIGHTALT: "alt",
    e.KEY_LEFTMETA: "meta", e.KEY_RIGHTMETA: "meta",
    e.KEY_CAPSLOCK: "capslock", e.KEY_DELETE: "delete",
    e.KEY_UP: "up", e.KEY_DOWN: "down", e.KEY_LEFT: "left", e.KEY_RIGHT: "right",
}
for c in range(ord('a'), ord('z') + 1):
    KEYCODE_TO_NAME[getattr(e, f"KEY_{chr(c).upper()}")] = chr(c)
for d in range(10):
    KEYCODE_TO_NAME[getattr(e, f"KEY_{d}")] = str(d)
for i in range(1, 13):
    KEYCODE_TO_NAME[getattr(e, f"KEY_F{i}")] = f"f{i}"


def _find_keyboard(preferred: Optional[str] = None) -> InputDevice:
    if preferred:
        dev = InputDevice(preferred)
        logger.info("Using configured keyboard: %s (%s)", dev.name, dev.path)
        return dev

    devices = [InputDevice(p) for p in evdev.list_devices()]
    candidates = []
    for dev in devices:
        caps = dev.capabilities(verbose=False).get(e.EV_KEY, [])
        has_letters = all(
            getattr(e, f"KEY_{chr(c).upper()}") in caps
            for c in range(ord('a'), ord('z') + 1)
        )
        if not has_letters:
            continue
        name = dev.name.lower()
        score = len(caps)
        if "virtual" in name or "uinput" in name:
            score -= 1000
        if "keyboard" in name:
            score += 500
        candidates.append((score, dev))

    if not candidates:
        raise RuntimeError(
            "No keyboard found. Ensure 'input' group or root.\n"
            + "\n".join(f"  {d.path}: {d.name}" for d in devices)
        )
    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0][1]
    logger.info("Auto-detected keyboard: %s (%s)", best.name, best.path)
    return best


class LinuxHook(PlatformHook):
    def __init__(self, keyboard_device_path: Optional[str] = None):
        self._device_path = keyboard_device_path
        self._device: Optional[InputDevice] = None
        self._uinput: Optional[UInput] = None
        self._callback: Optional[KeyCallback] = None
        self._running = False
        self._injecting = False
        self._held_modifiers: set[str] = set()

    def start(self, callback: KeyCallback) -> None:
        self._callback = callback
        self._device = _find_keyboard(self._device_path)
        self._device.grab()
        logger.info("Grabbed device: %s", self._device.name)
        self._uinput = UInput.from_device(self._device, name="codemaker-vkb")
        logger.info("Virtual keyboard created")
        atexit.register(self._cleanup)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        self._running = True
        try:
            self._event_loop()
        except Exception:
            logger.exception("Event loop crashed")
        finally:
            self._cleanup()

    def _event_loop(self) -> None:
        for event in self._device.read_loop():
            if not self._running:
                break
            if event.type != e.EV_KEY:
                if self._uinput:
                    self._uinput.write(event.type, event.code, event.value)
                    self._uinput.syn()
                continue
            if self._injecting:
                continue

            if event.value == 1:
                evt = KeyEventType.KEY_DOWN
            elif event.value == 0:
                evt = KeyEventType.KEY_UP
            elif event.value == 2:
                evt = KeyEventType.KEY_REPEAT
            else:
                continue

            key_name = KEYCODE_TO_NAME.get(event.code, f"unknown_{event.code}")
            self._track_modifiers(key_name, evt)
            action = self._callback(key_name, evt)

            if action == KeyAction.PASS_THROUGH:
                self._uinput.write(event.type, event.code, event.value)
                self._uinput.syn()

    def _track_modifiers(self, key: str, evt: KeyEventType) -> None:
        if key in ("ctrl", "shift", "alt", "meta", "escape"):
            if evt == KeyEventType.KEY_DOWN:
                self._held_modifiers.add(key)
            elif evt == KeyEventType.KEY_UP:
                self._held_modifiers.discard(key)

    def get_held_modifiers(self) -> frozenset[str]:
        return frozenset(self._held_modifiers)

    def inject_char(self, char: str) -> None:
        if not self._uinput:
            return
        mapping = CHAR_TO_KEY.get(char)
        if not mapping:
            logger.warning("No mapping for char: %r", char)
            return
        keycode, shift = mapping
        self._injecting = True
        try:
            if shift:
                self._uinput.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1)
                self._uinput.syn()
            self._uinput.write(e.EV_KEY, keycode, 1)
            self._uinput.syn()
            self._uinput.write(e.EV_KEY, keycode, 0)
            self._uinput.syn()
            if shift:
                self._uinput.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0)
                self._uinput.syn()
        finally:
            self._injecting = False

    def inject_backspace(self) -> None:
        if not self._uinput:
            return
        self._injecting = True
        try:
            self._uinput.write(e.EV_KEY, e.KEY_BACKSPACE, 1)
            self._uinput.syn()
            self._uinput.write(e.EV_KEY, e.KEY_BACKSPACE, 0)
            self._uinput.syn()
        finally:
            self._injecting = False

    def stop(self) -> None:
        self._running = False

    def _cleanup(self) -> None:
        if self._device:
            try:
                self._device.ungrab()
                logger.info("Ungrabbed device")
            except OSError:
                pass
            self._device = None
        if self._uinput:
            try:
                self._uinput.close()
            except OSError:
                pass
            self._uinput = None

    def _signal_handler(self, signum, frame):
        logger.info("Signal %d, shutting down", signum)
        self.stop()
        self._cleanup()
        sys.exit(0)
