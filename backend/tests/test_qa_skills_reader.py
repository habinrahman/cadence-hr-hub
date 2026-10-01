"""Skills come from the skills section only. Found in the end-to-end pass: "Poker", "Graffiti", "Honors & Awards" and
"Programming Languages:" (label only) were stored as a candidate's skills."""

from uuid import uuid4

from app.extraction.deterministic import DeterministicExtractor


def _skills(text: str) -> list[str]:
    draft = DeterministicExtractor().extract(document_id=uuid4(), source_text=text, prompt_version="t")
    return [item.name for item in draft.skills]


def test_a_labelled_skill_line_keeps_the_skills_not_the_label():
    assert _skills("Jane Doe\nSkills\nProgramming Languages: Python, Java\nTools: Excel, Git") == ["Python", "Java", "Excel", "Git"]


def test_an_unrecognised_heading_ends_the_skills_list():
    text = "Jane Doe\nSKILLS\nPython, SQL\nHonors & Awards\nDean's list\nLeadership & Athletics\nVarsity soccer"
    assert _skills(text) == ["Python", "SQL"]


def test_interests_are_never_skills():
    assert _skills("Jane Doe\nSkills\nPython\nOther Activities: Investing Club\nExcel") == ["Python", "Excel"]
    assert _skills("Jane Doe\nSkills\nPython\nInterests: chess, poker, guitar") == ["Python"]


def test_a_real_skill_that_mentions_leadership_is_kept():
    assert _skills("Jane Doe\nSkills\nPython\nTeam Leadership\nExcel") == ["Python", "Team Leadership", "Excel"]
