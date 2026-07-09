from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import JSONResponse, Response
from openai import OpenAI
from twilio.base.exceptions import TwilioRestException
from twilio.twiml.voice_response import Gather, VoiceResponse
import uvicorn

from src.config import assert_allowed_destination, load_settings
from src.conversation import ConversationAgent, SCENARIOS
from src.reporting import write_bug_report, write_transcript
from src.storage import SessionStore
from src.telephony import (
    build_twilio_client,
    create_outbound_call,
    download_recording_mp3,
    fetch_call_status,
    fetch_latest_recording,
)
from src.transcription import transcribe_recording_mp3, write_audio_transcript


load_dotenv()
settings = load_settings()
store = SessionStore(settings.calls_dir)
openai_client = OpenAI(api_key=settings.openai_api_key)
agent = ConversationAgent(client=openai_client, model=settings.openai_model)
twilio_client = build_twilio_client(settings.twilio_account_sid, settings.twilio_auth_token)

app = FastAPI(title="PGAI Voice Bot", version="0.1.0")

RECEIVER_PREAMBLE_TERMS = (
    "recorded for quality",
    "quality and training",
    "this call may be recorded",
)

RECEIVER_GREETING_TERMS = (
    "how may i help",
    "how can i help",
    "thanks for calling",
    "thank you for calling",
    "how can i assist",
    "how may i assist",
)


def _call_dir(call_sid: str) -> Path:
    path = settings.calls_dir / call_sid
    path.mkdir(parents=True, exist_ok=True)
    return path


def _voice_turn_response(call_sid: str, prompt: str, turn: int, initial_pause_seconds: int = 0) -> Response:
    vr = VoiceResponse()

    if initial_pause_seconds > 0:
        vr.pause(length=initial_pause_seconds)

    gather = Gather(
        input="speech",
        action=f"/voice/turn?turn={turn}",
        method="POST",
        language="en-US",
        speech_timeout="auto",
        timeout=8,
        barge_in=True,
    )
    # Put bot speech inside Gather so receiver barge-in is captured immediately.
    gather.say(prompt, voice="alice")
    vr.append(gather)
    vr.redirect(f"/voice/turn?turn={turn}")
    return Response(content=str(vr), media_type="application/xml")


def _listen_for_agent_greeting() -> Response:
    vr = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/voice/turn?turn=-1",
        method="POST",
        language="en-US",
        speech_timeout="auto",
        timeout=10,
        barge_in=True,
    )
    vr.append(gather)
    vr.redirect("/voice/turn?turn=-1")
    return Response(content=str(vr), media_type="application/xml")


def _looks_like_receiver_preamble(speech_result: str) -> bool:
    text = speech_result.lower()
    return any(term in text for term in RECEIVER_PREAMBLE_TERMS)


def _looks_like_receiver_greeting(speech_result: str) -> bool:
    text = speech_result.lower()
    return any(term in text for term in RECEIVER_GREETING_TERMS)


def _load_session(call_sid: str):
    try:
        return store.load(call_sid)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown call sid: {call_sid}") from exc


@app.post("/voice/start")
async def voice_start(CallSid: str = Form(...)):
    try:
        session = _load_session(CallSid)
    except HTTPException:
        # Twilio can hit the voice webhook immediately after call creation.
        # Return a short retry prompt instead of failing the call.
        vr = VoiceResponse()
        vr.say("One moment while I pull up my information.", voice="alice")
        vr.redirect("/voice/start")
        return Response(content=str(vr), media_type="application/xml")

    return _listen_for_agent_greeting()


