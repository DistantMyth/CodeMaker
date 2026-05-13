"""Abstract base class for platform-specific keyboard hooks.

Each platform implementation must handle:
1. Installing a global keyboard hook
2. Intercepting key events and routing them through a callback
3. Injecting synthetic characters/keys into the active window
4. Clean shutdown with hook removal
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable, Optional


class KeyAction(Enum):
    """What the hook should do with a key event after the callback."""

    PASS_THROUGH = "pass_through"  # Let the original key go through
    BLOCK = "block"                # Suppress the original key


class KeyEventType(Enum):
    """Type of key event."""

    KEY_DOWN = "key_down"
    KEY_UP = "key_up"
    KEY_REPEAT = "key_repeat"


# Callback signature: (key_name: str, event_type: KeyEventType) -> KeyAction
KeyCallback = Callable[[str, KeyEventType], KeyAction]


class PlatformHook(ABC):
    """Abstract interface for platform keyboard hooks.

    Implementations must guarantee:
    - The hook is properly cleaned up on exit (even on crash)
    - inject_char/inject_backspace do NOT trigger the hook callback
      (no infinite loop)
    - The callback is invoked from a consistent thread context
    """

    @abstractmethod
    def start(self, callback: KeyCallback) -> None:
        """Install the global keyboard hook and begin processing events.

        This method may block (e.g., running a message loop).
        The callback will be invoked for each key event.

        Args:
            callback: Function called for every key event. Its return
                      value determines whether the key is passed through
                      or blocked.
        """
        ...

    @abstractmethod
    def inject_char(self, char: str) -> None:
        """Inject a single character into the active window.

        Must handle shift/modifier keys as needed for the character.
        Must not trigger the hook callback (to avoid infinite loops).

        Args:
            char: A single character to type (e.g., 'a', '{', '\\n').
        """
        ...

    @abstractmethod
    def inject_backspace(self) -> None:
        """Inject a single backspace keystroke into the active window.

        Used when the user backspaces during playback and we need to
        delete a previously injected character.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Remove the keyboard hook and clean up resources.

        Must be safe to call multiple times.
        Must restore normal keyboard operation.
        """
        ...
