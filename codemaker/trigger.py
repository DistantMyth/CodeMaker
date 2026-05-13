"""Sliding-window trigger sequence detector.

Maintains a fixed-size buffer of recent key names and checks for
an exact match against the configured trigger sequence.
Pure logic — no platform dependencies.
"""

import collections
import logging
from typing import Sequence

logger = logging.getLogger("codemaker.trigger")


class TriggerDetector:
    """Detects a specific key sequence using a sliding window.

    The window size equals the length of the trigger sequence.
    Each call to `feed()` appends a key and checks for a match.
    """

    def __init__(self, sequence: Sequence[str]):
        """
        Args:
            sequence: Ordered list of key names (lowercase) that
                      constitute the trigger. e.g. ['tab', 'tab', 'tab',
                      'backspace', 'backspace', 'backspace']
        """
        if not sequence:
            raise ValueError("Trigger sequence must not be empty")

        self._sequence = list(sequence)
        self._buffer: collections.deque[str] = collections.deque(
            maxlen=len(sequence)
        )
        logger.debug("TriggerDetector initialized: %s", self._sequence)

    def feed(self, key_name: str) -> bool:
        """Feed a key event into the detector.

        Args:
            key_name: Lowercase name of the key pressed
                      (e.g. 'tab', 'backspace', 'a').

        Returns:
            True if the sliding window now matches the trigger sequence.
        """
        self._buffer.append(key_name.lower())

        if len(self._buffer) == len(self._sequence):
            if list(self._buffer) == self._sequence:
                logger.info("Trigger sequence matched!")
                self._buffer.clear()
                return True

        return False

    def reset(self) -> None:
        """Clear the sliding window buffer."""
        self._buffer.clear()

    @property
    def window_size(self) -> int:
        """Length of the trigger sequence."""
        return len(self._sequence)

    @property
    def current_buffer(self) -> list[str]:
        """Current contents of the sliding window (for debugging)."""
        return list(self._buffer)
