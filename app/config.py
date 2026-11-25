"""Runtime configuration for the Raspberry Pi API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name, "1" if default else "0").lower()
    return value in {"1", "true", "yes", "on"}


def _env_csv(name: str) -> tuple[str, ...]:
    value = os.getenv(name, "")
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    api_token: str = ""
    risk_model_version: str = "catboost-2026.11"
    chat_model_version: str = "chatbot-kesehatan-qwen2.5-0.5b-q4km"

    model_dir: Path = field(default_factory=lambda: BASE_DIR / "models")
    meta_path: Path = field(default_factory=lambda: BASE_DIR / "data" / "final" / "meta.json")
    risk_levels_path: Path = field(default_factory=lambda: BASE_DIR / "data" / "final" / "risk_levels.json")
    dashboard_dir: Path = field(default_factory=lambda: BASE_DIR / "dashboard" / "dist")

    chat_base_url: str = "http://127.0.0.1:8080"
    chat_multi_turn: bool = False
    chat_max_turns: int = 2
    chat_max_tokens: int = 320
    chat_temperature: float = 0.0
    chat_top_p: float = 1.0
    chat_timeout_seconds: float = 170.0

    assessment_ttl_seconds: int = 2 * 60 * 60
    session_ttl_seconds: int = 30 * 60

    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    )

    @property
    def effective_max_turns(self) -> int:
        return 1 if not self.chat_multi_turn else max(1, self.chat_max_turns)


def load_settings() -> Settings:
    origins = _env_csv("CORS_ORIGINS")
    return Settings(
        api_token=_env("HEALTH_API_TOKEN", ""),
        risk_model_version=_env("RISK_MODEL_VERSION", "catboost-2026.11"),
        chat_model_version=_env(
            "CHAT_MODEL_VERSION", "chatbot-kesehatan-qwen2.5-0.5b-q4km"
        ),
        model_dir=Path(_env("RISK_MODEL_DIR", str(BASE_DIR / "models"))).resolve(),
        meta_path=Path(
            _env("META_PATH", str(BASE_DIR / "data" / "final" / "meta.json"))
        ).resolve(),
        risk_levels_path=Path(
            _env("RISK_LEVELS_PATH", str(BASE_DIR / "data" / "final" / "risk_levels.json"))
        ).resolve(),
        dashboard_dir=Path(
            _env("DASHBOARD_DIR", str(BASE_DIR / "dashboard" / "dist"))
        ).resolve(),
        chat_base_url=_env("CHAT_BASE_URL", "http://127.0.0.1:8080").rstrip("/"),
        chat_multi_turn=_env_bool("CHAT_MULTI_TURN", False),
        chat_max_turns=_env_int("CHAT_MAX_TURNS", 2),
        chat_max_tokens=_env_int("CHAT_MAX_TOKENS", 320),
        chat_temperature=_env_float("CHAT_TEMPERATURE", 0.0),
        chat_top_p=_env_float("CHAT_TOP_P", 1.0),
        chat_timeout_seconds=_env_float("CHAT_TIMEOUT_SECONDS", 170.0),
        assessment_ttl_seconds=_env_int("ASSESSMENT_TTL_SECONDS", 2 * 60 * 60),
        session_ttl_seconds=_env_int("SESSION_TTL_SECONDS", 30 * 60),
        cors_origins=origins or (
            "http://127.0.0.1:4173",
            "http://localhost:4173",
        ),
    )