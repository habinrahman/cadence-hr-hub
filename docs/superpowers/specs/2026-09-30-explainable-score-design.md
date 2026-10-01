# Explainable 0-100 match score — design

Date: 2026-09-30
Status: approved in conversation (score model chosen by the user); not committed.

## Boundary (unchanged)

System: find, evaluate, explain, score, recommend. HR: review, shortlist, approve sharing, decide.
The score ranks and explains. It never changes the disposition and never shortlists.

## Model

- 100 points across the request's requirements. Mandatory requirements share 70, preferred share 30. If only one kind
  exists it shares all 100.
- A pool is split equally in whole tenths; the first requirements take any remainder tenth, so shares always add up to
  the pool exactly.
- Meets earns the full share, partial half, unmet and unknown nothing. Earned points are rounded half up to one decimal.
- Total = sum of the earned points shown per requirement (one decimal). Headline = total rounded half up to a whole
  number, shown as `78/100`.
- No embeddings in the score. Similarity finds evidence; evidence sets the verdict; verdicts set the points.
- `overall_disposition` is untouched: mandatory unmet excludes, mandatory partial/unknown needs review. A 92/100
  candidate with an unmet mandatory requirement is still excluded.

## Policy, not a client requirement

The 70/30 split is Cadence's own design choice. The client asked for a 0-100 score where every point is traceable to a
requirement and its evidence; the split is how we satisfy that. Present it as our policy, not as something the client
specified. A score of 100 means every requirement supplied for this request was met. It does not mean a perfect
candidate, and a request with only preferred requirements can reach 100 that way. The card says so.

## Where it lives

- Pure function `score_breakdown(pairs)` in `backend/app/domain/matching.py`, computed when a match is read. No schema
  change and no stored score, so it cannot drift from the verdicts.
- `_match_payload` (`backend/app/api/hiring.py`) adds `score`, `score_exact`, `score_max` and per-requirement
  `points_possible` / `points_earned`.
- UI: `N/100` on the candidate card, a Points column beside each requirement's verdict and CV evidence, and a line
  stating how the total was reached. The pool orders shortlisted, then disposition, then score.

## Out of scope

- Per-requirement weights set by HR; year-count requirements per skill ("5 years Python"). The matcher's experience
  requirement is total years only.
