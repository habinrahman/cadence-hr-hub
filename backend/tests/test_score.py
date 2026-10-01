"""The 0-100 score is built from requirement verdicts only, and it never decides the disposition."""

from decimal import Decimal

from app.domain.matching import overall_disposition, score_breakdown


def test_mandatory_share_70_and_preferred_share_30():
    pairs = [
        ("mandatory", "meets"),
        ("mandatory", "meets"),
        ("mandatory", "partial"),
        ("preferred", "meets"),
        ("preferred", "unknown"),
    ]
    result = score_breakdown(pairs)
    assert [str(row.possible) for row in result.rows] == ["23.4", "23.3", "23.3", "15.0", "15.0"]
    assert [str(row.earned) for row in result.rows] == ["23.4", "23.3", "11.7", "15.0", "0.0"]
    assert sum(row.possible for row in result.rows) == Decimal("100")
    assert result.total == Decimal("73.4") == sum(row.earned for row in result.rows)
    assert result.score == 73


def test_a_single_kind_of_requirement_shares_all_100_points():
    assert [str(r.possible) for r in score_breakdown([("mandatory", "meets")] * 4).rows] == ["25.0"] * 4
    assert score_breakdown([("preferred", "meets")] * 2).score == 100


def test_unmet_and_unknown_earn_nothing_and_partial_earns_half():
    result = score_breakdown([("mandatory", "unmet"), ("mandatory", "unknown"), ("mandatory", "partial"), ("mandatory", "meets")])
    assert [str(row.earned) for row in result.rows] == ["0.0", "0.0", "12.5", "25.0"]


def test_score_rounds_half_up_and_no_requirements_has_no_score():
    result = score_breakdown([("mandatory", "partial")] * 3 + [("mandatory", "meets")])
    assert result.total == Decimal("62.5")
    assert result.score == 63
    assert score_breakdown([]) is None


def test_a_high_score_does_not_clear_a_mandatory_gap():
    pairs = [("mandatory", "unmet")] + [("preferred", "meets")] * 3
    assert score_breakdown(pairs).score == 30  # the preferred pool alone is 30
    assert overall_disposition(pairs) == "excluded"
    many = [("mandatory", "meets")] * 9 + [("mandatory", "unmet")]
    assert score_breakdown(many).score == 90
    assert overall_disposition(many) == "excluded"
    unknown = [("mandatory", "meets")] * 9 + [("mandatory", "unknown")]
    assert overall_disposition(unknown) == "needs_review"


# ---------- two stages: the mandatory gate, then a ranking score only for candidates who pass it ----------

from app.api.hiring import _ranked  # noqa: E402
from app.domain.matching import RequirementVerdict, match_summary  # noqa: E402


def _rows(*items):
    """(name, strength, result) in requirement order."""
    return [RequirementVerdict(f"r{index}", name, strength, result) for index, (name, strength, result) in enumerate(items)]


def _carlos(years="meets", aws="meets"):
    return _rows(
        ("Python", "mandatory", "meets"),
        ("FastAPI", "mandatory", "meets"),
        ("PostgreSQL", "mandatory", "meets"),
        ("3 years experience", "mandatory", years),
        ("AWS", "preferred", aws),
    )


def test_all_mandatory_met_and_preferred_unknown_is_eligible_with_the_mandatory_pool():
    summary = match_summary(_carlos(aws="unknown"))
    assert summary.eligibility == "eligible"
    assert summary.match_score == 70
    assert (summary.mandatory_met, summary.mandatory_total) == (4, 4)
    assert (summary.preferred_met, summary.preferred_total) == (0, 1)
    assert summary.blocking == []
    assert summary.reason == "4/4 mandatory requirements met · AWS preferred not found"


def test_every_requirement_met_scores_100():
    summary = match_summary(_carlos())
    assert summary.eligibility == "eligible"
    assert summary.match_score == 100
    assert summary.reason == "4/4 mandatory requirements met"


