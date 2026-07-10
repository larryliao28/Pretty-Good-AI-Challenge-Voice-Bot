# Pretty Good AI Challenge Voice Bot

Python voice bot for the Pretty Good AI assessment line.

## What this does
- Places outbound calls to the allowed test number only: +1-805-439-8008
- Simulates realistic patient scenarios (appointments, refill, billing, language access, urgent symptoms, edge cases)
- Stores call metadata and turn-by-turn conversation logs
- Downloads call recordings as mp3 from Twilio recording callbacks
- Reconciles missed statuses and recordings from Twilio when callbacks are delayed or missed
- Renders a canonical transcript per call (audio-derived when available, turn-log fallback)
- Generates a machine-readable bug report JSON from all calls

## Repository structure
- src/main.py: CLI + FastAPI webhooks
- src/telephony.py: Twilio call placement, recording download, and Twilio reconciliation helpers
- src/conversation.py: scenario definitions + patient response generation
- src/storage.py: session persistence under data/calls/<call_sid>/session.json
- src/reporting.py: transcript rendering + bug report generation
- ARCHITECTURE.md: architecture summary and design choices

## Prerequisites
- Python 3.11+
- Twilio account + a Twilio phone number (single caller number for all calls)
- OpenAI API key
- Public URL for webhooks (for example ngrok)

## Setup
1. Create and activate a virtual environment.
2. Install dependencies.
3. Copy `.env.example` to `.env` and fill values.
4. Start a public tunnel and set `APP_BASE_URL` to that HTTPS URL.

### Example setup commands
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run
Start webhook server:
```bash
python -m src.main serve
```

Place one call:
```bash
python -m src.main place-call --to +18054398008 --scenario appointment_simple
```

Run 10 calls (minimum submission requirement):
```bash
python -m src.main run-batch --to +18054398008 --count 10
```

Run a paced batch (recommended to reduce call failures):
```bash
python -m src.main run-batch --to +18054398008 --count 10 --spacing-seconds 25
```

Backfill missed statuses and recordings from Twilio:
```bash
python -m src.main reconcile-calls
```

Generate canonical transcript text files:
```bash
python -m src.main materialize-transcripts
```

Legacy alias (same behavior as materialize-transcripts):
```bash
python -m src.main transcribe-recordings
```

Generate bug report (model-assisted with deterministic fallback):
```bash
python -m src.main generate-report
```

Run tests:
```bash
pytest -q
```

## Scenario IDs
- appointment_simple
- reschedule
- cancel
- med_refill
- hours_and_location
- insurance
- edge_interruption
- edge_ambiguous
- new_patient_intake
- urgent_symptom_redirect
- billing_question
- referral_required
- imaging_followup
- physical_therapy_request
- medication_side_effects
- records_transfer
- language_access
- repeat_caller_identity

## Cost control notes
- Calls are hard-limited by `MAX_CALL_SECONDS` when set, otherwise `MAX_CALL_MINUTES`.
- Turn count is hard-limited by `MAX_TURNS`.
- Use `gpt-4o-mini` by default for lower cost.
- Keep scenarios concise to avoid unnecessary call duration.

## Suggested submission run profile
- `MAX_TURNS=12`
- `MAX_CALL_SECONDS=150`
- Run one canary call first, then run a paced 10-call batch.

## Output artifacts
Per call:
- data/calls/<call_sid>/session.json
- data/calls/<call_sid>/recording-<call_sid>.mp3 (when recording callback or reconciliation succeeds)
- data/calls/<call_sid>/transcript-<call_sid>.txt (canonical transcript; audio-derived when recording exists, otherwise turn-log)

Aggregate:
- data/reports/bug-report.json

Note: recording URLs stored in committed `data/calls/*/session.json` artifacts have the Twilio account identifier redacted (for example `AC_REDACTED`) to satisfy GitHub push-protection secret scanning.


## Important constraints
- The implementation validates destination number and only allows +18054398008.
- Do not commit `.env` or secrets.

## Troubleshooting
- If serve exits with address already in use, kill the process on port 8000 and restart.
- If some calls remain queued or missing mp3 files, run reconcile-calls before transcript/report generation.
- Always run CLI commands with the project virtual environment activated.

## Loom Videos
- LLM debugging session: https://www.loom.com/share/f0d942d4213949daa404098818291c73
- Project overview: https://www.loom.com/share/3dab27bb43ac4b488fe43cfa6b783ce1

