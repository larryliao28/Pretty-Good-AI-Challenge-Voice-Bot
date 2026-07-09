from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI


ISSUE_RULES = [
    (
        "possible_weekend_scheduling",
        "high",
        ["sunday", "saturday", "scheduled", "booked"],
        "Possible appointment confirmation on weekend. Verify office-hours logic.",
    ),
    (
        "possible_unanswered_question",
        "medium",
        ["do you accept", "insurance"],
        "Insurance acceptance may be unresolved or unclear.",
    ),
    (
        "possible_hallucinated_confirmation",
        "high",
        ["confirmed", "booked", "without", "details"],
        "Potential confirmation without collecting key details.",
    ),
    (
        "possible_forced_profile_before_scheduling",
        "high",
        ["create", "profile", "schedule"],
        "Agent appears to require profile creation before answering scheduling request.",
    ),
    (
        "possible_unresolved_scheduling_request",
        "medium",
        ["schedule", "appointment"],
        "Scheduling intent may be unresolved by the end of the call.",
    ),
]

WEEKEND_TERMS = ("saturday", "sunday")
CONFIRMATION_TERMS = ("scheduled", "booked", "confirmed")


def render_transcript(turns: list[dict[str, Any]]) -> str:
    lines = []
    for turn in turns:
        speaker = turn.get("speaker", "unknown")
        text = turn.get("text", "")
        ts = turn.get("timestamp", "")
        lines.append(f"[{ts}] {speaker.upper()}: {text}")
    return "\n".join(lines) + "\n"


def detect_issues(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    joined = "\n".join(t.get("text", "").lower() for t in turns)
    findings: list[dict[str, str]] = []
    agent_turns = [t.get("text", "").lower() for t in turns if t.get("speaker") == "agent"]
    patient_turns = [t.get("text", "").lower() for t in turns if t.get("speaker") == "patient"]

    if any(day in joined for day in WEEKEND_TERMS) and any(term in joined for term in CONFIRMATION_TERMS):
        findings.append(
            {
                "bug": "possible_weekend_scheduling",
                "severity": "high",
                "what_happened": "Agent appears to confirm a weekend appointment.",
                "why_problem": "Practice may be closed on weekends, so confirmation could be incorrect.",
                "where_to_find": "Look for Saturday/Sunday request and confirmation in the transcript.",
            }
        )

    for bug_id, severity, keywords, details in ISSUE_RULES:
        if bug_id == "possible_weekend_scheduling":
            continue
        if bug_id == "possible_forced_profile_before_scheduling":
            if (
                any("profile" in text for text in agent_turns)
                and any("schedule" in text for text in patient_turns)
            ):
                findings.append(
                    {
                        "bug": bug_id,
                        "severity": severity,
                        "what_happened": "Agent repeatedly requests profile creation before scheduling.",
                        "why_problem": "The caller's scheduling intent is blocked instead of being resolved.",
                        "where_to_find": "Find turns where agent requires profile creation after scheduling request.",
                    }
                )
            continue
        if bug_id == "possible_unresolved_scheduling_request":
            if any("schedule" in text or "appointment" in text for text in patient_turns):
                resolved = any(
                    any(term in text for term in ("booked", "confirmed", "scheduled", "available"))
                    for text in agent_turns
                )
                if not resolved:
                    findings.append(
                        {
                            "bug": bug_id,
                            "severity": severity,
                            "what_happened": "Patient asks to schedule but no concrete slot/resolution is provided.",
                            "why_problem": "The call ends without satisfying the primary user intent.",
                            "where_to_find": "Check final turns for unresolved scheduling language.",
                        }
                    )
            continue
        if all(k in joined for k in keywords):
            findings.append(
                {
                    "bug": bug_id,
                    "severity": severity,
                    "what_happened": details,
                    "why_problem": "Behavior can confuse users or produce incorrect call outcomes.",
                    "where_to_find": "Search transcript for the triggering keywords.",
                }
            )
    return findings


def detect_issues_with_model(
    client: OpenAI,
    model: str,
    turns: list[dict[str, Any]],
) -> list[dict[str, str]]:
    transcript = render_transcript(turns)
    prompt = (
        "Review this patient-agent phone transcript and identify likely agent bugs. "
        "Focus on behavior regressions, policy failures, unresolved intent, interruptions, and poor turn-taking. "
        "Return strict JSON only with this schema: "
        '{"issues":[{"bug":"string","severity":"low|medium|high","what_happened":"string","why_problem":"string","where_to_find":"string"}]}. '
        "Limit to at most 6 issues.\n\n"
        f"Transcript:\n{transcript}"
    )

    result = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a strict QA reviewer for phone-agent behavior."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=500,
    )

    content = (result.choices[0].message.content or "").strip()
    if not content:
        return []

    payload = json.loads(content)
    issues = payload.get("issues", [])
    normalized: list[dict[str, str]] = []
    for issue in issues:
        bug = str(issue.get("bug", "possible_issue")).strip() or "possible_issue"
        severity = str(issue.get("severity", "medium")).strip().lower()
        if severity not in {"low", "medium", "high"}:
            severity = "medium"
        what_happened = str(issue.get("what_happened", "Model-identified issue.")).strip() or "Model-identified issue."
        why_problem = str(issue.get("why_problem", "Potential quality/safety impact.")).strip() or "Potential quality/safety impact."
        where_to_find = str(issue.get("where_to_find", "See call transcript.")).strip() or "See call transcript."
        normalized.append(
            {
                "bug": bug,
                "severity": severity,
                "what_happened": what_happened,
                "why_problem": why_problem,
                "where_to_find": where_to_find,
            }
        )
    return normalized


def write_transcript(call_dir: Path, call_sid: str, turns: list[dict[str, Any]]) -> Path:
    text = render_transcript(turns)
    output = call_dir / f"transcript-{call_sid}.txt"
    output.write_text(text)
    return output


def write_bug_report(
    reports_dir: Path,
    sessions: list[dict[str, Any]],
    model_client: OpenAI | None = None,
    model_name: str | None = None,
) -> Path:
    report = {
        "summary": {
            "total_calls": len(sessions),
            "total_findings": 0,
        },
        "calls": [],
    }

    finding_count = 0
    for session in sessions:
        turns = session.get("turns", [])
        if model_client and model_name:
            try:
                issues = detect_issues_with_model(model_client, model_name, turns)
            except Exception:
                issues = detect_issues(turns)
        else:
            issues = detect_issues(turns)
        finding_count += len(issues)
        report["calls"].append(
            {
                "call_sid": session.get("call_sid"),
                "scenario_id": session.get("scenario_id"),
                "status": session.get("status"),
                "transcript_file": session.get("transcript_file"),
                "audio_transcript_file": session.get("audio_transcript_file"),
                "recording_file": session.get("recording_file"),
                "issues": issues,
            }
        )

    report["summary"]["total_findings"] = finding_count
    output = reports_dir / "bug-report.json"
    output.write_text(json.dumps(report, indent=2))
    return output