@app.post("/voice/turn")
async def voice_turn(
    turn: int,
    CallSid: str = Form(...),
    SpeechResult: str | None = Form(default=None),
):
    session = _load_session(CallSid)

    if turn < 0:
        if not SpeechResult:
            return _listen_for_agent_greeting()

        # Ignore legal preambles/noise and wait until a real greeting prompt is heard.
        if _looks_like_receiver_preamble(SpeechResult) or not _looks_like_receiver_greeting(SpeechResult):
            return _listen_for_agent_greeting()

        store.append_turn(CallSid, "agent", SpeechResult)
        opening = agent.opening_for(session.scenario_id)
        store.append_turn(CallSid, "patient", opening)
        return _voice_turn_response(CallSid, opening, turn=0, initial_pause_seconds=1)

    if SpeechResult:
        store.append_turn(CallSid, "agent", SpeechResult)

    if turn + 1 >= settings.max_turns:
        vr = VoiceResponse()
        closing = "Thanks, that answers my questions for now. Have a great day."
        store.append_turn(CallSid, "patient", closing)
        vr.say(closing, voice="alice")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    transcript_turns = store.load(CallSid).turns
    reply = agent.respond(session.scenario_id, turn_index=turn + 1, transcript_turns=transcript_turns)
    store.append_turn(CallSid, "patient", reply)
    return _voice_turn_response(CallSid, reply, turn=turn + 1)


@app.post("/webhooks/call-status")
async def call_status(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
):
    try:
        store.set_status(CallSid, CallStatus)
    except FileNotFoundError:
        pass
    return JSONResponse({"ok": True})


@app.post("/webhooks/recording")
async def recording_status(
    CallSid: str = Form(...),
    RecordingSid: str = Form(...),
    RecordingUrl: str = Form(...),
):
    call_dir = _call_dir(CallSid)
    output_file = call_dir / f"recording-{CallSid}.mp3"

    try:
        download_recording_mp3(
            recording_url=RecordingUrl,
            output_path=output_file,
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
        )
        recording_file = str(output_file)
    except Exception:
        recording_file = None

    try:
        store.set_recording(
            call_sid=CallSid,
            recording_sid=RecordingSid,
            recording_url=RecordingUrl,
            recording_file=recording_file,
        )
    except FileNotFoundError:
        pass

    return JSONResponse({"ok": True})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def run_server() -> None:
    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=False)


def cmd_place_call(destination: str, scenario_id: str) -> None:
    assert_allowed_destination(destination)
    if scenario_id not in SCENARIOS:
        raise ValueError(
            f"Unknown scenario '{scenario_id}'. Available: {', '.join(sorted(SCENARIOS.keys()))}"
        )

    try:
        create_resp = create_outbound_call(
            client=twilio_client,
            from_number=settings.twilio_from_number,
            to_number=destination,
            voice_url=f"{settings.app_base_url}/voice/start",
            status_callback_url=f"{settings.app_base_url}/webhooks/call-status",
            recording_callback_url=f"{settings.app_base_url}/webhooks/recording",
            max_call_seconds=settings.max_call_seconds,
        )
    except TwilioRestException as exc:
        if getattr(exc, "code", None) == 21219:
            raise RuntimeError(
                "Twilio rejected the call because this is a trial account and the destination number is not verified. "
                "Verify +18054398008 in the Twilio console under Verified Caller IDs, or upgrade the account to place the call."
            ) from exc
        raise

    store.create(create_resp.sid, scenario_id=scenario_id, destination=destination)
    print(json.dumps({"call_sid": create_resp.sid, "scenario_id": scenario_id}, indent=2))


def cmd_batch(count: int, destination: str, spacing_seconds: int = 25) -> None:
    scenario_ids = list(SCENARIOS.keys())
    for i in range(count):
        scenario_id = scenario_ids[i % len(scenario_ids)]
        if count > len(scenario_ids):
            scenario_id = random.choice(scenario_ids)
        cmd_place_call(destination=destination, scenario_id=scenario_id)
        if i < count - 1 and spacing_seconds > 0:
            time.sleep(spacing_seconds)


def _load_all_sessions() -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for call_dir in settings.calls_dir.iterdir():
        if not call_dir.is_dir():
            continue
        session_file = call_dir / "session.json"
        if not session_file.exists():
            continue
        sessions.append(json.loads(session_file.read_text()))
    return sessions


