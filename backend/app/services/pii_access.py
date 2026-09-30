"""Candidate contacts and CV text are recruiter data."""

from __future__ import annotations


class PiiAccessError(Exception):
    def __init__(self, code: str = "recruiter_required") -> None:
        self.code = code
        super().__init__(code)


def allow_candidate_pii(role: str) -> None:
    """Raise unless this role is allowed to read contacts or CV text."""
    if role != "recruiter":
        raise PiiAccessError()
