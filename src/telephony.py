from __future__ import annotations

from pathlib import Path

import httpx
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client


def build_twilio_client(account_sid: str, auth_token: str) -> Client:
    return Client(account_sid, auth_token)


def create_outbound_call(
    client: Client,
    from_number: str,
    to_number: str,
    voice_url: str,
    status_callback_url: str,
    recording_callback_url: str,
    max_call_seconds: int,
):
    return client.calls.create(
        from_=from_number,
        to=to_number,
        url=voice_url,
        method="POST",
        status_callback=status_callback_url,
        status_callback_method="POST",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
        record=True,
        recording_status_callback=recording_callback_url,
        recording_status_callback_method="POST",
        time_limit=max_call_seconds,
    )


def download_recording_mp3(recording_url: str, output_path: Path, account_sid: str, auth_token: str) -> Path:
    mp3_url = recording_url if recording_url.endswith(".mp3") else f"{recording_url}.mp3"
    with httpx.Client(timeout=60.0, follow_redirects=True, auth=(account_sid, auth_token)) as client:
        response = client.get(mp3_url)
        response.raise_for_status()
        output_path.write_bytes(response.content)
    return output_path


def fetch_call_status(client: Client, call_sid: str) -> str | None:
    try:
        call = client.calls(call_sid).fetch()
        return getattr(call, "status", None)
    except TwilioRestException:
        return None


def fetch_latest_recording(client: Client, call_sid: str) -> tuple[str, str] | None:
    try:
        recordings = client.recordings.list(call_sid=call_sid, limit=1)
    except TwilioRestException:
        return None

    if not recordings:
        return None

    recording = recordings[0]
    recording_sid = getattr(recording, "sid", None)
    recording_uri = getattr(recording, "uri", None)
    if not recording_sid or not recording_uri:
        return None

    # Convert API URI path into a full URL that can be downloaded with account auth.
    recording_url = f"https://api.twilio.com{recording_uri.rsplit('.', 1)[0]}"
    return recording_sid, recording_url