def test_one_mandatory_unknown_needs_review_with_no_score():
    # The old arithmetic gave this candidate 53/100.
    summary = match_summary(_carlos(years="unknown", aws="unmet"))
    assert summary.eligibility == "needs_review"
    assert summary.match_score is None and summary.match_score_exact is None and summary.breakdown is None
    assert (summary.mandatory_met, summary.mandatory_total) == (3, 4)
    assert [row.name for row in summary.blocking] == ["3 years experience"]
    assert summary.reason == "Mandatory requirement unresolved: 3 years experience"


def test_one_mandatory_partial_needs_review_with_no_score():
    rows = _rows(("Python", "mandatory", "partial"), ("SQL", "mandatory", "meets"), ("AWS", "preferred", "meets"))
    summary = match_summary(rows)
    assert summary.eligibility == "needs_review"
    assert summary.match_score is None
    assert [(row.name, row.result) for row in summary.blocking] == [("Python", "partial")]


def test_one_mandatory_unmet_is_excluded_with_no_score():
    summary = match_summary(_carlos(years="unmet"))
    assert summary.eligibility == "excluded"
    assert summary.match_score is None
    assert [(row.name, row.result) for row in summary.blocking] == [("3 years experience", "unmet")]
    assert summary.reason == "Mandatory requirement not met: 3 years experience"


def test_one_mandatory_met_and_three_unknown_is_not_18():
    rows = _rows(
        ("Python", "mandatory", "unknown"),
        ("FastAPI", "mandatory", "unknown"),
        ("PostgreSQL", "mandatory", "unknown"),
        ("3 years experience", "mandatory", "meets"),
        ("AWS", "preferred", "unknown"),
    )
    summary = match_summary(rows)
    assert summary.eligibility == "needs_review"
    assert summary.match_score is None
    assert summary.mandatory_met == 1
    assert summary.reason == "Mandatory requirements unresolved: Python, FastAPI, PostgreSQL"


def test_preferred_partial_earns_half_its_share_once_the_gate_is_passed():
    summary = match_summary(_carlos(aws="partial"))
    assert summary.eligibility == "eligible"
    assert summary.match_score == 85
    assert summary.reason == "4/4 mandatory requirements met · AWS preferred partly met"


def test_preferred_only_request_still_shares_all_100():
    summary = match_summary(_rows(("AWS", "preferred", "meets"), ("GCP", "preferred", "unknown")))
    assert summary.eligibility == "eligible"
    assert summary.match_score == 50


def test_the_gate_matches_the_stored_disposition():
    for verdicts in (_carlos(), _carlos(years="unknown"), _carlos(years="unmet"), _carlos(years="partial")):
        pairs = [(row.strength, row.result) for row in verdicts]
        expected = {"recommended": "eligible", "needs_review": "needs_review", "excluded": "excluded"}[overall_disposition(pairs)]
        assert match_summary(verdicts).eligibility == expected


def _payload(name, eligibility, score=None, mandatory_met=0, ratio=0.0):
    return {
        "id": name or "unnamed",
        "candidate_name": name,
        "eligibility": eligibility,
        "match_score_exact": score,
        "mandatory_met": mandatory_met,
        "requirement_met_ratio": ratio,
    }


def test_eligible_candidates_always_rank_above_held_ones():
    ranked = _ranked(
        [
            _payload("review-3of4", "needs_review", mandatory_met=3, ratio=0.8),
            _payload("excluded", "excluded", mandatory_met=3, ratio=0.8),
            _payload("eligible-70", "eligible", 70.0, 4, 0.8),
            _payload("review-1of4", "needs_review", mandatory_met=1, ratio=0.2),
            _payload("eligible-100", "eligible", 100.0, 4, 1.0),
        ]
    )
    assert [item["id"] for item in ranked] == ["eligible-100", "eligible-70", "review-3of4", "review-1of4", "excluded"]


def test_unnamed_candidates_do_not_jump_the_queue():
    ranked = _ranked([_payload(None, "needs_review", mandatory_met=1), _payload("Ada", "needs_review", mandatory_met=1)])
    assert [item["candidate_name"] for item in ranked] == ["Ada", None]
