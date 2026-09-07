#!/usr/bin/env python3
"""Build a starter vocabulary list from an open Persian word-frequency list
(hermitdave/FrequencyWords, CC BY-SA 3.0 -- built from real subtitle/corpus
data, so it reflects everyday usage rather than formal/literary text).

Words are filtered to skip short grammatical/function words, then matched
against the Wiktionary dictionary already built by build_dictionary.py --
only words with a real dictionary gloss are included, so this starter list
doesn't inherit the small AI translator's occasional repetition quirks.
Romanized spelling is generated the same way as the "Add a word" flow
(espeak-ng phonemization), for consistency.

Runs once at Docker build time. Fails gracefully (writes an empty list) if
the download or dictionary file is unavailable -- the app still works fine
without this extra starter content in that case.
"""
import json
import re
import subprocess
import urllib.request

FREQ_URL = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2016/fa/fa_50k.txt"
DICT_PATH = "/app/models/fa_en_dict.json"
OUT_PATH = "/app/models/starter_words.json"
TARGET_COUNT = 1000

# Common Persian function/grammar words to skip -- a raw frequency list's
# top entries are dominated by these rather than useful standalone vocabulary.
STOPWORDS = {
    "و", "را", "به", "از", "که", "این", "است", "در", "با", "هم", "تا",
    "یا", "اگر", "همه", "آن", "من", "تو", "او", "ما", "شما", "ایشان",
    "می", "شد", "شود", "بود", "کرد", "کند", "های", "ها", "برای", "چون",
    "اما", "یک", "دو", "خود", "هر", "نه", "بی", "چه", "کجا", "چرا",
    "پس", "نیز", "دیگر", "روی", "زیر", "بین", "بعد", "قبل", "چند",
}

from transliterate import ipa_to_latin  # noqa: E402  (sits alongside this script)
from g2p_fa import G2P_Fa


try:
    with open("/app/models/fa_ipa_dict.json", encoding="utf-8") as f:
        pron_dict = json.load(f)
except Exception:
    pron_dict = {}

print("Loading Persian G2P model for starter word transliteration...", flush=True)
_g2p = G2P_Fa()


def transliterate(text):
    if text in pron_dict:
        return pron_dict[text]
    try:
        return ipa_to_latin(_g2p(text))
    except Exception:
        return ""


out = []
try:
    with open(DICT_PATH, encoding="utf-8") as f:
        dictionary = json.load(f)

    print(f"Downloading Persian frequency list from {FREQ_URL} ...", flush=True)
    with urllib.request.urlopen(FREQ_URL, timeout=30) as resp:
        lines = resp.read().decode("utf-8").splitlines()

    seen = set()
    for line in lines:
        if len(out) >= TARGET_COUNT:
            break
        parts = line.strip().split()
        if not parts:
            continue
        word = parts[0]
        if len(word) < 2 or word in STOPWORDS or word in seen:
            continue
        if not re.match(r"^[\u0600-\u06FF]+$", word):
            continue  # skip anything mixed with digits/Latin letters/punctuation
        seen.add(word)
        english = dictionary.get(word)
        if not english:
            continue  # only include words with a real dictionary gloss
        out.append({
            "category": "Common words",
            "farsi": word,
            "english": english,
            "translit": transliterate(word),
        })

    print(f"Built starter list with {len(out)} words.", flush=True)

except Exception as exc:
    print(f"Starter word list build failed, continuing without it: {exc!r}", flush=True)
    out = []

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
