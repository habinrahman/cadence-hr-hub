"""The CV name reader. A wrong name is worse than none: the name feeds the relationship check, and a place or a job
title read as a name links strangers who share it. Every case below was read wrongly from the real corpus."""

from uuid import uuid4

import pytest

from app.extraction.deterministic import DeterministicExtractor


def _name(text: str) -> str | None:
    return DeterministicExtractor().extract(document_id=uuid4(), source_text=text, prompt_version="t").display_name


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # A nickname in brackets is part of the name; before the fix the reader skipped it and took "Berkeley, CA".
        ("Zhouyi (Zoey) Yang\n(949)-870-2319 | Irvine, CA\nEDUCATION\nUniversity of California, Berkeley\nBerkeley, CA", "Zhouyi (Zoey) Yang"),
        ("YUSHUO (EDDIE) ZHANG\nGlendora, CA • (626) 877-4888\nEDUCATION\nBerkeley, CA", "YUSHUO (EDDIE) ZHANG"),
        # A one-line header: the name is the first part.
        ("MANIK SINGH|San Francisco, CA | 925-577-5295\nEDUCATION\nUNIVERSITY OF CALIFORNIA, BERKELEY", "MANIK SINGH"),
        # A labelled fact above the name is not the name.
        ("Triple Citizenship: USA, Brazil, Venezuela\nBeatrix Aiko Gnemi\nbeatrix_gnemi@berkeley.edu", "Beatrix Aiko Gnemi"),
        # An address above the name.
        ("15024 Encanto Drive\nSherman Oaks, CA\naidenmertzel@berkeley.edu\n747.477.6460\nAiden Mertzel\nEDUCATION", "Aiden Mertzel"),
    ],
)
def test_reads_the_persons_name(text, expected):
    assert _name(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "ethan_toh@berkeley.edu • (510) 365-9474\nEducation\nUniversity of California, Berkeley\nBerkeley, CA",
        "Blind Resume\nPROFESSIONAL PROFILE\nHigh-achieving Finance undergraduate",
        "SID: 3041496968\nResearch\nResearch Intern\nStanford University",
        "+1 (347) 576-7588\nUC Berkeley - Management\nDual Degree: B.S. Bioengineering & B.S. Business\nSeek LLC, Nashville, Tennessee, USA",
        "[Redacted]\nEDUCATION\nUniversity of California, Berkeley\nMay 2029\nB.S. Business Administration",
        "Product Strategy Consultant, YOUROK\nNanyang Technological University, Singapore",
    ],
)
def test_a_place_a_school_or_a_title_is_never_a_name(text):
    assert _name(text) is None


def test_the_candidates_own_email_finds_a_name_printed_at_the_bottom():
    """Two-column layouts put the name after the body text. The CV's first email corroborates it."""
    body = "\n".join(f"Line {i} of experience" for i in range(30))
    text = f"mohan_aniruddh@berkeley.edu\nEDUCATION\n{body}\nAniruddh Mohan"
    assert _name(text) == "Aniruddh Mohan"


def test_a_referees_email_does_not_replace_the_header_name():
    body = "\n".join(f"Line {i} of experience" for i in range(30))
    text = f"SALMAN ALMAHARI\nCybersecurity Analyst\n{body}\nREFERENCES\nAli Khalfan\na.khalfan@bank.example"
    assert _name(text) == "SALMAN ALMAHARI"


def test_a_capitalised_line_deep_in_the_cv_is_not_taken_without_corroboration():
    body = "\n".join(f"line {i} of experience" for i in range(30))
    assert _name(f"EDUCATION\n{body}\nRystad Energy") is None
