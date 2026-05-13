"""Service state machine for CodeMaker.

Defines the three operational states and provides a thread-safe
state manager with transition validation and logging.
"""

import enum
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger("codemaker.state")


class ServiceState(enum.Enum):
    """The three operational modes of the service."""

    OBSERVER = "observer"
    CAPTURE = "capture"
    PLAYBACK = "playback"


# Valid state transitions
_VALID_TRANSITIONS: dict[ServiceState, set[ServiceState]] = {
    ServiceState.OBSERVER: {ServiceState.CAPTURE},
    ServiceState.CAPTURE: {ServiceState.PLAYBACK, ServiceState.OBSERVER},
    ServiceState.PLAYBACK: {ServiceState.OBSERVER},
}


class StateManager:
    """Thread-safe state machine for the service lifecycle.

    Enforces valid transitions and optionally calls a listener
    on every state change.
    """

    def __init__(
        self,
        initial: ServiceState = ServiceState.OBSERVER,
        on_change: Optional[Callable[[ServiceState, ServiceState], None]] = None,
    ):
        self._state = initial
        self._lock = threading.Lock()
        self._on_change = on_change
        logger.info("State machine initialized in %s", initial.value)

    @property
    def current(self) -> ServiceState:
        """Current state (read without lock — enum assignment is atomic in CPython)."""
        return self._state

    def transition(self, new_state: ServiceState) -> bool:
        """Attempt a state transition.

        Args:
            new_state: Target state.

        Returns:
            True if the transition was valid and performed.
            False if the transition is invalid from the current state.
        """
        with self._lock:
            old = self._state
            if new_state not in _VALID_TRANSITIONS.get(old, set()):
                logger.warning(
                    "Invalid transition: %s → %s", old.value, new_state.value
                )
                return False

            self._state = new_state
            logger.info("State transition: %s → %s", old.value, new_state.value)

            if self._on_change:
                try:
                    self._on_change(old, new_state)
                except Exception:
                    logger.exception("Error in state change callback")

            return True

    def reset(self) -> None:
        """Force-reset to OBSERVER state (for error recovery)."""
        with self._lock:
            old = self._state
            self._state = ServiceState.OBSERVER
            logger.info("State force-reset: %s → OBSERVER", old.value)
