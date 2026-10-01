"""A proposal is not a requirement until the quote is in the job description."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.constants import BLOCKED_FIELDS
from app.domain.protected import experience_supported, protected_reason, supporting_clause
from app.domain.requirements import RequirementDraft, _BLOCKED_LINE, _INJECTION, quote_in_description, sentence_is_injected

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


class ProposedRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Literal["skill", "experience", "education", "certification", "other"]
    text: str = Field(min_length=1, max_length=300)
    strength: Literal["mandatory", "preferred"]
    quote: str = Field(min_length=1, max_length=1000)


class ProposalRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_proposal(description: str, payload: object) -> RequirementDraft:
    if isinstance(payload, RequirementDraft):
        payload = {
            "label": payload.label,
            "text": payload.text,
            "strength": payload.strength,
            "quote": payload.quote,
        }
    if isinstance(payload, dict) and BLOCKED_FIELDS.intersection(payload):
        raise ProposalRejected("blocked_attribute")
    try:
        item = ProposedRequirement.model_validate(payload)
    except ValidationError as exc:
        raise ProposalRejected("malformed_output") from exc
    if _INJECTION.search(item.quote) or _INJECTION.search(item.text) or sentence_is_injected(description, item.quote):
        raise ProposalRejected("injected_instruction")
    text = item.text.strip()
    # A protected characteristic is never a requirement, in the text or in the clause it was taken from.
    # A lawful requirement elsewhere in the same sentence keeps its own, clean clause.
    clause = supporting_clause(item.quote, text) if item.label != "experience" else item.quote
    if _blocked(text) or protected_reason(text) or (item.label != "experience" and protected_reason(clause)):
        raise ProposalRejected("blocked_attribute")
    if not quote_in_description(description, item.quote):
        raise ProposalRejected("unsupported_requirement")
    if item.label == "experience":
        number = _NUMBER.search(text)
        if number is None or number.group(0) not in item.quote:
            raise ProposalRejected("unsupported_requirement")
        # The number must be a count of years of experience in the quote, never an age such as "aged 25-30".
        if not experience_supported(number.group(0), item.quote):
            raise ProposalRejected("blocked_attribute" if protected_reason(item.quote) else "unsupported_requirement")
        text = number.group(0)
    elif text.casefold() not in item.quote.casefold():
        raise ProposalRejected("unsupported_requirement")
    return RequirementDraft(item.label, text[:300], item.strength, item.quote)


def _blocked(value: str) -> bool:
    if value.casefold() in BLOCKED_FIELDS:
        return True
    return _BLOCKED_LINE.search(value) is not None
