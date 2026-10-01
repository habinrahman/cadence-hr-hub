"""Phone numbers are identity evidence, so a CV date or date range must never be read as one.

The shapes below were found as "phones" in the real 488-file corpus before this rule (33 of 384 phone rows)."""

import pytest

from app.extraction.contacts import find_phones


@pytest.mark.parametrize(
    "text",
    [
        "Analyst, Example Bank 2022 - 2024",
        "2013 - 2015",
        "2023-2025",
        "Bachelor of Science 2021 – 2025",
        "03/2021 - 06/2023",
        "2023-01-01",
        "Sep 2019 2021-2024 Present",
    ],
)
def test_dates_and_date_ranges_are_not_phone_numbers(text):
    assert find_phones(text) == []


@pytest.mark.parametrize(
    ("text", "digits"),
    [
        ("Mobile: +1 (651) 279-7684", "16512797684"),
        ("+973 3900 1122", "97339001122"),
        ("Tel 2409-4064", "24094064"),
        ("+49 1516 4525400", "4915164525400"),
        ("call 4088762500 today", "4088762500"),
        ("+973 2010 2020 5", "973201020205"),
    ],
)
def test_real_phone_numbers_are_kept(text, digits):
    assert [normalized for _raw, normalized in find_phones(text)] == [digits]


from app.extraction.deterministic import _name


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (["Relevant Coursework:", "Maya Rahman"], "Maya Rahman"),
        (["cumulative underlying notional exposure.", "Omar Farouk"], "Omar Farouk"),
        (["Guided Mentorship:", "hands-on application"], None),
        (["Competition stock selection."], None),
        (["Isabella J. de Souza"], "Isabella J. de Souza"),
        (["Ahmed bin Khalid"], "Ahmed bin Khalid"),
        (["SALMAN ALMAHARI"], "SALMAN ALMAHARI"),
        (["PROFESSIONAL EXPERIENCE", "Nadia Karim"], "Nadia Karim"),
        (["RELEVANT COURSES", "VOLUNTEER EXPERIENCE", "Work History", "School Leadership", "Sana Malik"], "Sana Malik"),
        (["ADDITIONAL HOBBIES AND INTEREST"], None),
    ],
)
def test_headings_and_sentence_fragments_are_not_names(lines, expected):
    """Shapes found as candidate names in the real corpus before the name rule was tightened."""
    assert _name(lines)[0] == expected


def _extract(text):
    from uuid import uuid4

    from app.extraction.deterministic import DeterministicExtractor

    return DeterministicExtractor().extract(document_id=uuid4(), source_text=text, prompt_version="t")


def test_real_world_experience_headings_are_read():
    draft = _extract("Nadia Karim\nPROFESSIONAL EXPERIENCE\nExample Bank, Analyst\nJune 2024 - Present\nWork History\nOther Co, Intern\n2022 - 2023\n")
    assert len(draft.experiences) >= 1
    assert any("Example Bank" in (item.employer or "") for item in draft.experiences)


def test_sections_the_parser_does_not_read_do_not_leak_into_certificates():
    draft = _extract("Nadia Karim\nCertifications:\nCFA Level 1\nInterests:\nWakeboarding, Snowboarding\nADDITIONAL INFORMATION\nFitness, Reading\n")
    names = [item.name for item in draft.certificates]
    assert names == ["CFA Level 1"]


def test_bullets_and_sentences_under_certifications_are_not_certificates():
    draft = _extract(
        "Nadia Karim\nCertifications\nInvestment Banking Job Simulation\n"
        "• Built a DCF model to derive implied equity value and share price\n"
        "with sensitivity analysis across WACC and terminal growth.\nCFA Level 1, Series 65\n"
    )
    assert [item.name for item in draft.certificates] == ["Investment Banking Job Simulation", "CFA Level 1", "Series 65"]


def test_a_heading_and_its_list_on_one_line_are_read():
    draft = _extract(
        "Richelle Gan\nSkills: Python, SQL, Excel\nCertificates: JP Morgan Virtual Experience, CFA Investment Foundations (In Progress)\n"
        "Activities: Basketball Team Captain, Coach\nEducation\nUC Berkeley, BA Economics\n"
    )
    assert [item.name for item in draft.skills] == ["Python", "SQL", "Excel"]
    assert [item.name for item in draft.certificates] == ["JP Morgan Virtual Experience", "CFA Investment Foundations (In Progress)"]
    # "Activities:" ends the certificate list, so its items are not filed under it.
    assert all("Basketball" not in item.name for item in draft.certificates)


def test_icon_glyphs_and_bullets_are_not_part_of_a_skill_name():
    draft = _extract("Omar Khan\nSkills\n• Analysis Excel, ANSYS FEA, Blender, • CAD & simulation SolidWorks, CFD\n")
    names = [item.name for item in draft.skills]
    assert names == ["Analysis Excel", "ANSYS FEA", "Blender", "CAD & simulation SolidWorks", "CFD"]
    assert all("" not in name and "" not in name and not name.startswith("•") for name in names)


def test_a_phone_next_to_a_date_range_is_still_found():
    text = "Jane Doe | +1 415 555 0123 | Analyst 2022 - 2024"
    assert [normalized for _raw, normalized in find_phones(text)] == ["14155550123"]
