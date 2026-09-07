#!/usr/bin/env python3
"""Build a compact Persian -> English dictionary lookup file from a
Wiktionary data dump (via kaikki.org's structured extraction of Wiktionary),
to use as a fast, accurate first pass for common words before falling back
to the AI translator. Runs once at Docker build time.

If the download or parsing fails for any reason (URL moved, format
changed, no network at build time), this exits without raising -- it just
writes an empty dictionary file. The app still works fine with the AI
translator alone in that case, just without this extra accuracy layer.
"""
import json
import os
import urllib.request

URL = "https://kaikki.org/dictionary/Persian/kaikki.org-dictionary-Persian.json"
RAW_PATH = "/tmp/fa_wiktionary_raw.jsonl"
OUT_PATH = "/app/models/fa_en_dict.json"

out = {}

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
            if not word or word in out:
                continue

            for sense in entry.get("senses", []):
                glosses = sense.get("glosses")
                if glosses:
                    out[word] = glosses[0]
                    break

    os.remove(RAW_PATH)
    print(f"Built dictionary with {len(out)} entries.", flush=True)

except Exception as exc:
    print(f"Dictionary build failed, continuing without it: {exc!r}", flush=True)
    out = {}

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
