#!/usr/bin/env python3
"""Translate Persian text to English using the offline Argos Translate model
installed at image build time. Prints the translation to stdout.

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
        result = translate.translate(text, "fa", "en")
        print(result.strip())
    except Exception:
        # If translation fails for any reason, fail quietly with an empty
        # string so the caller can fall back to asking the user to fill it in.
        print("", end="")


if __name__ == "__main__":
    main()
