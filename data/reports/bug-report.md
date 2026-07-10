# Bug Report (Curated High-Impact Findings)

## Scope
- Calls reviewed: 13 completed calls with recordings and canonical transcripts.
- Evidence sources: `data/calls/*/transcript-<call_sid>.txt` plus existing JSON findings.
- Method: prioritize safety, task-completion, and trust-impacting defects over minor phrasing issues.

## Executive Summary
The strongest issues are not cosmetic. They are workflow and reasoning failures that can block user intent or create unsafe outcomes:
1. Safety triage is delayed by rigid identity verification.
2. The agent can ignore corrected constraints and keep repeating stale answers.
3. Scheduling constraints (e.g., afternoon only) are not consistently respected.
4. Location/details are inconsistent across calls, reducing trust.

---

## Findings

### 1) Urgent-symptom triage delayed by DOB gating
- Bug: Urgent care risk is raised by caller, but agent repeatedly requests DOB before triage guidance.
- Severity: High
- Call: `transcript-CAa1216ad1053d3465d70338b53c27eb0e.txt`
- Where to find:
  - [00:18.04 - 00:24.04] caller reports worsening knee pain overnight.
  - [00:33.72 - 00:43.08] agent asks DOB twice before clinical direction.
- What happened: The conversation enters identity-verification steps before immediate triage advice.
- Why this is a problem: In urgent symptom scenarios, delayed guidance can create safety risk and poor user experience.
- Suggested fix: Add a safety-first branch: if pain is severe/worsening, provide immediate escalation guidance first, then collect identity details.

### 2) Agent does not recover after user corrects date context
- Bug: User requests an October appointment; agent keeps repeating July 8 availability.
- Severity: High
- Call: `transcript-CA309161b166b140b17684a6b4afd7b2d3.txt`
- Where to find:
  - [02:18.40 - 02:21.92] user explicitly asks for October.
  - [02:21.92 - 02:29.44] agent repeats July 7/July 8 framing.
- What happened: The model ignores an explicit context correction and returns stale answer pattern.
- Why this is a problem: Indicates weak state update logic and poor repair behavior after user correction.
- Suggested fix: Add constraint reconciliation step each turn (extract latest requested date/time window and force candidate responses to satisfy it).

### 3) Requested scheduling constraints not followed (afternoon preference)
- Bug: Caller asks for weekday afternoon; agent offers Monday 10:30 AM among options.
- Severity: Medium
- Call: `transcript-CA412ac4480b957acb0fe959aa21d0c9f4.txt`
- Where to find:
  - [01:41.76 - 01:46.60] user asks weekday afternoon options.
  - [01:56.36 - 02:01.88] agent offers Monday 10:30 AM (morning) as "next available".
- What happened: Candidate options violate stated time preference.
- Why this is a problem: Constraint violations reduce trust and increase back-and-forth.
- Suggested fix: Add hard filter in response planning: if user says afternoon, only return afternoon options first.

### 4) Inconsistent facility/location details across calls
- Bug: Location details conflict between calls.
- Severity: High
- Calls:
  - `transcript-CA3a88a68ef69b91408be898a57b2ce091.txt` (Austin, 1234 Recovery Way)
  - `transcript-CA412ac4480b957acb0fe959aa21d0c9f4.txt` ("Nashville 220 Athens Way")
- Where to find:
  - Hours/location call: [00:35.66 - 00:40.80], [00:45.44 - 00:51.88], [01:20.16 - 01:26.30]
  - Reschedule call: [00:52.24 - 00:55.64]
- What happened: The system provides materially different clinic address/city information.
- Why this is a problem: Operationally critical data inconsistency can misdirect patients and harm credibility.
- Suggested fix: Move all clinic metadata (address, phone, hours, providers) to a fixed knowledge source and disallow free-form generation for these fields.

### 5) "Evening" slot semantics are ambiguous/inconsistent
- Bug: Agent labels 12 PM-7 PM as evening availability.
- Severity: Medium
- Call: `transcript-CA932cd767e1ee3c573e6596cb17d5893e.txt`
- Where to find:
  - [00:25.24 - 00:31.12] and [02:10.32 - 02:16.40]
  - User flags ambiguity at [02:18.72 - 02:25.24]
- What happened: The response mixes noon and evening language without clear slot boundaries.
- Why this is a problem: Users can misbook due to ambiguous time-of-day definitions.
- Suggested fix: Normalize time buckets (e.g., afternoon 12-5, evening 5-8) and present options in explicit ranges.

---

## Prioritized Remediation Plan
1. Safety-first interrupt policy for urgent symptoms before identity verification.
2. Constraint-tracking layer (latest user constraints override stale context).
3. Structured backend for non-generative factual data (location/hours/provider details).
4. Time-bucket normalization for schedule wording (afternoon/evening).

## Notes
- This report intentionally excludes minor transcript artifacts and focuses on user-impacting defects likely to matter in evaluation.
- The highest-value wins for next iteration are #1, #2, and #4.