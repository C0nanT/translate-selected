import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "pc"))
from cases import load_cases  # noqa: E402
from core import Failure, NetworkError, Translation, translate  # noqa: E402
from providers import DeepL, GoogleCloud, GoogleFree, from_env  # noqa: E402

DEEPL_CASES = load_cases("deepl_response.json")


class DeepLResponseTest(unittest.TestCase):
    def test_shared_cases(self):
        self.assertTrue(DEEPL_CASES)
        for case in DEEPL_CASES:
            with self.subTest(case=case["name"]):
                exp = case["expected"]
                r = translate("x", lambda _: case["body"], DeepL("k:fx"))
                if exp["type"] == "translation":
                    self.assertEqual(Translation(exp["text"]), r)
                else:
                    self.assertEqual(Failure(exp["reason"]), r)


class DeepLRequestTest(unittest.TestCase):
    def test_free_key_uses_free_host(self):
        req = DeepL("abc:fx").request("Hi")
        self.assertEqual("https://api-free.deepl.com/v2/translate", req.url)

    def test_pro_key_uses_pro_host(self):
        self.assertEqual("https://api.deepl.com/v2/translate", DeepL("abc").request("Hi").url)

    def test_post_json_with_key_in_header_not_url(self):
        req = DeepL("abc:fx").request('Say "hi"\né')
        self.assertIn("Authorization: DeepL-Auth-Key abc:fx", req.headers)
        self.assertIn("Content-Type: application/json", req.headers)
        self.assertNotIn("abc", req.url)
        self.assertEqual({"text": ['Say "hi"\né'], "target_lang": "PT-BR"}, json.loads(req.data))

    def test_http_errors_get_specific_messages(self):
        for code, msg in ((456, "Cota do DeepL esgotada"), (403, "Chave do DeepL inválida")):
            with self.subTest(code=code):
                def fetch(_):
                    raise NetworkError.http(code)
                self.assertEqual(Failure(msg), translate("x", fetch, DeepL("k")))

    def test_other_http_error_keeps_generic_message(self):
        def fetch(_):
            raise NetworkError.http(500)
        self.assertEqual(Failure("Erro do servidor (HTTP 500)"), translate("x", fetch, DeepL("k")))


class FromEnvTest(unittest.TestCase):
    def test_default_is_google_free(self):
        self.assertIsInstance(from_env({}), GoogleFree)
        self.assertIsInstance(from_env({"TRANSLATOR_PROVIDER": ""}), GoogleFree)

    def test_deepl_with_key(self):
        p = from_env({"TRANSLATOR_PROVIDER": "DeepL", "DEEPL_API_KEY": " k:fx "})
        self.assertIsInstance(p, DeepL)
        self.assertEqual("k:fx", p.api_key)

    def test_google_cloud_with_key(self):
        p = from_env({"TRANSLATOR_PROVIDER": "google-cloud", "GOOGLE_TRANSLATE_API_KEY": "g"})
        self.assertIsInstance(p, GoogleCloud)

    def test_missing_key_fails_instead_of_falling_back(self):
        with self.assertRaisesRegex(ValueError, "DEEPL_API_KEY"):
            from_env({"TRANSLATOR_PROVIDER": "deepl", "DEEPL_API_KEY": ""})

    def test_unknown_provider_fails(self):
        with self.assertRaisesRegex(ValueError, "TRANSLATOR_PROVIDER"):
            from_env({"TRANSLATOR_PROVIDER": "bing"})


if __name__ == "__main__":
    unittest.main()
