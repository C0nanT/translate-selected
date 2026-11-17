import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "pc"))
from core import parse_env  # noqa: E402


class ParseEnvTest(unittest.TestCase):
    def test_parse(self):
        text = ("# comment\n\nA=1\nexport B = two \nC=\"q v\"\nD='x'\nE=val # note\nF=a=b\nbad line\n")
        self.assertEqual({"A": "1", "B": "two", "C": "q v", "D": "x", "E": "val", "F": "a=b"}, parse_env(text))


if __name__ == "__main__":
    unittest.main()
