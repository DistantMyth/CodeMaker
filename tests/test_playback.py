"""Unit tests for PlaybackBuffer."""

import pytest
from codemaker.playback import PlaybackBuffer


class TestPlaybackBuffer:
    def test_sequential_typing(self):
        buf = PlaybackBuffer("abc")
        assert buf.next_char() == "a"
        assert buf.next_char() == "b"
        assert buf.next_char() == "c"
        assert buf.next_char() is None
        assert buf.exhausted is True

    def test_backspace_decrements_index(self):
        buf = PlaybackBuffer("hello")
        buf.next_char()  # h, index=1
        buf.next_char()  # e, index=2
        assert buf.backspace() is True  # index=1
        assert buf.next_char() == "e"   # index=2 again

    def test_backspace_at_zero_blocks(self):
        buf = PlaybackBuffer("abc")
        assert buf.backspace() is False  # blocked, nothing tracked

    def test_backspace_at_zero_then_type_resumes_from_start(self):
        """Backspace at 0 is just blocked. Next keypress resumes from index 0."""
        buf = PlaybackBuffer("abc")
        # Mash backspace at position 0
        buf.backspace()
        buf.backspace()
        buf.backspace()
        # Typing should still start from the beginning
        assert buf.next_char() == "a"
        assert buf.next_char() == "b"
        assert buf.next_char() == "c"
        assert buf.exhausted is True

    def test_mixed_backspace_and_typing(self):
        buf = PlaybackBuffer("abcd")
        assert buf.next_char() == "a"  # index=1
        assert buf.next_char() == "b"  # index=2
        assert buf.backspace() is True  # index=1
        assert buf.backspace() is True  # index=0
        assert buf.backspace() is False  # blocked at 0
        # Resume from beginning
        assert buf.next_char() == "a"    # index=1
        assert buf.next_char() == "b"    # index=2
        assert buf.next_char() == "c"    # index=3
        assert buf.next_char() == "d"    # index=4
        assert buf.exhausted is True

    def test_exhausted(self):
        buf = PlaybackBuffer("a")
        buf.next_char()
        assert buf.exhausted is True

    def test_empty_code_raises(self):
        with pytest.raises(ValueError):
            PlaybackBuffer("")

    def test_progress(self):
        buf = PlaybackBuffer("abcd")
        assert buf.progress == 0.0
        buf.next_char()
        assert buf.progress == 0.25
        buf.next_char()
        buf.next_char()
        buf.next_char()
        assert buf.progress == 1.0

    def test_remaining(self):
        buf = PlaybackBuffer("abc")
        assert buf.remaining == 3
        buf.next_char()
        assert buf.remaining == 2
        buf.backspace()
        assert buf.remaining == 3

    def test_special_chars(self):
        code = '#include <stdio.h>\n{\n\treturn 0;\n}'
        buf = PlaybackBuffer(code)
        result = []
        while not buf.exhausted:
            c = buf.next_char()
            if c is not None:
                result.append(c)
        assert "".join(result) == code
