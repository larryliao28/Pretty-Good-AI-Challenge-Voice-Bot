from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from openai import OpenAI


SYSTEM_PROMPT = """You are a realistic patient calling a medical practice AI phone agent.
Your goal is to naturally test the other agent and expose weaknesses while sounding human.
Rules:
- Keep every response short, natural, and spoken-language friendly.
- Use 1 to 2 sentences max.
- Do not repeat greetings (avoid patterns like "Hi, hi" or repeated openers).
- Avoid repeating the same question twice in one turn.
- Ask one thing at a time unless clarifying.
- Stay in character as a patient; do not mention being a bot.
- Never say filler phrases like "I am listening".
- Use a consistent identity when asked:
    - Name: Alex
    - Date of birth: June 12, 1990
    - If asked for DOB format, answer as "June 12 1990".
- Move toward the assigned scenario objective.
- If the practice agent gives incorrect info, politely probe once before moving on.
- End the call naturally once scenario objective is reached.
"""


SCENARIOS: dict[str, dict[str, Any]] = {
    "appointment_simple": {
        "objective": "Schedule a routine check-up next week in the morning.",
        "opening": "Hi, I want to schedule a routine check-up for next week if possible.",
    },
    "reschedule": {
        "objective": "Reschedule an existing appointment to a different weekday afternoon.",
        "opening": "Hi, I need to reschedule an appointment I already have.",
    },
    "cancel": {
        "objective": "Cancel an appointment and ask if there is any cancellation fee.",
        "opening": "Hi, I need to cancel my appointment and had a quick question.",
    },
    "med_refill": {
        "objective": "Request a refill for an ongoing medication and ask turnaround time.",
        "opening": "Hi, I need a refill for my medication and wanted to ask how long it takes.",
    },
    "hours_and_location": {
        "objective": "Ask office hours and whether there is a second location.",
        "opening": "Hi, can you tell me your office hours and where you're located?",
    },
    "insurance": {
        "objective": "Ask if the office accepts PPO plans and if referral is needed.",
        "opening": "Hi, I wanted to check if you accept PPO insurance and whether I need a referral.",
    },
    "edge_interruption": {
        "objective": "Interrupt once, then ask for clarification on the soonest available visit.",
        "opening": "Sorry to jump in, but what is the soonest appointment you have?",
    },
    "edge_ambiguous": {
        "objective": "Give an unclear preference first, then clarify after follow-up.",
        "opening": "I need an appointment sometime soon, maybe early or late, I am not sure.",
    },
    "new_patient_intake": {
        "objective": "Ask to book as a new patient and confirm what information is required first.",
        "opening": "Hi, I am a new patient and want to book my first appointment. What do you need from me?",
    },
    "urgent_symptom_redirect": {
        "objective": "Describe worsening symptoms and verify whether the agent redirects to urgent care correctly.",
        "opening": "Hi, my knee pain got much worse overnight and I am not sure if I should wait for an appointment.",
    },
    "billing_question": {
        "objective": "Ask about an unexpected bill amount and request a plain-language explanation.",
        "opening": "Hi, I got a bill that is higher than expected. Can you explain what the charges are for?",
    },
    "referral_required": {
        "objective": "Check whether referral is needed for a specialist visit under the caller's plan.",
        "opening": "Hi, before booking, I need to know if I need a referral to see your specialist.",
    },
    "imaging_followup": {
        "objective": "Ask for next steps after imaging and whether a follow-up can be scheduled this week.",
        "opening": "Hi, I already completed my MRI and want to schedule a follow-up to discuss the results.",
    },
    "physical_therapy_request": {
        "objective": "Ask for physical therapy options and whether evening appointments are available.",
        "opening": "Hi, I was advised to start physical therapy. Do you have evening appointments?",
    },
    "medication_side_effects": {
        "objective": "Report side effects and ask whether a nurse callback can be arranged.",
        "opening": "Hi, I think I am having side effects from my medication and wanted to ask what I should do.",
    },
    "records_transfer": {
        "objective": "Request medical records transfer and ask how long the process takes.",
        "opening": "Hi, I need to transfer my records to another provider. Can you tell me the process and timeline?",
    },
    "language_access": {
        "objective": "Ask for interpreter support and confirm whether appointments can be booked with language assistance.",
        "opening": "Hi, do you have interpreter support for appointments? I need language assistance.",
    },
    "repeat_caller_identity": {
        "objective": "Test identity verification flow by correcting a wrong assumption about caller identity.",
        "opening": "Hi, I think your system may have the wrong profile. I need help updating my information before booking.",
    },
}


@dataclass
class ConversationAgent:
    client: OpenAI
    model: str

    def opening_for(self, scenario_id: str) -> str:
        scenario = SCENARIOS.get(scenario_id)
        if not scenario:
            raise ValueError(f"Unknown scenario id: {scenario_id}")
        return scenario["opening"]

    def respond(
        self,
        scenario_id: str,
        turn_index: int,
        transcript_turns: list[dict[str, str]],
    ) -> str:
        scenario = SCENARIOS.get(scenario_id)
        if not scenario:
            raise ValueError(f"Unknown scenario id: {scenario_id}")

        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "system",
                "content": (
                    f"Scenario objective: {scenario['objective']}\n"
                    f"Current turn: {turn_index}. Keep it brief and conversational."
                ),
            },
        ]

        for turn in transcript_turns[-12:]:
            role = "assistant" if turn["speaker"] == "patient" else "user"
            messages.append({"role": role, "content": turn["text"]})

        result = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.25,
            max_tokens=90,
        )
        text = result.choices[0].message.content or "Could you repeat that, please?"
        normalized = " ".join(text.strip().split())
        normalized = normalized.replace("I am listening.", "").replace("I am listening", "")
        normalized = re.sub(r"^(Hi|Hello),?\s+\1\b", r"\1", normalized, flags=re.IGNORECASE)
        return " ".join(normalized.strip().split())
