from src.reporting import detect_issues, render_transcript, write_bug_report
from pathlib import Path


def test_render_transcript_formats_lines():
    turns = [
        {"timestamp": "2026-06-30T00:00:00Z", "speaker": "patient", "text": "Hello"},
        {"timestamp": "2026-06-30T00:00:02Z", "speaker": "agent", "text": "Hi there"},
    ]
    out = render_transcript(turns)
    assert "PATIENT: Hello" in out
    assert "AGENT: Hi there" in out


def test_detect_issues_flags_weekend_schedule_pattern():
    turns = [
        {"text": "Can I come in Sunday?"},
        {"text": "Yes, you are scheduled and booked for Sunday morning."},
    ]
    findings = detect_issues(turns)
    bug_ids = {f["bug"] for f in findings}
    assert "possible_weekend_scheduling" in bug_ids
    weekend_issue = [f for f in findings if f["bug"] == "possible_weekend_scheduling"][0]
    assert "what_happened" in weekend_issue
    assert "why_problem" in weekend_issue
    assert "where_to_find" in weekend_issue


def test_detect_issues_flags_forced_profile_before_scheduling():
    turns = [
        {"speaker": "patient", "text": "I need to schedule an appointment."},
        {"speaker": "agent", "text": "Please create a profile before we can schedule."},
    ]
    findings = detect_issues(turns)
    bug_ids = {f["bug"] for f in findings}
    assert "possible_forced_profile_before_scheduling" in bug_ids


def test_detect_issues_flags_unresolved_scheduling_request():
    turns = [
        {"speaker": "patient", "text": "I want to schedule an appointment for next week."},
        {"speaker": "agent", "text": "I cannot proceed right now."},
    ]
    findings = detect_issues(turns)
    bug_ids = {f["bug"] for f in findings}
    assert "possible_unresolved_scheduling_request" in bug_ids


def test_write_bug_report_works_without_model(tmp_path: Path):
    sessions = [
        {
            "call_sid": "CA_TEST",
            "scenario_id": "appointment_simple",
            "status": "completed",
            "turns": [
                {"speaker": "patient", "text": "I need to schedule an appointment."},
                {"speaker": "agent", "text": "Please create a profile first."},
            ],
            "transcript_file": "transcript-CA_TEST.txt",
            "audio_transcript_file": "transcript-CA_TEST.txt",
            "recording_file": "recording-CA_TEST.mp3",
        }
    ]

    output = write_bug_report(tmp_path, sessions)
    payload = output.read_text()
    assert "possible_forced_profile_before_scheduling" in payload
    assert "what_happened" in payload
    assert "why_problem" in payload
    assert "where_to_find" in payload
