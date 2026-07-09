from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ALLOWED_TEST_NUMBER = "+18054398008"


@dataclass(frozen=True)
class Settings:
    app_base_url: str
    host: str
    port: int

    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str

    openai_api_key: str
    openai_model: str
    openai_transcribe_model: str

    output_dir: Path
    calls_dir: Path
    reports_dir: Path

    max_turns: int
    max_call_minutes: int
    max_call_seconds: int


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer") from exc


def load_settings() -> Settings:
    output_dir = Path(os.getenv("OUTPUT_DIR", "data")).resolve()
    calls_dir = output_dir / "calls"
    reports_dir = output_dir / "reports"

    calls_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        app_base_url=_required("APP_BASE_URL").rstrip("/"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=_int_env("PORT", 8000),
        twilio_account_sid=_required("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=_required("TWILIO_AUTH_TOKEN"),
        twilio_from_number=_required("TWILIO_FROM_NUMBER"),
        openai_api_key=_required("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_transcribe_model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1"),
        output_dir=output_dir,
        calls_dir=calls_dir,
        reports_dir=reports_dir,
        max_turns=_int_env("MAX_TURNS", 10),
        max_call_minutes=_int_env("MAX_CALL_MINUTES", 3),
        max_call_seconds=_int_env("MAX_CALL_SECONDS", _int_env("MAX_CALL_MINUTES", 3) * 60),
    )


def assert_allowed_destination(destination_number: str) -> None:
    normalized = destination_number.replace(" ", "")
    if normalized != ALLOWED_TEST_NUMBER:
        raise ValueError(
            "Destination number is not allowed. "
            f"Only {ALLOWED_TEST_NUMBER} can be called for this challenge."
        )
