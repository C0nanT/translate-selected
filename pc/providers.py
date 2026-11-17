"""Translation providers: how to build the HTTP request and read the response.

Pure (no network). A provider has:
  name                 shown to the user ("Resposta inesperada do <name>")
  request(text)        -> Request
  parse(body)          -> translated text; raises on unexpected format
  http_errors          {status: pt-BR message} for errors worth explaining

To add a provider: write a class with those members and register it in PROVIDERS.
"""
import json
import urllib.parse
from collections import namedtuple

TARGET_LANGUAGE = "pt"

# data=None -> GET; data set -> POST with that body. headers: tuple of "Name: value".
Request = namedtuple("Request", "url headers data", defaults=((), None))


class GoogleFree:
    """Unofficial endpoint (client=gtx), no key. Copy of Translator.kt (translationUrl/extract)
    on Android, checked by cases/google_response.json and cases/validation.json."""
    name = "Google Tradutor"
    http_errors = {}

    def request(self, text):
        # Single encoding rule for q (makes Python and Java agree): RFC 3986. Only
        # A-Z a-z 0-9 - . _ ~ stay raw; space becomes +; everything else becomes %XX in UTF-8.
        # They diverged on ~ (Java: %7E) and * (Java: raw, Python: %2A); Kotlin is the one that adjusts.
        q = urllib.parse.quote_plus(text, safe="", encoding="utf-8")
        return Request("https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto"
                       f"&tl={TARGET_LANGUAGE}&dt=t&q={q}")

    def parse(self, body):
        data = json.loads(body)
        # lists only: str and dict also index in Python, but Kotlin (and the API) only accept lists
        if not isinstance(data, list) or not isinstance(data[0], list):
            raise ValueError("unexpected format")
        out = []
        for part in data[0]:
            if not isinstance(part, list):
                raise ValueError("invalid part")
            p = part[0]
            if p is not None and not isinstance(p, str):
                raise ValueError("invalid part")
            out.append(p or "")
        return "".join(out)


class GoogleCloud:
    """Official Cloud Translation v2 (Basic). format=text avoids HTML entities in the result."""
    name = "Google Tradutor"
    http_errors = {}

    def __init__(self, api_key):
        self.api_key = api_key

    def request(self, text):
        q = urllib.parse.quote_plus(text, safe="", encoding="utf-8")
        key = urllib.parse.quote_plus(self.api_key, safe="")
        return Request("https://translation.googleapis.com/language/translate/v2"
                       f"?key={key}&target={TARGET_LANGUAGE}&format=text&q={q}")

    def parse(self, body):
        data = json.loads(body)
        # {"data": {"translations": [{"translatedText": "..."}]}}
        if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
            raise ValueError("unexpected format")
        return _join(data["data"].get("translations"), "translatedText")


class DeepL:
    """DeepL API v2. Free (API Developer) keys end in ':fx' and use the api-free host.
    Key goes in a header (network.py passes headers via stdin, never argv)."""
    name = "DeepL"
    target = "PT-BR"
    http_errors = {
        403: "Chave do DeepL inválida",
        456: "Cota do DeepL esgotada",
    }

    def __init__(self, api_key):
        self.api_key = api_key

    def request(self, text):
        host = "api-free.deepl.com" if self.api_key.endswith(":fx") else "api.deepl.com"
        return Request(f"https://{host}/v2/translate",
                       headers=(f"Authorization: DeepL-Auth-Key {self.api_key}",
                                "Content-Type: application/json"),
                       data=json.dumps({"text": [text], "target_lang": self.target}))

    def parse(self, body):
        data = json.loads(body)
        # {"translations": [{"detected_source_language": "EN", "text": "..."}]}
        if not isinstance(data, dict):
            raise ValueError("unexpected format")
        return _join(data.get("translations"), "text")


def _join(items, field):
    if not isinstance(items, list) or not items:
        raise ValueError("unexpected format")
    out = []
    for item in items:
        t = item.get(field) if isinstance(item, dict) else None
        if not isinstance(t, str):
            raise ValueError("invalid part")
        out.append(t)
    return "".join(out)


# name in TRANSLATOR_PROVIDER -> (class, env var with the key or None)
PROVIDERS = {
    "google": (GoogleFree, None),
    "google-cloud": (GoogleCloud, "GOOGLE_TRANSLATE_API_KEY"),
    "deepl": (DeepL, "DEEPL_API_KEY"),
}


def from_env(env):
    """Picks the provider from TRANSLATOR_PROVIDER (default "google").
    Raises ValueError (pt-BR message) on an unknown name or a missing key: no silent fallback."""
    name = env.get("TRANSLATOR_PROVIDER", "").strip().lower() or "google"
    if name not in PROVIDERS:
        raise ValueError(f"TRANSLATOR_PROVIDER inválido: {name!r} (use: {', '.join(PROVIDERS)})")
    cls, key_var = PROVIDERS[name]
    if key_var is None:
        return cls()
    key = env.get(key_var, "").strip()
    if not key:
        raise ValueError(f"TRANSLATOR_PROVIDER={name} precisa de {key_var} no .env")
    return cls(key)
