#!/usr/bin/env python3
"""Lightweight local HTTP server that keeps the Argos Translate
Persian -> English pipeline loaded in memory permanently, instead of
reloading it from disk on every translation request (which is what made
each word take several seconds). Listens on 127.0.0.1 only -- it's an
internal helper for server.js, not exposed outside the container.
"""
import json
import os
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import argostranslate.translate as translate
from PersianG2p import Persian_g2p_converter

from fa_normalize import normalize_fa

print("Loading Argos Translate Persian -> English model into memory...", flush=True)
_installed = translate.get_installed_languages()
_fa = next(l for l in _installed if l.code == "fa")
_en = next(l for l in _installed if l.code == "en")
_translation = _fa.get_translation(_en)
print("Translation model ready.", flush=True)

print("Loading Persian G2P pronunciation model into memory...", flush=True)
_g2p = Persian_g2p_converter(use_large=True)
print("G2P model ready.", flush=True)

# Load the Piper voice ONCE and keep it in memory. Previously every word
# launched a fresh `piper` process, which re-read the ~60MB voice model from
# disk each time -- fine for one word, but that reload was the dominant cost
# when generating audio for a whole word list.
_PIPER_MODEL = "/app/models/fa_IR-gyro-medium.onnx"
_voice = None
try:
    from piper import PiperVoice
    print("Loading Piper voice model into memory...", flush=True)
    _voice = PiperVoice.load(_PIPER_MODEL)
    print("Piper voice ready.", flush=True)
except Exception as exc:
    # Not fatal: server.js falls back to running the piper command per word,
    # which is slower but works. Logged so the cause is visible.
    print(f"Could not preload Piper voice ({exc!r}); "
          f"audio will fall back to the slower per-word method.", flush=True)


def synthesize(text, out_path):
    """Write a WAV pronunciation of `text` to `out_path`."""
    if _voice is None:
        raise RuntimeError("Piper voice not loaded")
    tmp_path = out_path + ".tmp"
    with wave.open(tmp_path, "wb") as wav_file:
        # The method was renamed between Piper releases; support both.
        if hasattr(_voice, "synthesize_wav"):
            _voice.synthesize_wav(text, wav_file)
        else:
            _voice.synthesize(text, wav_file)
    # Move into place only once fully written, so a partial file is never
    # served to the app as if it were finished audio.
    os.replace(tmp_path, out_path)

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

# PersianG2p outputs accented Latin (ā, š, ž, ġ) rather than raw IPA.
# Convert it to the English-alphabet-only convention used everywhere else in
# this app. Ordering matters: multi-character results are produced by some
# rules, so anything that could re-match must come first.
_HOUSE_STYLE = [
    ("ā", "aa"), ("â", "aa"), ("Ā", "aa"), ("A", "aa"),
    ("š", "sh"), ("ž", "zh"), ("č", "ch"), ("ǧ", "gh"), ("ġ", "gh"),
    ("x", "kh"), ("q", "gh"), ("ū", "oo"), ("u", "oo"), ("ī", "ee"),
    ("'", ""), ("ʼ", ""), ("`", ""),
]


def to_house_style(text):
    out = text
    for old, new in _HOUSE_STYLE:
        out = out.replace(old, new)
    return out


def transliterate_word(text):
    """Spell out how a Persian word or phrase sounds, in English letters.

    Each word is looked up and converted individually. That matters for two
    reasons: the pronunciation dictionary is keyed per-word, and the G2P
    model spells unfamiliar words out letter-by-letter with spaces between
    them ("x o d aa"), which has to be closed up per word without also
    losing the real spaces between separate words.
    """
    if not text or not text.strip():
        return ""
    spelled = []
    for word in text.strip().split():
        key = normalize_fa(word)
        if key in _pron_dict:
            spelled.append(_pron_dict[key])
            continue
        try:
            raw = _g2p.transliterate(word)
            # Close up the model's letter-by-letter spacing within this word.
            collapsed = "".join(str(raw).split())
            converted = to_house_style(collapsed)
            spelled.append(converted)
        except Exception as exc:
            print(f"G2P error for {word!r}: {exc!r}", flush=True)
    return " ".join(w for w in spelled if w)


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
            key = normalize_fa(text)
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
        elif parsed.path == "/speak":
            out_path = qs.get("out", [""])[0]
            ok = False
            if text.strip() and out_path:
                try:
                    synthesize(text.strip(), out_path)
                    ok = True
                except Exception as exc:
                    print(f"Piper synthesis failed for {text!r}: {exc!r}", flush=True)
            body = json.dumps({"ok": ok}).encode("utf-8")
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
    # Threading so that a slow audio synthesis doesn't hold up a translation
    # or transliteration request happening at the same time.
    ThreadingHTTPServer(("127.0.0.1", 5001), Handler).serve_forever()
