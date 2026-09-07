#!/usr/bin/env python3
"""Normalize Persian text so dictionary lookups match reliably.

The same Persian word can be typed several different ways depending on the
keyboard used. Arabic keyboards produce ي and ك where Persian keyboards
produce ی and ک -- visually near-identical, but completely different
characters to a computer, so an unnormalized lookup misses entirely.
Optional vowel marks (which Wiktionary entries often include but ordinary
typing never does) cause the same problem.

Normalizing both sides of every lookup makes those variants match.
"""

# Character variants that should all collapse to one canonical form.
_CHAR_MAP = {
    "\u064A": "\u06CC",  # Arabic yeh -> Persian yeh
    "\u0649": "\u06CC",  # Alef maksura -> Persian yeh
    "\u0643": "\u06A9",  # Arabic kaf -> Persian kaf
    "\u0623": "\u0627",  # Alef with hamza above -> plain alef
    "\u0625": "\u0627",  # Alef with hamza below -> plain alef
    "\u0622": "\u0627",  # Alef madda -> plain alef
    "\u0671": "\u0627",  # Alef wasla -> plain alef
    "\u0629": "\u0647",  # Teh marbuta -> heh
    "\u06C0": "\u0647",  # Heh with yeh above -> heh
    "\u0624": "\u0648",  # Waw with hamza -> waw
    "\u200C": "",        # Zero-width non-joiner
    "\u200F": "",        # Right-to-left mark
    "\u200E": "",        # Left-to-right mark
    "\u0640": "",        # Tatweel (decorative letter-stretching)
}

# Short-vowel and other diacritic marks: written in dictionaries and
# teaching material, essentially never in everyday typing.
_DIACRITICS = "".join(chr(c) for c in range(0x064B, 0x0653)) + "\u0670"

_ARABIC_DIGITS = {
    "\u0660": "0", "\u0661": "1", "\u0662": "2", "\u0663": "3", "\u0664": "4",
    "\u0665": "5", "\u0666": "6", "\u0667": "7", "\u0668": "8", "\u0669": "9",
    "\u06F0": "0", "\u06F1": "1", "\u06F2": "2", "\u06F3": "3", "\u06F4": "4",
    "\u06F5": "5", "\u06F6": "6", "\u06F7": "7", "\u06F8": "8", "\u06F9": "9",
}


def normalize_fa(text):
    """Return a canonical form of Persian text for use as a lookup key."""
    if not text:
        return ""
    out = []
    for ch in text.strip():
        if ch in _DIACRITICS:
            continue
        ch = _CHAR_MAP.get(ch, _ARABIC_DIGITS.get(ch, ch))
        out.append(ch)
    return "".join(out).strip()
