"""Script detection. A non-English CV is still a CV."""

from __future__ import annotations


def detect_language(text: str) -> str:
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return "unknown"
    arabic = sum(1 for character in letters if "\u0600" <= character <= "\u06FF")
    latin = sum(1 for character in letters if ("A" <= character <= "Z") or ("a" <= character <= "z"))
    total = len(letters)
    has_arabic = arabic / total >= 0.2
    has_latin = latin / total >= 0.2
    if has_arabic and has_latin:
        return "mul"
    if has_arabic:
        return "ar"
    if latin / total >= 0.5:
        return "en"
    return "unknown"
