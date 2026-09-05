#!/usr/bin/env python3
"""Approximate a Latin ("Finglish") spelling for a Persian word or phrase.

Persian script does not write short vowels, so there is no single correct
Latin spelling for a given piece of Persian text -- this produces a
reasonable phonetic guess by running the text through espeak-ng's Persian
phonemizer and mapping the resulting IPA symbols to Latin letters using the
same romanization conventions used elsewhere in this app (â, kh, gh, sh, zh,
ch, j). It is a best-effort guess, not a lookup -- always editable in the UI.

Usage: transliterate.py "متن فارسی"
"""
import re
import subprocess
import sys

# Longest IPA symbols first so multi-character phonemes match before their
# single-character prefixes do.
IPA_TO_LATIN = [
    ("tʃ", "ch"),
    ("dʒ", "j"),
    ("ɒː", "â"),
    ("ʃ", "sh"),
    ("ʒ", "zh"),
    ("x", "kh"),
    ("ɣ", "gh"),
    ("q", "gh"),
    ("ɒ", "â"),
    ("æ", "a"),
    ("e", "e"),
    ("i", "i"),
    ("o", "o"),
    ("u", "oo"),
    ("j", "y"),
    ("ʔ", ""),
    ("ˈ", ""),
    ("ˌ", ""),
    ("ː", ""),
    ("h", "h"),
    ("r", "r"),
    ("l", "l"),
    ("m", "m"),
    ("n", "n"),
    ("p", "p"),
    ("b", "b"),
    ("t", "t"),
    ("d", "d"),
    ("k", "k"),
    ("g", "g"),
    ("f", "f"),
    ("v", "v"),
    ("s", "s"),
    ("z", "z"),
    ("w", "v"),
]


def ipa_to_latin(ipa: str) -> str:
    result = []
    i = 0
    while i < len(ipa):
        matched = False
        for symbol, latin in IPA_TO_LATIN:
            if ipa.startswith(symbol, i):
                result.append(latin)
                i += len(symbol)
                matched = True
                break
        if not matched:
            # Unknown symbol (stress marks, punctuation, etc.) - skip it
            i += 1
    return "".join(result)


def main():
    if len(sys.argv) < 2:
        print("", end="")
        return
    text = sys.argv[1]
    try:
        proc = subprocess.run(
            ["espeak-ng", "-v", "fa", "--ipa", "-q", text],
            capture_output=True,
            text=True,
            timeout=10,
        )
        ipa_output = proc.stdout.strip()
        words = ipa_output.split()
        latin_words = [ipa_to_latin(w) for w in words]
        guess = " ".join(w for w in latin_words if w)
        print(guess)
    except Exception:
        print("", end="")


if __name__ == "__main__":
    main()
