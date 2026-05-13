"""Windows keyboard hook using WH_KEYBOARD_LL + SendInput.

Uses ctypes to interface with User32.dll for low-level keyboard
interception and synthetic keystroke injection.

Requirements: Windows 10/11, admin privileges recommended.
"""

import atexit
import ctypes
import ctypes.wintypes as wt
import logging
import sys
import threading
from typing import Optional

from .base import PlatformHook, KeyAction, KeyEventType, KeyCallback

logger = logging.getLogger("codemaker.platform.windows")

if sys.platform != "win32":
    # Stub so imports don't crash on Linux
    class WindowsHook(PlatformHook):
        def start(self, cb): raise NotImplementedError("Windows only")
        def inject_char(self, c): raise NotImplementedError
        def inject_backspace(self): raise NotImplementedError
        def stop(self): pass
else:
    import ctypes.wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # Constants
    WH_KEYBOARD_LL = 13
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1

    # Virtual key codes
    VK_BACK = 0x08
    VK_TAB = 0x09
    VK_RETURN = 0x0D
    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_MENU = 0x12  # Alt
    VK_ESCAPE = 0x1B
    VK_SPACE = 0x20
    VK_DELETE = 0x2E
    VK_LSHIFT = 0xA0
    VK_RSHIFT = 0xA1
    VK_LCONTROL = 0xA2
    VK_RCONTROL = 0xA3
    VK_LMENU = 0xA4
    VK_RMENU = 0xA5
    VK_LWIN = 0x5B
    VK_RWIN = 0x5C

    # VK → key name mapping
    VK_TO_NAME: dict[int, str] = {
        VK_TAB: "tab", VK_BACK: "backspace", VK_RETURN: "enter",
        VK_SPACE: "space", VK_ESCAPE: "escape", VK_DELETE: "delete",
        VK_SHIFT: "shift", VK_LSHIFT: "shift", VK_RSHIFT: "shift",
        VK_CONTROL: "ctrl", VK_LCONTROL: "ctrl", VK_RCONTROL: "ctrl",
        VK_MENU: "alt", VK_LMENU: "alt", VK_RMENU: "alt",
        VK_LWIN: "meta", VK_RWIN: "meta",
    }
    # Letters A-Z (VK 0x41-0x5A)
    for c in range(ord('A'), ord('Z') + 1):
        VK_TO_NAME[c] = chr(c).lower()
    # Digits 0-9 (VK 0x30-0x39)
    for d in range(10):
        VK_TO_NAME[0x30 + d] = str(d)
    # F-keys
    for i in range(1, 13):
        VK_TO_NAME[0x70 + i - 1] = f"f{i}"

    # Structs
    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wt.DWORD),
            ("scanCode", wt.DWORD),
            ("flags", wt.DWORD),
            ("time", wt.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wt.WORD),
            ("wScan", wt.WORD),
            ("dwFlags", wt.DWORD),
            ("time", wt.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wt.DWORD),
            ("union", INPUT_UNION),
        ]

    HOOKPROC = ctypes.CFUNCTYPE(
        ctypes.c_long, ctypes.c_int, wt.WPARAM, wt.LPARAM
    )

    # Marker to identify our own injected events
    _INJECTED_EXTRA = 0xDEAD_CAFE

    class WindowsHook(PlatformHook):
        def __init__(self):
            self._hook = None
            self._callback: Optional[KeyCallback] = None
            self._hook_proc = None  # prevent GC
            self._held_modifiers: set[str] = set()

        def start(self, callback: KeyCallback) -> None:
            self._callback = callback

            # Must keep reference to prevent garbage collection
            self._hook_proc = HOOKPROC(self._low_level_handler)
            self._hook = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL,
                self._hook_proc,
                kernel32.GetModuleHandleW(None),
                0,
            )
            if not self._hook:
                raise RuntimeError(
                    f"SetWindowsHookExW failed: {ctypes.GetLastError()}"
                )

            logger.info("WH_KEYBOARD_LL hook installed")
            atexit.register(self._cleanup)

            # Run the message pump (blocks)
            msg = wt.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        def _low_level_handler(
            self, nCode: int, wParam: int, lParam: int
        ) -> int:
            if nCode < 0:
                return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

            kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents

            # Skip our own injected events
            extra_val = 0
            if kb.dwExtraInfo:
                try:
                    extra_val = kb.dwExtraInfo.contents.value
                except (ValueError, ctypes.ArgumentError):
                    pass
            if extra_val == _INJECTED_EXTRA:
                return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

            # Map event type
            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                evt = KeyEventType.KEY_DOWN
            elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                evt = KeyEventType.KEY_UP
            else:
                return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

            key_name = VK_TO_NAME.get(kb.vkCode, f"unknown_{kb.vkCode}")
            self._track_modifiers(key_name, evt)

            action = self._callback(key_name, evt)

            if action == KeyAction.BLOCK:
                return 1  # Suppress the key
            return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

        def _track_modifiers(self, key: str, evt: KeyEventType):
            if key in ("ctrl", "shift", "alt", "meta", "escape"):
                if evt == KeyEventType.KEY_DOWN:
                    self._held_modifiers.add(key)
                elif evt == KeyEventType.KEY_UP:
                    self._held_modifiers.discard(key)

        def get_held_modifiers(self) -> frozenset[str]:
            return frozenset(self._held_modifiers)

        def inject_char(self, char: str) -> None:
            """Inject a Unicode character using SendInput."""
            code = ord(char)
            extra = ctypes.pointer(ctypes.c_ulong(_INJECTED_EXTRA))

            # Key down
            inp_down = INPUT()
            inp_down.type = INPUT_KEYBOARD
            inp_down.union.ki.wVk = 0
            inp_down.union.ki.wScan = code
            inp_down.union.ki.dwFlags = KEYEVENTF_UNICODE
            inp_down.union.ki.dwExtraInfo = extra

            # Key up
            inp_up = INPUT()
            inp_up.type = INPUT_KEYBOARD
            inp_up.union.ki.wVk = 0
            inp_up.union.ki.wScan = code
            inp_up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
            inp_up.union.ki.dwExtraInfo = extra

            arr = (INPUT * 2)(inp_down, inp_up)
            user32.SendInput(2, arr, ctypes.sizeof(INPUT))

        def inject_backspace(self) -> None:
            extra = ctypes.pointer(ctypes.c_ulong(_INJECTED_EXTRA))
            inp_down = INPUT()
            inp_down.type = INPUT_KEYBOARD
            inp_down.union.ki.wVk = VK_BACK
            inp_down.union.ki.dwExtraInfo = extra

            inp_up = INPUT()
            inp_up.type = INPUT_KEYBOARD
            inp_up.union.ki.wVk = VK_BACK
            inp_up.union.ki.dwFlags = KEYEVENTF_KEYUP
            inp_up.union.ki.dwExtraInfo = extra

            arr = (INPUT * 2)(inp_down, inp_up)
            user32.SendInput(2, arr, ctypes.sizeof(INPUT))

        def stop(self) -> None:
            self._cleanup()
            user32.PostQuitMessage(0)

        def _cleanup(self) -> None:
            if self._hook:
                user32.UnhookWindowsHookEx(self._hook)
                logger.info("Hook removed")
                self._hook = None
