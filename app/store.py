"""In-memory assessment and chat-session stores.

The demo runs as a single uvicorn worker, so a simple lock-protected dict is
enough. Nothing is written to disk: health values disappear on service restart.
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass
class Assessment:
    id: str
    card: dict
    probabilities: dict[str, float]
    versions: dict[str, str | None]
    created_at: datetime
    expires_at: datetime


@dataclass
class Turn:
    question: str
    answer: str
    fallback: bool


@dataclass
class Session:
    id: str
    assessment_id: str
    turns: list[Turn] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
    expires_at: datetime = field(
        default_factory=lambda: utcnow() + timedelta(minutes=30)
    )


class AssessmentStore:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._items: dict[str, Assessment] = {}
        self._lock = threading.Lock()

    def create(
        self,
        card: dict,
        probabilities: dict[str, float],
        versions: dict[str, str | None],
    ) -> Assessment:
        now = utcnow()
        assessment = Assessment(
            id=f"asm_{secrets.token_urlsafe(18)}",
            card=card,
            probabilities=probabilities,
            versions=versions,
            created_at=now,
            expires_at=now + self.ttl,
        )
        with self._lock:
            self._items[assessment.id] = assessment
        return assessment

    def get(self, assessment_id: str) -> Assessment | None:
        now = utcnow()
        with self._lock:
            assessment = self._items.get(assessment_id)
            if assessment is None:
                return None
            if assessment.expires_at <= now:
                self._items.pop(assessment_id, None)
                return None
            return assessment


class SessionStore:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._items: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, assessment_id: str) -> Session:
        now = utcnow()
        session = Session(
            id=f"cht_{secrets.token_urlsafe(18)}",
            assessment_id=assessment_id,
            created_at=now,
            expires_at=now + self.ttl,
        )
        with self._lock:
            self._items[session.id] = session
        return session

    def get(self, session_id: str, assessment_id: str) -> Session | None:
        now = utcnow()
        with self._lock:
            session = self._items.get(session_id)
            if session is None or session.assessment_id != assessment_id:
                return None
            if session.expires_at <= now:
                self._items.pop(session_id, None)
                return None
            return session

    def add_turn(
        self,
        session: Session,
        question: str,
        answer: str,
        fallback: bool,
    ) -> int:
        with self._lock:
            if session.expires_at <= utcnow():
                self._items.pop(session.id, None)
                raise ValueError("session expired")
            session.turns.append(Turn(question, answer, fallback))
            return len(session.turns)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._items.pop(session_id, None)