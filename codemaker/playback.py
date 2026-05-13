"""Playback buffer and pointer-sync logic for ghost typing.

Manages the code_buffer, the virtual cursor (buffer_index), and the
negative_offset for overshot backspaces. This is the most critical
logic in the service — it determines which character gets injected
for each intercepted keystroke.
"""

import logging
from typing import Optional

logger = logging.getLogger("codemaker.playback")


class PlaybackBuffer:
    """Manages the AI-generated code buffer and ghost-typing state.

    Pointer-Sync Rules:
    ┌────────────────────────────────────────────────────┐
    │ Scenario                │ index  │ Behavior       │
    ├─────────────────────────┼────────┼────────────────┤
    │ Normal typing           │ ++     │ Inject char    │
    │ Backspace (index > 0)   │ --     │ Allow BS       │
    │ Backspace (index == 0)  │ 0      │ Block BS       │
    └────────────────────────────────────────────────────┘
    """

    def __init__(self, code: str):
        """
        Args:
            code: The AI-generated code string to ghost-type.
        """
        if not code:
            raise ValueError("Code buffer must not be empty")

        self.code = code
        self.index = 0
        logger.info(
            "PlaybackBuffer initialized: %d characters", len(code)
        )
        logger.debug("Buffer preview: %s...", code[:80])

    def next_char(self) -> Optional[str]:
        """Get the next character to inject for an intercepted keystroke.

        Called when the user presses any character key during Playback.

        Returns:
            The character to inject, or None if the buffer is exhausted.
        """
        # Buffer exhausted
        if self.index >= len(self.code):
            return None

        char = self.code[self.index]
        self.index += 1

        if self.index % 50 == 0 or self.index == len(self.code):
            logger.debug(
                "Playback progress: %d/%d (%.1f%%)",
                self.index,
                len(self.code),
                100 * self.index / len(self.code),
            )

        return char

    def backspace(self) -> bool:
        """Handle a backspace press during Playback.

        Moves the virtual cursor backward through the code buffer.
        If already at position 0, the backspace is simply blocked.

        Returns:
            True if a real backspace should be sent to the application
            (to delete the previously injected character).
            False if the backspace should be blocked (index already at 0).
        """
        if self.index > 0:
            self.index -= 1
            logger.debug("Backspace: index now %d", self.index)
            return True
        else:
            logger.debug("Backspace at start: blocked")
            return False

    @property
    def exhausted(self) -> bool:
        """Whether the entire buffer has been typed out."""
        return self.index >= len(self.code)

    @property
    def remaining(self) -> int:
        """Number of characters left to type."""
        return max(0, len(self.code) - self.index)

    @property
    def progress(self) -> float:
        """Playback progress as a fraction (0.0 to 1.0)."""
        if not self.code:
            return 1.0
        return self.index / len(self.code)
