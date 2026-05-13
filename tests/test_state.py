"""Unit tests for StateManager."""

import pytest
from codemaker.state import ServiceState, StateManager


class TestStateManager:
    def test_initial_state(self):
        sm = StateManager()
        assert sm.current == ServiceState.OBSERVER

    def test_valid_transitions(self):
        sm = StateManager()
        assert sm.transition(ServiceState.CAPTURE) is True
        assert sm.current == ServiceState.CAPTURE
        assert sm.transition(ServiceState.PLAYBACK) is True
        assert sm.current == ServiceState.PLAYBACK
        assert sm.transition(ServiceState.OBSERVER) is True
        assert sm.current == ServiceState.OBSERVER

    def test_invalid_transition(self):
        sm = StateManager()
        assert sm.transition(ServiceState.PLAYBACK) is False
        assert sm.current == ServiceState.OBSERVER

    def test_capture_to_observer(self):
        sm = StateManager()
        sm.transition(ServiceState.CAPTURE)
        assert sm.transition(ServiceState.OBSERVER) is True

    def test_reset(self):
        sm = StateManager()
        sm.transition(ServiceState.CAPTURE)
        sm.transition(ServiceState.PLAYBACK)
        sm.reset()
        assert sm.current == ServiceState.OBSERVER

    def test_callback_on_change(self):
        changes = []
        sm = StateManager(on_change=lambda o, n: changes.append((o, n)))
        sm.transition(ServiceState.CAPTURE)
        sm.transition(ServiceState.PLAYBACK)
        assert len(changes) == 2
        assert changes[0] == (ServiceState.OBSERVER, ServiceState.CAPTURE)
        assert changes[1] == (ServiceState.CAPTURE, ServiceState.PLAYBACK)

    def test_no_callback_on_invalid(self):
        changes = []
        sm = StateManager(on_change=lambda o, n: changes.append((o, n)))
        sm.transition(ServiceState.PLAYBACK)  # invalid
        assert len(changes) == 0
