"""Network: HTTP via the system curl (adapter).

translate.googleapis.com (client=gtx) answers 429 to HTTP/1.1 and Python's urllib
only speaks HTTP/1.1; curl speaks HTTP/2 with no extra Python dependency.
"""
import subprocess
import time

from core import NetworkError

TIMEOUT_S = 10
_RETRY_CODES = {429, 503}
_RETRIES = 2
# curl exit codes: https://curl.se/libcurl/c/libcurl-errors.html
_NO_CONNECTION = {6, 7}  # couldn't resolve host, couldn't connect
_TIMEOUT = 28


def _quote(s):
    """Quoted value for a curl config file: backslash first, then the escapes curl reads."""
    for a, b in (("\\", "\\\\"), ('"', '\\"'), ("\n", "\\n"), ("\r", "\\r"), ("\t", "\\t")):
        s = s.replace(a, b)
    return f'"{s}"'


def _config(req):
    lines = [f"url = {_quote(req.url)}"]
    lines += [f"header = {_quote(h)}" for h in req.headers]
    if req.data is not None:
        lines.append(f"data-raw = {_quote(req.data)}")  # data-raw: a leading @ is not a filename
    return "".join(line + "\n" for line in lines)


def _curl(req):
    """Returns (status, body). URL, headers and body go via stdin config, not argv
    (keeps the API key out of ps)."""
    cmd = ["curl", "--silent", "--show-error", "--http2", "--max-time", str(TIMEOUT_S),
           "--user-agent", "Mozilla/5.0", "--write-out", "\n%{http_code}", "--config", "-"]
    try:
        p = subprocess.run(cmd, input=_config(req), capture_output=True,
                           text=True, encoding="utf-8", timeout=TIMEOUT_S + 5)
    except FileNotFoundError:
        raise NetworkError.other("curl não encontrado (sudo apt install curl)")
    except subprocess.TimeoutExpired:
        raise NetworkError.timeout()
    if p.returncode in _NO_CONNECTION:
        raise NetworkError.no_connection()
    if p.returncode == _TIMEOUT:
        raise NetworkError.timeout()
    if p.returncode != 0:
        raise NetworkError.other(p.stderr.strip() or f"curl exit {p.returncode}")
    body, _, status = p.stdout.rpartition("\n")
    return int(status), body


def fetch(req):
    """Send the providers.Request (GET, or POST when req.data is set) and return the body;
    any failure becomes NetworkError.
    Retries on 429/503 with backoff (1s, 2s)."""
    for attempt in range(_RETRIES + 1):
        status, body = _curl(req)
        if status == 200:
            return body
        if status in _RETRY_CODES and attempt < _RETRIES:
            time.sleep(2 ** attempt)
            continue
        raise NetworkError.http(status)
