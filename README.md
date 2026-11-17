# translate-selected

Select text in any app (PDF reader, browser, etc.) and see the pt-BR translation in a fixed popup at the bottom of the screen, without copy and paste.

Made for reading English books and only checking the translation when you get stuck on a sentence.

**Android (tablet, Kotlin):** https://github.com/C0nanT/translate-selected-android

## Requirements

- Linux with an **X11** session (does not work on Wayland)
- Python 3 + GTK 3 (`python3-gi`), already included in Ubuntu/GNOME
- `curl` with HTTP/2 (default on Ubuntu; check with `curl --version | grep HTTP2`)
- Internet access (free Google Translate endpoint by default; see [Translation provider](#translation-provider))

## Usage

```bash
make start    # runs attached to the terminal
```

Ctrl+C or closing the terminal stops it.

Or directly: `python3 pc/translator.py`.

Tests: `make test`. To have `git push` run the tests before sending, enable the hook once per clone with `make hooks`; `git push --no-verify` skips the check.

- Select the text -> "Traduzindo…" appears, then the translation
- Click anywhere -> the popup closes
- Hold and drag the popup to move it; the next ones open there (saved in `~/.config/translate-selected.json`; delete the file to go back to the default)
- If the request fails, the popup turns red with the reason

While it is running, **any** selected text is sent to the translation provider.

## Translation provider

Chosen by `TRANSLATOR_PROVIDER` in `.env` at the project root (git-ignored; a variable exported in the shell takes precedence):

```bash
cp .env.example .env   # then fill it in
```

| `TRANSLATOR_PROVIDER` | Key variable | Notes |
|---|---|---|
| `google` (default) | none | free, unofficial endpoint (`client=gtx`). No account, but rate-limited by IP (HTTP 429) and Google can block it at any time |
| `deepl` | `DEEPL_API_KEY` | DeepL API v2. The free plan (API Developer) gives **1,000,000 characters in total, not monthly**; then HTTP 456 ("Cota do DeepL esgotada") until you upgrade. Free keys end in `:fx` and use `api-free.deepl.com`; other keys use `api.deepl.com` |
| `google-cloud` | `GOOGLE_TRANSLATE_API_KEY` | official Cloud Translation v2 (Basic). Needs billing (card; some accounts are asked for a prepayment). 500k characters/month free, then per million characters |

If the selected provider needs a key and it is empty, the app refuses to start; it never falls back to another provider silently. The active provider is shown on startup.

The free Google endpoint answers HTTP 429 to HTTP/1.1 clients (such as Python's `urllib`), which is why requests go through `curl` with HTTP/2 (`pc/network.py`). URL, headers and body go to curl via stdin, so keys never show up in `ps`.

**Adding a provider:** write a class in `pc/providers.py` with `name`, `request(text)`, `parse(body)` and `http_errors`, and register it in `PROVIDERS`. Add a `cases/<provider>_response.json` with response cases.

## Configuration

Constants at the top of `pc/popup.py` (`HIDE_AFTER_S`, `POPUP_CHARS`, `CLICK_HIDE_MS`, `MARGIN`), `pc/core.py` (`MAX_CHARS`) and `pc/selection.py` (`POLL_MS`):

| Constant | Default | What it does |
|---|---|---|
| `POLL_MS` | 30 | while the mouse button is down, checks every so often whether it has been released (only then translates) |
| `HIDE_AFTER_S` | 15 | the popup hides by itself after this time |
| `MAX_CHARS` | 3000 | ignores selections larger than this |
| `POPUP_CHARS` | 80 | maximum popup width, in characters |
| `CLICK_HIDE_MS` | 0 | delay before closing after a click |
| `MARGIN` | 8 | distance from the popup to the screen edge |

## Development

- **Core**: pure rules, no UI and no network: `pc/core.py` (validation, translate) and `pc/providers.py` (request/response of each translation service).
- **Adapters**: what is specific to the platform: `pc/selection.py` (X11 selection), `pc/popup.py` (GTK window), `pc/network.py` (HTTP) and `pc/translator.py` (wires everything together).
- **`cases/`**: JSON files with input -> expected output, read by the tests. They are the single source of truth for behavior.

**Rule: when behavior changes, change the case first.** Write or adjust the case in `cases/` and only then the code. The stopwatch and position clamping do not use `cases/`: they have direct tests.

**`cases/` is duplicated in the [Android repo](https://github.com/C0nanT/translate-selected-android)**, whose Kotlin core follows the same rules. When a case changes here, copy the change there too (and vice versa), or the two versions drift apart.

| Command | What it does |
|---|---|
| `make test` | unit tests (no GTK/network) |
| `make hooks` | enables the pre-push hook versioned in `hooks/`, which runs `make test` before each `git push`. Run once per clone; repeating it is safe |

**Why two languages:** unifying (Kotlin on both sides, or another language) was evaluated and postponed. The core is small (~100 lines) and switching would require Java + JNA on the PC. Reevaluate if the core grows (multiple translation services, language choice, history).
