from backend.app.domain.enums import RiskLevel, UserScenario
from backend.app.llm.models import LLMMessage


def build_system_prompt_for_scenario(
    scenario: UserScenario,
    risk_level: RiskLevel,
) -> str:
    scenario_guidance = []
    if scenario == UserScenario.kazakhstan_entry:
        scenario_guidance.extend(
            [
                "For travel to Kazakhstan, establish the traveller's citizenship, passport "
                "type, purpose, intended entry and exit dates, and planned stay length. "
                "Never ask for passport numbers.",
                "Do not apply China entry rules to Kazakhstan. Do not infer visa-free "
                "eligibility, e-Visa access, or work/study/residence permission without a "
                "published official source that matches the traveller's exact conditions.",
                "If any required trip details or official evidence are missing, ask a concise "
                "clarification or direct the user to Kazakhstan's official visa and migration "
                "services instead of guessing.",
            ]
        )
    return "\n".join(
        [
            "You are QminiGuide.",
            f"Scenario: {scenario.value}.",
            f"Risk level: {risk_level.value}.",
            "Follow the source hierarchy: official sources, curated guides, verified "
            "institutional experience, verified practical experience, ordinary approved "
            "community experience, then untrusted sources.",
            "Do not fabricate legal, immigration, medical, emergency, or source claims.",
            "Separate official information from community or contributor experience.",
            "For high-risk cases, use cautious language and recommend human or official "
            "confirmation.",
            *scenario_guidance,
        ]
    )


def build_messages(
    system_prompt: str,
    user_message: str,
    context: str | None = None,
) -> list[LLMMessage]:
    messages = [LLMMessage(role="system", content=system_prompt)]
    if context:
        messages.append(LLMMessage(role="system", content=f"Context:\n{context}"))
    messages.append(LLMMessage(role="user", content=user_message))
    return messages
