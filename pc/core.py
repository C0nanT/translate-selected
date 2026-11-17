"""Core: pure rules, no GTK and no network."""
import logging
import re
from collections import namedtuple

from providers import GoogleFree

log = logging.getLogger("translator")

MAX_CHARS = 3000
# cap on the already-encoded URL; equal to MAX_URL in Limits.kt (conservative value, not measured)
MAX_URL = 8000


# Copy of joinLines in android/core/src/main/kotlin/com/conan/translator/Translator.kt: keep both equal,
# checked by the shared cases in cases/join_lines.json.
# Text copied from a PDF has \n at every line end (and a hyphen in split words);
# joins the lines, a blank line still separates paragraphs.
def join_lines(text):
    def hyphen(m):  # dis-|tributed drops the hyphen; Monolith-|To keeps it
        return "" if m.group(1).islower() else "-"

    paragraphs = re.split(r"\n[ \t]*\n\s*", text.replace("\r\n", "\n"))
    out = []
    for par in paragraphs:
        par = re.sub(r"-[ \t]*\n[ \t]*(?=(.?))", hyphen, par)
        par = re.sub(r"[ \t]*\n[ \t]*", " ", par)
        par = re.sub(r"[ \t]{2,}", " ", par)
        out.append(par.strip())
    return "\n\n".join(out)


# Copy of Stopwatch.kt: time left on the popup. No clock: the "now" (ms)
# comes in on each call. States: idle (loading), running, paused (mouse over).
class Stopwatch:
    def __init__(self, total_ms):
        self.total_ms = total_ms
        self.remaining_ms = total_ms
        self.started = False
        self._paused = False
        self._last = 0

    @property
    def finished(self):
        return self.started and self.remaining_ms <= 0

    @property
    def fraction(self):
        return min(1.0, max(0.0, self.remaining_ms / self.total_ms))

    def start(self, now):
        # full time; if paused, it only runs on resume
        self.remaining_ms = self.total_ms
        self.started = True
        self._last = now

    def stop(self):
        # back to "loading"; the pause still applies
        self.remaining_ms = self.total_ms
        self.started = False

    def pause(self, now):
        self.elapse(now)
        self._paused = True

    def resume(self, now):
        if not self._paused:
            return
        self._paused = False
        self._last = now

    def elapse(self, now):
        if self.started and not self._paused:
            self.remaining_ms = max(0, self.remaining_ms - (now - self._last))
            self._last = now
        return self.remaining_ms


Size = namedtuple("Size", "width height")
Position = namedtuple("Position", "x y")


def _limit(v, lo, hi):
    return max(lo, min(v, hi))


# Copy of clampPosition in Position.kt: keeps the window inside the screen.
# centered_x=False: x is the distance from the left edge; True: offset from the center.
# y goes from 0 to (screen - window).
def clamp_position(pos, screen, window, centered_x):
    slack_x = max(0, screen.width - window.width)
    if centered_x:
        x = _limit(pos.x, -(slack_x // 2), slack_x // 2)
    else:
        x = _limit(pos.x, 0, slack_x)
    y = _limit(pos.y, 0, max(0, screen.height - window.height))
    return Position(x, y)


# --- translate: validation + provider request/response, with the HTTP fetch coming from outside ---
# Copy of Translator.kt (translate), checked by cases/validation.json; providers live in providers.py.
class _Marker:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


Empty = _Marker("Empty")
NoLetters = _Marker("NoLetters")
Translation = namedtuple("Translation", "text")
Failure = namedtuple("Failure", "reason")


class TooLarge(namedtuple("TooLarge", "n")):
    @property
    def message(self):
        return f"Texto grande demais ({self.n} caracteres)"


# Contract between the network adapter and the core (equal to NetworkError in Translator.kt):
# fetch raises NetworkError; the adapter converts platform exceptions (see network.py).
# kind: "timeout", "no_connection", "http" (+ code) or "other" (+ detail).
class NetworkError(Exception):
    def __init__(self, kind, code=None, detail=None):
        super().__init__(*(a for a in (kind, code, detail) if a is not None))
        self.kind = kind
        self.code = code
        self.detail = detail

    @classmethod
    def timeout(cls):
        return cls("timeout")

    @classmethod
    def no_connection(cls):
        return cls("no_connection")

    @classmethod
    def http(cls, code):
        return cls("http", code=code)

    @classmethod
    def other(cls, detail):
        return cls("other", detail=detail)

    @property
    def message(self):  # the only place for network error messages (user-facing, pt-BR)
        if self.kind == "timeout":
            return "Tempo esgotado"
        if self.kind == "no_connection":
            return "Sem conexão com a internet"
        if self.kind == "http":
            return f"Erro do servidor (HTTP {self.code})"
        return self.detail


def parse_env(text):
    """Parses .env content: KEY=value lines, # comments, optional quotes and `export `."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        elif " #" in v:
            v = v.split(" #", 1)[0].rstrip()
        out[k.strip()] = v
    return out


def validate(text):
    """Empty, NoLetters, TooLarge(n) or None if the text (lines already joined) is fine."""
    if not text.strip():
        return Empty
    if not any(c.isalpha() for c in text):
        return NoLetters
    if len(text) > MAX_CHARS:  # str counts code points: an emoji is 1
        return TooLarge(len(text))
    return None


def _reason(e):
    if isinstance(e, NetworkError):
        return e.message
    return str(e) or type(e).__name__  # exception outside the contract: treated as "other"


def translate(raw, fetch, provider=GoogleFree()):
    """fetch(request) -> body (str); raises an exception on network failure (NetworkError).
    provider (see providers.py) builds the request and reads the response."""
    text = join_lines(raw)
    invalid = validate(text)
    if invalid is not None:
        return invalid
    req = provider.request(text)
    if len(req.url) > MAX_URL:
        return TooLarge(len(text))  # n is <= MAX_CHARS: counts characters, not the URL
    try:
        body = fetch(req)
    except Exception as e:
        # never log req itself: it may carry the API key (URL or header)
        log.error("fetch failed (%s, %d chars, url %d chars): %r",
                  provider.name, len(text), len(req.url), e, exc_info=True)
        if isinstance(e, NetworkError) and e.kind == "http" and e.code in provider.http_errors:
            return Failure(provider.http_errors[e.code])
        return Failure(_reason(e))
    try:
        return Translation(provider.parse(body))
    except Exception:
        log.error("unexpected response (%d bytes), body starts: %r", len(body), body[:500], exc_info=True)
        return Failure(f"Resposta inesperada do {provider.name}")
