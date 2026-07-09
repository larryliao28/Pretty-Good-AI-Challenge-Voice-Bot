from __future__ import annotations

from pathlib import Path
from typing import Any

from openai import OpenAI


def _format_seconds(seconds: float) -> str:
    total = max(0.0, float(seconds))
    mins = int(total // 60)
    secs = total - (mins * 60)
    return f"{mins:02d}:{secs:05.2f}"


def transcribe_recording_mp3(client: OpenAI, recording_path: Path, model: str) -> dict[str, Any]:
    with recording_path.open("rb") as audio_file:
        result = client.audio.transcriptions.create(
            model=model,
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    if hasattr(result, "model_dump"):
        payload = result.model_dump()
    elif isinstance(result, dict):
        payload = result
    else:
        payload = {"text": str(result)}

    segments: list[dict[str, Any]] = []
    for segment in payload.get("segments", []) or []:
        segments.append(
            {
                "start": float(segment.get("start", 0.0)),
                "end": float(segment.get("end", 0.0)),
                "text": str(segment.get("text", "")).strip(),
            }
        )

    return {
        "text": str(payload.get("text", "")).strip(),
        "segments": segments,
    }


def render_audio_transcript(transcription: dict[str, Any]) -> str:
    segments = transcription.get("segments", []) or []
    lines: list[str] = []

    if segments:
        for idx, segment in enumerate(segments, start=1):
            start = _format_seconds(segment.get("start", 0.0))
            end = _format_seconds(segment.get("end", 0.0))
            text = str(segment.get("text", "")).strip()
            lines.append(f"[{start} - {end}] SEGMENT {idx}: {text}")
    else:
        lines.append(transcription.get("text", ""))

    return "\n".join(lines).strip() + "\n"


def write_audio_transcript(call_dir: Path, call_sid: str, transcription: dict[str, Any]) -> Path:
    output = call_dir / f"transcript-{call_sid}.txt"
    output.write_text(render_audio_transcript(transcription))
    return output
