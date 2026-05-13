"""Tests for utility functions."""

from codemaker.utils import strip_code_fences


class TestStripCodeFences:
    def test_c_fence(self):
        raw = '```c\nint main() { return 0; }\n```'
        assert strip_code_fences(raw) == 'int main() { return 0; }'

    def test_no_language(self):
        raw = '```\nprint("hello")\n```'
        assert strip_code_fences(raw) == 'print("hello")'

    def test_no_fences(self):
        raw = 'int main() { return 0; }'
        assert strip_code_fences(raw) == raw

    def test_whitespace(self):
        raw = '  ```c\ncode\n```  '
        assert strip_code_fences(raw) == 'code'

    def test_multiple_fences(self):
        # Only strips outermost fences
        raw = '```c\n```inner```\n```'
        result = strip_code_fences(raw)
        assert '```inner```' in result
