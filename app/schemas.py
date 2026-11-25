"""Pydantic request models for the v1 API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Binary = Literal[0, 1]


class AssessmentRequest(BaseModel):
    """The exactly twelve values the dashboard/classifier understands."""

    model_config = ConfigDict(extra="forbid")

    age: int = Field(ge=18, le=120)
    male: Binary
    bmi: float = Field(ge=10, le=80)
    sbp: float = Field(ge=70, le=260)
    dbp: float = Field(ge=40, le=150)

    smoker: Binary | None = None
    waist: float | None = Field(default=None, ge=40, le=200)
    hdl: float = Field(ge=10, le=200)

    fam_dm: Binary | None = None
    fam_mi: Binary | None = None
    vig_rec: Binary | None = None
    mod_rec: Binary | None = None

    def model_values(self) -> dict[str, int | float | None]:
        """Return values in the same shape used by the notebook card builder."""
        return self.model_dump()


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str | None = Field(default=None, max_length=120)
    message: str = Field(min_length=1, max_length=500)

    @field_validator("session_id")
    @classmethod
    def empty_session_is_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("message")
    @classmethod
    def message_must_have_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Pertanyaan tidak boleh kosong.")
        return value


class AssessmentResponse(BaseModel):
    assessment_id: str
    created_at: str
    expires_at: str
    probabilities: dict[str, float]
    card: dict
    versions: dict[str, str | None]


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    turn: int
    guard: dict
    fallback: bool
    model_version: str