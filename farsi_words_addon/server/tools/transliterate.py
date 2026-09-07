#!/usr/bin/env python3
"""Convert IPA pronunciation notation into plain-English spelling.

Persian script does not write short vowels, so a Latin spelling is always
to some degree a reconstruction. This module handles the second half of
that job: turning IPA symbols (from a pronunciation dictionary or a G2P
model) into letters an English reader can actually sound out.

Output uses the English alphabet only -- no accented characters -- matching
the convention used throughout this app: aa, kh, gh, sh, zh, ch, j, oo.

Two things this deliberately does NOT do, both of which caused silent
wrong answers in an earlier version:
  * It no longer discards unrecognized symbols quietly. IPA has several
    look-alike characters (most importantly ASCII 'g' U+0067 versus IPA
    script 'g' U+0261, which are different characters), and dropping one
    silently turned "sang" into "san" with nothing in the logs to explain it.
  * It reports how many symbols it could not map, so callers can refuse to
    trust a conversion that lost information.
"""
import sys
import unicodedata

# Longest symbols first, so multi-character phonemes match before their
# single-character prefixes do.
IPA_TO_LATIN = [
    # Affricates (several encodings exist for the same two sounds)
    ("t\u0361\u0283", "ch"), ("d\u0361\u0292", "j"),
    ("t\u0283", "ch"), ("d\u0292", "j"),
    ("\u02A7", "ch"), ("\u02A4", "j"),
    # Long vowels
    ("\u0252\u02D0", "aa"), ("\u0251\u02D0", "aa"), ("a\u02D0", "aa"),
    ("i\u02D0", "ee"), ("u\u02D0", "oo"), ("o\u02D0", "o"), ("e\u02D0", "e"),
    # Vowels
    ("\u0252", "aa"), ("\u0251", "aa"), ("\u00E6", "a"), ("a", "a"),
    ("\u025B", "e"), ("\u0259", "e"), ("e", "e"), ("\u026A", "i"),
    ("i", "i"), ("\u0254", "o"), ("o", "o"), ("\u028A", "oo"), ("u", "oo"),
    # Consonants with digraph spellings
    ("\u0283", "sh"), ("\u0292", "zh"), ("x", "kh"), ("\u03B8", "s"),
    ("\u00F0", "z"), ("\u0263", "gh"), ("\u0281", "gh"), ("q", "gh"),
    ("\u0262", "gh"), ("\u0127", "h"), ("\u0295", ""),
    # Nasal + stop clusters, before the individual symbols, so that
    # /sae-ng-g/ spells "sang" rather than doubling up as "sangg".
    ("\u014B\u0261", "ng"), ("\u014Bg", "ng"), ("\u014Bk", "nk"),
    # Plain consonants
    ("\u0261", "g"), ("g", "g"), ("\u014B", "ng"), ("\u027E", "r"),
    ("\u0279", "r"), ("r", "r"), ("j", "y"), ("y", "y"), ("h", "h"),
    ("l", "l"), ("m", "m"), ("n", "n"), ("p", "p"), ("b", "b"),
    ("t", "t"), ("d", "d"), ("k", "k"), ("c", "k"), ("f", "f"),
    ("\u028B", "v"), ("v", "v"), ("w", "v"), ("s", "s"), ("z", "z"),
    ("\u0282", "sh"),
    # Marks carrying no spelling information
    ("\u02C8", ""), ("\u02CC", ""), ("\u02D0", ""), ("\u02B0", ""),
    ("\u02B2", ""), ("\u0294", ""), ("\u0361", ""), ("\u032F", ""),
    ("\u0303", ""), (".", ""), ("-", ""),
]


def ipa_to_latin_checked(ipa):
    """Convert IPA to plain-English spelling.

    Returns (spelling, unknown_symbols) so the caller can decide whether the
    conversion lost anything meaningful.
    """
    if not ipa:
        return "", []
    text = unicodedata.normalize("NFD", ipa.strip().strip("/[]"))
    result = []
    unknown = []
    i = 0
    while i < len(text):
        for symbol, latin in IPA_TO_LATIN:
            if text.startswith(symbol, i):
                result.append(latin)
                i += len(symbol)
                break
        else:
            ch = text[i]
            if ch.isspace():
                result.append(" ")
            elif not unicodedata.combining(ch):
                unknown.append(ch)
            i += 1
    return " ".join("".join(result).split()), unknown


def ipa_to_latin(ipa):
    """Convenience wrapper for callers that don't need the diagnostics."""
    return ipa_to_latin_checked(ipa)[0]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        spelling, unknown = ipa_to_latin_checked(sys.argv[1])
        if unknown:
            print(f"unmapped symbols: {unknown}", file=sys.stderr)
        print(spelling)
