"""Unit tests for TriggerDetector."""

import pytest
from codemaker.trigger import TriggerDetector


class TestTriggerDetector:
    def test_exact_match(self):
        td = TriggerDetector(["tab", "tab", "tab"])
        assert td.feed("tab") is False
        assert td.feed("tab") is False
        assert td.feed("tab") is True

    def test_no_match(self):
        td = TriggerDetector(["tab", "tab", "tab"])
        assert td.feed("tab") is False
        assert td.feed("tab") is False
        assert td.feed("a") is False

    def test_default_sequence(self):
        seq = ["tab", "tab", "tab", "backspace", "backspace", "backspace"]
        td = TriggerDetector(seq)
        for key in ["tab", "tab", "tab", "backspace", "backspace"]:
            assert td.feed(key) is False
        assert td.feed("backspace") is True

    def test_sliding_window(self):
        td = TriggerDetector(["a", "b", "c"])
        td.feed("x")
        td.feed("a")
        td.feed("b")
        assert td.feed("c") is True

    def test_case_insensitive(self):
        td = TriggerDetector(["tab", "tab"])
        td.feed("TAB")
        assert td.feed("Tab") is True

    def test_clears_after_match(self):
        td = TriggerDetector(["a", "a"])
        assert td.feed("a") is False
        assert td.feed("a") is True
        # Buffer should be cleared after match
        assert td.feed("a") is False
        assert td.feed("a") is True

    def test_reset(self):
        td = TriggerDetector(["a", "b"])
        td.feed("a")
        td.reset()
        assert td.feed("b") is False
        td.feed("a")
        assert td.feed("b") is True

    def test_empty_sequence_raises(self):
        with pytest.raises(ValueError):
            TriggerDetector([])

    def test_single_key_trigger(self):
        td = TriggerDetector(["escape"])
        assert td.feed("escape") is True
        assert td.feed("a") is False
        assert td.feed("escape") is True

    def test_window_size(self):
        td = TriggerDetector(["a", "b", "c"])
        assert td.window_size == 3

    def test_overlapping_partial_match(self):
        td = TriggerDetector(["a", "a", "b"])
        td.feed("a")  # [a]
        td.feed("a")  # [a, a]
        td.feed("a")  # [a, a, a] - no match (all a's)
        # Deque becomes [a, a, b] which DOES match the trigger
        assert td.feed("b") is True

    def test_overlapping_sequence_matches(self):
        td = TriggerDetector(["a", "a", "b"])
        td.feed("a")
        td.feed("a")
        td.feed("a")
        # Deque is now [a, a, a] — no match
        # Feed 'b' → deque becomes [a, a, b] — match!
        assert td.feed("b") is True
