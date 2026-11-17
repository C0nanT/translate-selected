import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "pc"))
from cases import load_cases  # noqa: E402
from core import Failure, Translation, translate  # noqa: E402
from providers import GoogleCloud  # noqa: E402

CASES = load_cases("cloud_response.json")


# official Cloud Translation v2 responses (PC only)
class CloudResponseTest(unittest.TestCase):
    def test_shared_cases(self):
        self.assertTrue(CASES)
        for case in CASES:
            with self.subTest(case=case["name"]):
                exp = case["expected"]
                r = translate("x", lambda _: case["body"], GoogleCloud("k"))
                if exp["type"] == "translation":
                    self.assertEqual(Translation(exp["text"]), r)
                else:
                    self.assertEqual(Failure(exp["reason"]), r)


if __name__ == "__main__":
    unittest.main()
