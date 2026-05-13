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

    def test_backspace_at_zero(self):
        buf = PlaybackBuffer("abc")
        assert buf.backspace() is False
        assert buf.negative_offset == 1

    def test_negative_offset_swallows(self):
        buf = PlaybackBuffer("abc")
        # Hit backspace 3 times at position 0
        buf.backspace()
        buf.backspace()
        buf.backspace()
        assert buf.negative_offset == 3

        # Now type — first 3 keystrokes are swallowed
        assert buf.next_char() is None
        assert buf.next_char() is None
        assert buf.next_char() is None
        # Now normal typing resumes
        assert buf.next_char() == "a"
        assert buf.next_char() == "b"

    def test_mixed_backspace_and_typing(self):
        buf = PlaybackBuffer("abcd")
        assert buf.next_char() == "a"  # index=1
        assert buf.next_char() == "b"  # index=2
        assert buf.backspace() is True  # index=1
        assert buf.backspace() is True  # index=0
        assert buf.backspace() is False  # negative_offset=1
        assert buf.next_char() is None   # swallow, neg=0
        assert buf.next_char() == "a"    # index=1
        assert buf.next_char() == "b"    # index=2
        assert buf.next_char() == "c"    # index=3
        assert buf.next_char() == "d"    # index=4
        assert buf.exhausted is True

    def test_exhausted_with_negative_offset(self):
        buf = PlaybackBuffer("a")
        buf.next_char()  # exhausts buffer
        assert buf.exhausted is True

    def test_not_exhausted_during_negative_offset(self):
        buf = PlaybackBuffer("a")
        buf.backspace()  # neg_offset=1
        assert buf.exhausted is False

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

    def test_heavy_backspace_then_retype(self):
        """Simulate user hitting backspace 10 times at start."""
        buf = PlaybackBuffer("xy")
        for _ in range(10):
            assert buf.backspace() is False
        assert buf.negative_offset == 10

        # Type 10 keys — all swallowed
        for _ in range(10):
            assert buf.next_char() is None

        # Now normal
        assert buf.next_char() == "x"
        assert buf.next_char() == "y"
        assert buf.exhausted is True