def cmd_reconcile_calls(verbose: bool = True) -> None:
    sessions = _load_all_sessions()
    for payload in sessions:
        call_sid = payload["call_sid"]

        latest_status = fetch_call_status(twilio_client, call_sid)
        if latest_status and latest_status != payload.get("status"):
            try:
                store.set_status(call_sid, latest_status)
                if verbose:
                    print(f"updated status {call_sid}: {latest_status}")
            except FileNotFoundError:
                pass

        # If webhook was missed, try to recover recording from Twilio API.
        if payload.get("recording_file"):
            continue

        latest_recording = fetch_latest_recording(twilio_client, call_sid)
        if not latest_recording:
            continue

        recording_sid, recording_url = latest_recording
        call_dir = _call_dir(call_sid)
        output_file = call_dir / f"recording-{call_sid}.mp3"
        try:
            download_recording_mp3(
                recording_url=recording_url,
                output_path=output_file,
                account_sid=settings.twilio_account_sid,
                auth_token=settings.twilio_auth_token,
            )
            recording_file = str(output_file)
        except Exception:
            recording_file = None

        try:
            store.set_recording(
                call_sid=call_sid,
                recording_sid=recording_sid,
                recording_url=recording_url,
                recording_file=recording_file,
            )
            if verbose and recording_file:
                print(f"downloaded recording {call_sid}: {recording_file}")
        except FileNotFoundError:
            pass


def cmd_materialize_transcripts() -> None:
    cmd_reconcile_calls(verbose=False)
    sessions = _load_all_sessions()
    for payload in sessions:
        call_sid = payload["call_sid"]
        call_dir = _call_dir(call_sid)

        recording_file = payload.get("recording_file")
        if recording_file:
            recording_path = Path(recording_file)
            if recording_path.exists():
                try:
                    transcription = transcribe_recording_mp3(
                        client=openai_client,
                        recording_path=recording_path,
                        model=settings.openai_transcribe_model,
                    )
                    transcript_path = write_audio_transcript(call_dir, call_sid, transcription)
                    legacy_audio_path = call_dir / f"transcript-audio-{call_sid}.txt"
                    if legacy_audio_path.exists() and legacy_audio_path != transcript_path:
                        legacy_audio_path.unlink()

                    store.set_transcript_file(call_sid, str(transcript_path))
                    store.set_audio_transcript_file(call_sid, str(transcript_path))
                    print(f"wrote transcript (audio): {transcript_path}")
                    continue
                except Exception as exc:
                    print(f"audio transcription failed for {call_sid}, falling back to turn-log: {exc}")

        turns = payload.get("turns", [])
        transcript_path = write_transcript(call_dir, call_sid, turns)
        store.set_transcript_file(call_sid, str(transcript_path))
        print(f"wrote transcript (turn-log): {transcript_path}")


def cmd_report() -> None:
    sessions = _load_all_sessions()
    report_path = write_bug_report(
        settings.reports_dir,
        sessions,
        model_client=openai_client,
        model_name=settings.openai_model,
    )
    print(f"wrote report: {report_path}")


def cmd_transcribe_recordings() -> None:
    print("transcribe-recordings is now an alias of materialize-transcripts")
    cmd_materialize_transcripts()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pretty Good AI challenge voice bot")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="Run webhook server")

    place = sub.add_parser("place-call", help="Place one call")
    place.add_argument("--to", required=True, help="Destination number (must be +18054398008)")
    place.add_argument("--scenario", required=True, choices=sorted(SCENARIOS.keys()))

    batch = sub.add_parser("run-batch", help="Place multiple calls")
    batch.add_argument("--to", required=True, help="Destination number (must be +18054398008)")
    batch.add_argument("--count", type=int, default=10)
    batch.add_argument("--spacing-seconds", type=int, default=25)

    sub.add_parser(
        "materialize-transcripts",
        help="Write canonical transcripts (audio when recording exists, otherwise turn-log)",
    )
    sub.add_parser("reconcile-calls", help="Backfill missed call statuses and recordings from Twilio")
    sub.add_parser("transcribe-recordings", help="Alias for materialize-transcripts")
    sub.add_parser("generate-report", help="Generate bug report from sessions")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "serve":
        run_server()
        return
    if args.command == "place-call":
        cmd_place_call(destination=args.to, scenario_id=args.scenario)
        return
    if args.command == "run-batch":
        cmd_batch(count=args.count, destination=args.to, spacing_seconds=args.spacing_seconds)
        return
    if args.command == "materialize-transcripts":
        cmd_materialize_transcripts()
        return
    if args.command == "reconcile-calls":
        cmd_reconcile_calls()
        return
    if args.command == "transcribe-recordings":
        cmd_transcribe_recordings()
        return
    if args.command == "generate-report":
        cmd_report()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
