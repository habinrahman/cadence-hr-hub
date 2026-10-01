"""Overall state follows the requirement verdicts. A similarity score is not a verdict.

The hiring-request match score lives here. It has nothing to do with the CV identity score in domain.confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


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


MANDATORY_POINTS = 70
PREFERRED_POINTS = 30
_CREDIT = {"meets": Decimal("1"), "partial": Decimal("0.5")}
_TENTH = Decimal("0.1")


@dataclass(frozen=True)
class RequirementPoints:
    possible: Decimal
    earned: Decimal


@dataclass(frozen=True)
class ScoreBreakdown:
    rows: list[RequirementPoints]
    total: Decimal  # exact, one decimal: the sum of the earned points shown per requirement

    @property
    def score(self) -> int:
        return int(self.total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def score_breakdown(pairs: list[tuple[str, str]]) -> ScoreBreakdown | None:
    """A 100-point score built only from requirement verdicts. pairs are (strength, result), in requirement order.

    Mandatory requirements share 70 points and preferred ones share 30. If only one kind exists it shares all 100.
    Meets earns the full share, partial half, unmet and unknown nothing. Shares are cut in tenths and always add up
    to the pool, so every point on the card traces to one requirement. The score ranks and explains; it never
    changes the disposition, which overall_disposition decides from the mandatory verdicts alone.
    """
    if not pairs:
        return None
    mandatory = [i for i, (strength, _r) in enumerate(pairs) if strength == "mandatory"]
    other = [i for i in range(len(pairs)) if i not in set(mandatory)]
    pools = (
        {"m": 100, "o": 0} if not other else {"m": 0, "o": 100} if not mandatory else {"m": MANDATORY_POINTS, "o": PREFERRED_POINTS}
    )
    possible: dict[int, Decimal] = {}
    for indexes, pool in ((mandatory, pools["m"]), (other, pools["o"])):
        possible.update(_split(indexes, pool))
    rows = []
    for index, (_strength, result) in enumerate(pairs):
        share = possible[index]
        earned = (share * _CREDIT.get(result, Decimal("0"))).quantize(_TENTH, rounding=ROUND_HALF_UP)
        rows.append(RequirementPoints(possible=share, earned=earned))
    return ScoreBreakdown(rows=rows, total=sum((row.earned for row in rows), Decimal("0")))


ELIGIBILITY = {"recommended": "eligible", "needs_review": "needs_review", "excluded": "excluded"}


@dataclass(frozen=True)
class RequirementVerdict:
    """One requirement and the verdict the matcher gave it. name is the text a recruiter reads."""

    requirement_id: str
    name: str
    strength: str
    result: str


@dataclass(frozen=True)
class MatchSummary:
    eligibility: str  # eligible | needs_review | excluded
    match_score: int | None  # null unless every mandatory requirement is met
    match_score_exact: Decimal | None
    breakdown: ScoreBreakdown | None  # per-requirement points, only when match_score is set
    mandatory_met: int
    mandatory_total: int
    preferred_met: int
    preferred_total: int
    blocking: list[RequirementVerdict]
    reason: str


def match_summary(rows: list[RequirementVerdict]) -> MatchSummary:
    """Two stages. First the mandatory gate, from the verdicts as the matcher gave them: any unmet excludes, any
    partial or unknown needs review. Then, only for a candidate who meets every mandatory requirement, the 0-100
    ranking score from score_breakdown. A blocked candidate gets no score at all, not a low one: the arithmetic
    for them would look like a ranking and is not one.
    """
    pairs = [(row.strength, row.result) for row in rows]
    eligibility = ELIGIBILITY[overall_disposition(pairs)]
    mandatory = [row for row in rows if row.strength == "mandatory"]
    preferred = [row for row in rows if row.strength != "mandatory"]
    mandatory_met = sum(row.result == "meets" for row in mandatory)
    preferred_met = sum(row.result == "meets" for row in preferred)
    if eligibility == "excluded":
        blocking = [row for row in mandatory if row.result == "unmet"]
    else:
        blocking = [row for row in mandatory if row.result != "meets"]
    breakdown = score_breakdown(pairs) if eligibility == "eligible" else None
    return MatchSummary(
        eligibility=eligibility,
        match_score=breakdown.score if breakdown else None,
        match_score_exact=breakdown.total if breakdown else None,
        breakdown=breakdown,
        mandatory_met=mandatory_met,
        mandatory_total=len(mandatory),
        preferred_met=preferred_met,
        preferred_total=len(preferred),
        blocking=blocking,
        reason=_reason(eligibility, blocking, mandatory_met, len(mandatory), preferred),
    )


def _reason(eligibility: str, blocking: list[RequirementVerdict], met: int, total: int, preferred: list[RequirementVerdict]) -> str:
    names = ", ".join(row.name for row in blocking)
    plural = len(blocking) != 1
    if eligibility == "excluded":
        return f"Mandatory requirement{'s' if plural else ''} not met: {names}"[:500]
    if eligibility == "needs_review":
        return f"Mandatory requirement{'s' if plural else ''} unresolved: {names}"[:500]
    parts = [f"{met}/{total} mandatory requirements met"] if total else []
    for row in preferred:
        if row.result == "partial":
            parts.append(f"{row.name} preferred partly met")
        elif row.result != "meets":
            parts.append(f"{row.name} preferred not found")
    if not parts and preferred:
        parts.append(f"{len(preferred)}/{len(preferred)} preferred requirements met")
    return (" · ".join(parts) or "No requirements to compare")[:500]


def _split(indexes: list[int], pool: int) -> dict[int, Decimal]:
    """Share a pool across requirements in whole tenths; the first ones take any remainder tenth."""
    if not indexes:
        return {}
    tenths, extra = divmod(pool * 10, len(indexes))
    return {
        index: Decimal(tenths + (1 if position < extra else 0)) * _TENTH
        for position, index in enumerate(indexes)
    }
