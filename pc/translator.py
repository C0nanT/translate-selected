#!/usr/bin/env python3
"""Selection translator: select text in any app -> popup with the pt-BR translation.

Usage: python3 pc/translator.py   (Ctrl+C in the terminal to stop)
"""
import logging
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

from core import TooLarge, Translation, join_lines, parse_env, translate, validate  # noqa: E402
from popup import Popup  # noqa: E402
from network import fetch  # noqa: E402
import providers  # noqa: E402
from selection import Selection  # noqa: E402


def load_env():
    """Loads .env from the project root; variables already in the environment win."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    try:
        with open(path, encoding="utf-8") as f:
            for k, v in parse_env(f.read()).items():
                os.environ.setdefault(k, v)
    except FileNotFoundError:
        pass


class App:
    def __init__(self, provider):
        self.provider = provider
        self.popup = Popup()
        self.last = ""
        self.selection = Selection(self.popup.button_pressed, self.on_text)

    def on_text(self, text):
        text = join_lines(text)  # joins PDF line breaks; the size limit applies afterwards
        if text == self.last:
            return
        invalid = validate(text)
        if isinstance(invalid, TooLarge):  # red warning, no network
            self.last = text
            self.popup.show_text(text, "⚠ " + invalid.message, state="error")
            return
        if invalid is not None:  # empty or no letters: no popup
            return
        self.last = text
        self.popup.show_text(text, "", state="loading")
        threading.Thread(target=self.worker, args=(text,), daemon=True).start()

    def worker(self, text):
        logging.getLogger("translator").debug("translating %d chars", len(text))
        r = translate(text, fetch, self.provider)
        logging.getLogger("translator").debug("result: %s", type(r).__name__)
        if isinstance(r, Translation):
            result, error = r.text, False
        elif isinstance(r, TooLarge):  # URL too large once encoded
            result, error = "⚠ " + r.message, True
        else:  # Failure (Empty/NoLetters already filtered out in on_text)
            result, error = "⚠ " + r.reason, True
        GLib.idle_add(self.done, text, result, error)

    def done(self, text, result, error):
        # user clicked (closed) while loading, or already selected something else
        if not self.popup.get_visible() or text != self.last:
            if error and text == self.last:
                self.last = ""
            return
        if error:
            self.last = ""  # allows retrying with the same selection
            self.popup.show_text(text, result, state="error")
        else:
            self.popup.show_text(text, result)


if __name__ == "__main__":
    import signal
    from logging.handlers import RotatingFileHandler
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    # 2 files (translator.log + translator.log.1) x 1MB = 2MB max
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "translator.log"),
        maxBytes=1024 * 1024, backupCount=1, encoding="utf-8")
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("TRANSLATOR_DEBUG") else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), file_handler])
    load_env()
    try:
        provider = providers.from_env(os.environ)
    except ValueError as e:
        sys.exit(f"Erro de configuração: {e}")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    App(provider)
    print(f"Tradutor ativo ({provider.name}). Selecione texto. Ctrl+C para sair.")
    Gtk.main()
