#!/usr/bin/env python3
"""Lightweight local HTTP server that keeps the Argos Translate
Persian -> English pipeline loaded in memory permanently, instead of
reloading it from disk on every translation request (which is what made
each word take several seconds). Listens on 127.0.0.1 only -- it's an
internal helper for server.js, not exposed outside the container.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import argostranslate.translate as translate
from PersianG2p import Persian_g2p_converter

print("Loading Argos Translate Persian -> English model into memory...", flush=True)
_installed = translate.get_installed_languages()
_fa = next(l for l in _installed if l.code == "fa")
_en = next(l for l in _installed if l.code == "en")
_translation = _fa.get_translation(_en)
print("Translation model ready.", flush=True)

print("Loading Persian G2P pronunciation model into memory...", flush=True)
_g2p = Persian_g2p_converter(use_large=True)
print("G2P model ready.", flush=True)

_DICT_PATH = "/app/models/fa_en_dict.json"
try:
    with open(_DICT_PATH, "r", encoding="utf-8") as f:
        _dictionary = json.load(f)
    print(f"Loaded {len(_dictionary)} dictionary entries.", flush=True)
except Exception as exc:
    print(f"Could not load dictionary file: {exc!r}", flush=True)
    _dictionary = {}

_IPA_DICT_PATH = "/app/models/fa_ipa_dict.json"
try:
    with open(_IPA_DICT_PATH, "r", encoding="utf-8") as f:
        _pron_dict = json.load(f)
    print(f"Loaded {len(_pron_dict)} pronunciation dictionary entries.", flush=True)
except Exception as exc:
    print(f"Could not load pronunciation dictionary file: {exc!r}", flush=True)
    _pron_dict = {}

# PersianG2p outputs accented Latin (ā, š, ž, ġ, x) rather than raw IPA.
# Normalize it to the same plain-ASCII spelling convention used everywhere
# else in this app (â, sh, zh, gh, kh).
_HOUSE_STYLE = {
    "ā": "â", "š": "sh", "ž": "zh", "ġ": "gh",
    "x": "kh", "č": "ch", "ū": "oo", "ī": "ee",
}


def to_house_style(text):
    out = text
    for k, v in _HOUSE_STYLE.items():
        out = out.replace(k, v)
    return out


def transliterate_word(text):
    key = text.strip()
    if not key:
        return ""
    if key in _pron_dict:
        return _pron_dict[key]
    try:
        raw = _g2p.transliterate(key)
        return to_house_style(raw)
    except Exception as exc:
        print(f"G2P error for {key!r}: {exc!r}", flush=True)
        return ""


def clean_translation(text):
    """Collapse a known failure mode of small offline translation models on
    short inputs, where the output repeats the same word (e.g. Persian دهان
    -> "Mouth of mouth." instead of just "mouth")."""
    if not text:
        return text
    words = text.strip().split()
    if len(words) >= 2:
        first = words[0].lower().rstrip(".,")
        last = words[-1].lower().rstrip(".,")
        if first == last:
            return words[0].rstrip(".,")
    # Also collapse simple immediate word-for-word repeats ("the the cat")
    deduped = []
    for w in words:
        if not deduped or deduped[-1].lower() != w.lower():
            deduped.append(w)
    return " ".join(deduped).rstrip(".")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # keep the app's log focused on real events, not routine requests

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        text = qs.get("text", [""])[0]

        if parsed.path == "/translate":
            key = text.strip()
            if key in _dictionary:
                result = _dictionary[key]
            else:
                try:
                    result = _translation.translate(text) if text else ""
                    result = clean_translation(result)
                except Exception as exc:
                    print(f"Translation error: {exc!r}", flush=True)
                    result = ""
            body = json.dumps({"translation": result}).encode("utf-8")
        elif parsed.path == "/transliterate":
            result = transliterate_word(text)
            body = json.dumps({"translit": result}).encode("utf-8")
        else:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 5001), Handler).serve_forever()
