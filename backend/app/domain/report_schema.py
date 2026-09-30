"""Problem-report context accepts only a fixed set of safe fields."""

from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CODE = re.compile(r"^[a-z0-9_]{1,80}$")
_ROUTE = re.compile(r"^/[a-z0-9_./-]{0,80}$")
_BLOCKED = re.compile(r"password|token|bearer|embedding|secret|api[_-]?key", re.IGNORECASE)

EntityType = Literal["candidate", "hiring_request", "document", "none"]
Category = Literal["intake", "matching", "sharing", "sourcing", "other"]
ReportStatus = Literal["open", "in_progress", "resolved"]


class ReportContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: str | None = None
    route: str | None = None
    action: str | None = None

    @field_validator("error_code", "action")
    @classmethod
    def code_is_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if _CODE.fullmatch(text) is None or _BLOCKED.search(text):
            raise ValueError("unsafe_context")
        return text

    @field_validator("route")
    @classmethod
    def route_is_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if _ROUTE.fullmatch(text) is None or "@" in text or _BLOCKED.search(text):
            raise ValueError("unsafe_context")
        return text


class CreateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    entity_type: EntityType = "none"
    entity_id: UUID | None = None
    context: ReportContext = Field(default_factory=ReportContext)

    @field_validator("title", "description")
    @classmethod
    def prose_is_safe(cls, value: str) -> str:
        text = " ".join(value.split())
        if not text:
            raise ValueError("empty")
        if "@" in text or _BLOCKED.search(text) or re.search(r"\d{8,}", text):
            raise ValueError("unsafe_content")
        return text


class EngineerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReportStatus | None = None
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note")
    @classmethod
    def note_is_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = " ".join(value.split())
        if not text:
            return None
        if "@" in text or _BLOCKED.search(text) or re.search(r"\d{8,}", text):
            raise ValueError("unsafe_content")
        return text
