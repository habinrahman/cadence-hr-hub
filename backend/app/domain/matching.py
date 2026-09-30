"""Overall state follows the requirement verdicts. A similarity score is not a verdict."""

from __future__ import annotations


def overall_disposition(pairs: list[tuple[str, str]]) -> str:
    """pairs are (strength, result). Preferred gaps do not exclude a candidate."""
    mandatory = [result for strength, result in pairs if strength == "mandatory"]
    if any(result == "unmet" for result in mandatory):
        return "excluded"
    if any(result in {"partial", "unknown"} for result in mandatory):
        return "needs_review"
    return "recommended"


def explain(rows: list[tuple[str, str, str]]) -> str:
    """rows are (requirement text, strength, result). No CV quotes."""
    meets = [text for text, _strength, result in rows if result == "meets"]
    gaps = [
        f"{text} ({strength}, {result})"
        for text, strength, result in rows
        if result != "meets"
    ]
    parts: list[str] = []
    if meets:
        parts.append("Meets: " + ", ".join(meets))
    if gaps:
        parts.append("Gaps: " + ", ".join(gaps))
    if not parts:
        return "No requirements to compare."
    return "; ".join(parts)[:500]
