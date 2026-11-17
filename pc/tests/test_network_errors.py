import os
import subprocess
import sys
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "pc"))
from cases import load_cases  # noqa: E402
from core import Failure, NetworkError, translate  # noqa: E402
import network  # noqa: E402
from providers import Request  # noqa: E402

CASES = load_cases("network_errors.json")


def failure(d):
    if d["type"] == "timeout":
        return NetworkError.timeout()
    if d["type"] == "no_connection":
        return NetworkError.no_connection()
    if d["type"] == "http":
        return NetworkError.http(d["code"])
    return NetworkError.other(d["detail"])


# the cases live in cases/network_errors.json and also apply to Android (NetworkErrorsTest.kt)
class MessagesTest(unittest.TestCase):
    def test_shared_cases(self):
        self.assertTrue(CASES)
        for case in CASES:
            with self.subTest(case=case["name"]):
                def fetch(_):
                    raise failure(case["failure"])
                self.assertEqual(Failure(case["expected"]), translate("x", fetch))

    def test_unknown_exception_becomes_other(self):
        def fetch(_):
            raise OSError("boom")
        self.assertEqual(Failure("boom"), translate("x", fetch))


def done(code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class FetchTest(unittest.TestCase):
    req = Request("http://x")

    def fetch(self, *results):
        with mock.patch("subprocess.run", side_effect=list(results)) as run, \
                mock.patch("time.sleep"):
            try:
                return network.fetch(self.req), run
            except NetworkError as e:
                return e, run

    def test_ok_returns_body(self):
        r, run = self.fetch(done(stdout='[["a"]]\n200'))
        self.assertEqual('[["a"]]', r)
        self.assertIn("--http2", run.call_args.args[0])
        self.assertNotIn("http://x", run.call_args.args[0])  # URL goes via stdin
        self.assertEqual('url = "http://x"\n', run.call_args.kwargs["input"])

    def test_headers_and_body_go_via_stdin_escaped(self):
        self.req = Request("http://x", ("Authorization: K secret",), '{"a":"q\\"b\\\\"}')
        _, run = self.fetch(done(stdout="ok\n200"))
        argv = " ".join(run.call_args.args[0])
        self.assertNotIn("secret", argv)
        self.assertEqual('url = "http://x"\n'
                         'header = "Authorization: K secret"\n'
                         'data-raw = "{\\"a\\":\\"q\\\\\\"b\\\\\\\\\\"}"\n',
                         run.call_args.kwargs["input"])

    def test_body_with_newlines(self):
        r, _ = self.fetch(done(stdout="a\nb\n200"))
        self.assertEqual("a\nb", r)

    def test_curl_errors(self):
        for result, kind in ((done(6), "no_connection"), (done(7), "no_connection"),
                             (done(28), "timeout"),
                             (subprocess.TimeoutExpired("curl", 15), "timeout")):
            with self.subTest(kind=kind):
                r, _ = self.fetch(result)
                self.assertEqual(kind, r.kind)

    def test_other_curl_error_shows_stderr(self):
        r, _ = self.fetch(done(35, stderr="curl: (35) SSL error\n"))
        self.assertEqual(("other", "curl: (35) SSL error"), (r.kind, r.detail))

    def test_missing_curl(self):
        r, _ = self.fetch(FileNotFoundError())
        self.assertEqual("other", r.kind)

    def test_non_200_becomes_http(self):
        r, run = self.fetch(done(stdout="x\n404"))
        self.assertEqual(("http", 404), (r.kind, r.code))
        self.assertEqual(1, run.call_count)

    def test_retries_429_then_succeeds(self):
        r, run = self.fetch(done(stdout="\n429"), done(stdout="ok\n200"))
        self.assertEqual("ok", r)
        self.assertEqual(2, run.call_count)

    def test_429_gives_up_after_retries(self):
        r, run = self.fetch(*[done(stdout="\n429")] * 3)
        self.assertEqual(("http", 429), (r.kind, r.code))
        self.assertEqual(3, run.call_count)


if __name__ == "__main__":
    unittest.main()
