"""Deterministic checks that keep protected characteristics out of hiring requirements.

A requirement may not be about religion, nationality, ethnicity or race, gender, marital status or age, however it is
worded and whichever reader proposed it. The check runs on the requirement text and on the clause of the quote that
the requirement was taken from, so a lawful requirement in the same sentence ("at least 5 years of Python") survives
while the protected part ("aged 25-30") does not.
"""

from __future__ import annotations

import re

_WORD = r"(?<![a-z])(?:{})(?![a-z])"


def _words(*items: str) -> re.Pattern[str]:
    return re.compile(_WORD.format("|".join(items)), re.IGNORECASE)


# Unambiguous terms: rejected wherever they appear in the requirement's clause.
_RELIGION = _words(
    "religion", "religious", "faith", "muslims?", "islam(?:ic)?", "christians?", "christianity", "catholics?",
    "protestants?", "orthodox", "jews?", "jewish", "judaism", "hindus?", "hinduism", "buddhists?", "buddhism", "sikhs?",
    "atheists?", "sunnis?", "shia", "shiites?", "church-?going", "practising", "practicing", "halal-observant",
)
_ETHNICITY = _words(
    "race", "racial", "ethnic(?:ity)?", "caste", "skin colou?r", "white candidates?", "black candidates?", "caucasian",
    "african-american", "asians? only", "arab origin", "of [a-z]+ origin", "descent", "tribe", "tribal",
)
_GENDER = _words(
    "gender", "sex", "males?", "females?", "men only", "women only", "man only", "woman only", "ladies", "gentlemen",
    "boys?", "girls?", "masculine", "feminine", "transgender", "pregnan(?:t|cy)",
)
_MARITAL = _words(
    "marital", "married", "unmarried", "divorced", "widowed", "spouse", "husband", "wife", "children", "kids",
    "family status", "(?:be|is|are|candidates?|applicants?|only) single", "single (?:candidates?|applicants?|persons?|people|men|women|status)",
)
_AGE = _words(
    "age", "aged", "ages", "years? of age", "years? old", "yrs? old", "\\d+\\s*(?:-|–|to)\\s*\\d+\\s*(?:years? old|yo)",
    "young(?:er)?", "older", "elderly", "youthful", "date of birth", "born (?:in|after|before)", "dob",
    "under \\d{2}\\b(?! years? of)", "over \\d{2}\\b(?! years? of)", "below \\d{2}\\b(?! years? of)",
    "recent graduates? only", "digital natives?",
)
_NATIONALITY = _words(
    "nationality", "nationals?", "citizens?", "citizenship", "passport holders?", "expats?", "expatriates?",
    "locals? only", "gcc nationals?", "saudis?", "emiratis?", "bahrainis?", "kuwaitis?", "qataris?", "omanis?",
    "yemenis?", "jordanians?", "egyptians?", "lebanese", "syrians?", "iraqis?", "iranians?", "palestinians?",
    "moroccans?", "tunisians?", "algerians?", "sudanese", "libyans?", "turks?", "turkish nationals?", "indians?",
    "pakistanis?", "bangladeshis?", "sri lankans?", "nepalese", "nepalis?", "filipinos?", "filipinas?",
    "indonesians?", "malaysians?", "thais?", "vietnamese", "koreans?", "japanese nationals?", "chinese nationals?",
    "americans?", "canadians?", "mexicans?", "brazilians?", "british nationals?", "britons?", "irish nationals?",
    "australians?", "nigerians?", "kenyans?", "ethiopians?", "south africans?", "russians?", "ukrainians?",
    "europeans?", "westerners?", "arabs?", "africans?", "asians?", "latinos?", "latinas?", "hispanics?",
)
# A language is a lawful skill. As a demonym it is not: "must be French", "French candidates only".
_LANGUAGE_DEMONYM = re.compile(
    r"(?i)(?:\bbe|\bare)\s+(?:a\s+)?(?:english|french|german|spanish|italian|chinese|japanese|arabic|british|dutch|polish|portuguese)\b"
    r"|\b(?:english|french|german|spanish|italian|chinese|japanese|british|dutch|polish|portuguese)\s+"
    r"(?:candidates?|applicants?|people|persons?|citizens?|nationals?|only|origin)\b"
    r"|\bnative\s+(?:born|citizens?)\b"
)

REASONS = (
    ("religion", _RELIGION),
    ("ethnicity", _ETHNICITY),
    ("gender", _GENDER),
    ("marital_status", _MARITAL),
    ("age", _AGE),
    ("nationality", _NATIONALITY),
)


def protected_reason(value: str | None) -> str | None:
    """The protected characteristic a piece of text is about, or None."""
    if not value:
        return None
    text = " ".join(value.split())
    for reason, pattern in REASONS:
        if pattern.search(text):
            return reason
    if _LANGUAGE_DEMONYM.search(text):
        return "nationality"
    return None


_CLAUSE_SPLIT = re.compile(r"[.;:!?\n]|,|\s+(?:and|with|plus|but|while|who|also)\s+", re.IGNORECASE)


def supporting_clause(quote: str, text: str) -> str:
    """The shortest clause of the quote that contains the requirement text. Falls back to the whole quote."""
    needle = text.casefold().strip()
    if not needle:
        return quote
    clauses = [c.strip() for c in _CLAUSE_SPLIT.split(quote) if c and c.strip()]
    holding = [c for c in clauses if needle in c.casefold()]
    return min(holding, key=len) if holding else quote


_YEARS_OF = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*\+?\s*(?:-\s*\d+\s*)?(?:years?|yrs?)(?!\s*(?:old|of age))", re.IGNORECASE
)
_AGE_NUMBER = re.compile(r"(?i)\b(?:aged?|ages)\s*(?:of\s*)?(\d+)|(\d+)\s*(?:-|–|to)\s*\d+\s*(?:years?\s*old|yo)\b|(\d+)\s*years?\s*old")


def experience_supported(number: str, quote: str) -> bool:
    """An experience number must be a count of years in the quote ("5 years", "3+ yrs"), never an age ("aged 25")."""
    ages = {group for m in _AGE_NUMBER.finditer(quote) for group in m.groups() if group}
    if number in ages:
        return False
    return any(m.group(1) == number for m in _YEARS_OF.finditer(quote))
