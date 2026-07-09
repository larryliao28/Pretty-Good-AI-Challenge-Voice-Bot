from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ISO = "%Y-%m-%dT%H:%M:%SZ"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime(ISO)


@dataclass
class CallSession:
    call_sid: str
    scenario_id: str
    destination: str
    status: str = "queued"
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)
    turns: list[dict[str, Any]] = field(default_factory=list)
    recording_sid: str | None = None
    recording_url: str | None = None
    recording_file: str | None = None
    transcript_file: str | None = None
    audio_transcript_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_sid": self.call_sid,
            "scenario_id": self.scenario_id,
            "destination": self.destination,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": utcnow(),
            "turns": self.turns,
            "recording_sid": self.recording_sid,
            "recording_url": self.recording_url,
            "recording_file": self.recording_file,
            "transcript_file": self.transcript_file,
            "audio_transcript_file": self.audio_transcript_file,
        }


class SessionStore:
    def __init__(self, calls_dir: Path) -> None:
        self.calls_dir = calls_dir

    def session_path(self, call_sid: str) -> Path:
        return self.calls_dir / call_sid / "session.json"

    def _ensure_dir(self, call_sid: str) -> Path:
        call_dir = self.calls_dir / call_sid
        call_dir.mkdir(parents=True, exist_ok=True)
        return call_dir

    def create(self, call_sid: str, scenario_id: str, destination: str) -> CallSession:
        self._ensure_dir(call_sid)
        session = CallSession(call_sid=call_sid, scenario_id=scenario_id, destination=destination)
        self.save(session)
        return session

    def load(self, call_sid: str) -> CallSession:
        path = self.session_path(call_sid)
        if not path.exists():
            raise FileNotFoundError(f"No session found for call sid: {call_sid}")
        payload = json.loads(path.read_text())
        return CallSession(**payload)

    def save(self, session: CallSession) -> None:
        self._ensure_dir(session.call_sid)
        path = self.session_path(session.call_sid)
        path.write_text(json.dumps(session.to_dict(), indent=2))

    def append_turn(self, call_sid: str, speaker: str, text: str) -> None:
        session = self.load(call_sid)
        session.turns.append(
            {
                "timestamp": utcnow(),
                "speaker": speaker,
                "text": text.strip(),
            }
        )
        session.updated_at = utcnow()
        self.save(session)

    def set_status(self, call_sid: str, status: str) -> None:
        session = self.load(call_sid)
        session.status = status
        session.updated_at = utcnow()
        self.save(session)

    def set_recording(self, call_sid: str, recording_sid: str, recording_url: str, recording_file: str | None = None) -> None:
        session = self.load(call_sid)
        session.recording_sid = recording_sid
        session.recording_url = recording_url
        session.recording_file = recording_file
        session.updated_at = utcnow()
        self.save(session)

    def set_transcript_file(self, call_sid: str, transcript_file: str) -> None:
        session = self.load(call_sid)
        session.transcript_file = transcript_file
        session.updated_at = utcnow()
        self.save(session)

    def set_audio_transcript_file(self, call_sid: str, transcript_file: str) -> None:
        session = self.load(call_sid)
        session.audio_transcript_file = transcript_file
        session.updated_at = utcnow()
        self.save(session)
