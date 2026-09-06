#!/usr/bin/env python3
"""Translate Persian text to English using the offline Argos Translate model
installed at image build time. Prints the translation to stdout. On any
failure, prints diagnostic details to stderr (visible in the app's Log tab
in Home Assistant) instead of failing silently, and prints an empty string
to stdout so the caller can fall back gracefully.

Usage: translate.py "متن فارسی"
"""
import sys
import argostranslate.translate as translate


def main():
    if len(sys.argv) < 2:
        print("", end="")
        return
    text = sys.argv[1]
    try:
        installed_languages = translate.get_installed_languages()
        from_lang = next((l for l in installed_languages if l.code == "fa"), None)
        to_lang = next((l for l in installed_languages if l.code == "en"), None)
        if not from_lang or not to_lang:
            codes = [l.code for l in installed_languages]
            print(
                f"No fa->en Argos Translate model found installed. "
                f"Installed language codes: {codes}",
                file=sys.stderr,
            )
            print("", end="")
            return
        translation = from_lang.get_translation(to_lang)
        result = translation.translate(text)
        print(result.strip())
    except Exception as exc:
        print(f"Translation error: {exc!r}", file=sys.stderr)
        print("", end="")


if __name__ == "__main__":
    main()
