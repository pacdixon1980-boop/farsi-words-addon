#!/usr/bin/env python3
"""Build Persian -> English lookup files from a Wiktionary data dump (via
kaikki.org's structured extraction of Wiktionary), used as a fast, accurate
first pass before falling back to the AI translator. Runs at Docker build
time.

Produces two files:
  fa_en_dict.json   Persian word -> English meaning
  fa_ipa_dict.json  Persian word -> plain-English pronunciation spelling

Both are keyed on the NORMALIZED form of the Persian word (see
fa_normalize.py), so a word typed on an Arabic keyboard still matches a
dictionary entry written with Persian characters.

If the download or parsing fails for any reason (URL moved, format changed,
no network at build time), this exits without raising -- it just writes
empty files. The app still works fine with the AI models alone in that
case, just without this extra accuracy layer.
"""
import json
import os
import re
import urllib.request

from fa_normalize import normalize_fa
from transliterate import ipa_to_latin_checked

URL = "https://kaikki.org/dictionary/Persian/kaikki.org-dictionary-Persian.json"
RAW_PATH = "/tmp/fa_wiktionary_raw.jsonl"
OUT_PATH = "/app/models/fa_en_dict.json"
IPA_OUT_PATH = "/app/models/fa_ipa_dict.json"

# Senses tagged this way describe how a word was used centuries ago or in
# specialist registers. Taking one of these as THE meaning of an everyday
# word is a common way automated dictionary extraction goes wrong.
SKIP_TAGS = {
    "obsolete", "archaic", "dated", "poetic", "literary", "rare",
    "dialectal", "historical", "slang", "vulgar", "offensive",
}

# Glosses that describe grammar rather than meaning -- useless on a flashcard.
GRAMMAR_GLOSS = re.compile(
    r"^\s*(plural|singular|present|past|comparative|superlative|"
    r"inflection|alternative (form|spelling)|romanization|"
    r"vocative|genitive|construct)\b",
    re.IGNORECASE,
)


def clean_gloss(text):
    """Trim a Wiktionary gloss down to something that fits on a flashcard."""
    if not text:
        return ""
    # Drop a leading subject label like "(anatomy)" or "(botany)".
    text = re.sub(r"^\s*\([^)]{0,40}\)\s*", "", text).strip()
    # Keep only the first sense-clause; Wiktionary separates distinct
    # meanings within one gloss using semicolons.
    text = text.split(";")[0].strip()
    # Very long glosses are full explanations, not translations.
    if len(text) > 60:
        text = text[:60].rsplit(" ", 1)[0].strip()
    return text.strip(" .,")


def pick_gloss(entry):
    """Choose the most useful everyday meaning from an entry's senses."""
    fallback = ""
    for sense in entry.get("senses", []):
        tags = {t.lower() for t in sense.get("tags", [])}
        glosses = sense.get("glosses") or []
        if not glosses:
            continue
        cleaned = clean_gloss(glosses[0])
        if not cleaned or GRAMMAR_GLOSS.match(cleaned):
            continue
        if tags & SKIP_TAGS:
            fallback = fallback or cleaned
            continue
        return cleaned
    return fallback


out = {}
ipa_out = {}
stats = {"entries": 0, "ipa_found": 0, "ipa_rejected": 0}

try:
    print(f"Downloading Persian dictionary data from {URL} ...", flush=True)
    urllib.request.urlretrieve(URL, RAW_PATH)

    with open(RAW_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            word = entry.get("word")
            if not word:
                continue
            key = normalize_fa(word)
            if not key:
                continue

            if key not in out:
                gloss = pick_gloss(entry)
                if gloss:
                    out[key] = gloss
                    stats["entries"] += 1

            if key not in ipa_out:
                for sound in entry.get("sounds", []):
                    ipa = sound.get("ipa")
                    if not ipa:
                        continue
                    spelling, unknown = ipa_to_latin_checked(ipa)
                    # Refuse conversions that lost symbols we don't
                    # understand: a partial spelling is worse than none,
                    # because it looks confident while being wrong.
                    if unknown or not spelling:
                        stats["ipa_rejected"] += 1
                        continue
                    ipa_out[key] = spelling
                    stats["ipa_found"] += 1
                    break

    os.remove(RAW_PATH)
    print(f"Built dictionary with {stats['entries']} entries.", flush=True)
    print(
        f"Pronunciation data: {stats['ipa_found']} usable, "
        f"{stats['ipa_rejected']} rejected as unreliable.",
        flush=True,
    )

except Exception as exc:
    print(f"Dictionary build failed, continuing without it: {exc!r}", flush=True)
    out = {}
    ipa_out = {}

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
with open(IPA_OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(ipa_out, f, ensure_ascii=False)
