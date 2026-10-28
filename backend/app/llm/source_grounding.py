from pydantic import BaseModel, Field

from backend.app.llm.models import LLMMessage, LLMRequest


class SourceContextItem(BaseModel):
    source_id: str
    title: str
    source_type: str
    trust_level: str
    excerpt: str
    url: str | None = None
    published_at: str | None = None
    language: str | None = None


class SourceGroundingPolicy(BaseModel):
    require_source_for_official_claims: bool = True
    allow_general_safety_guidance_without_source: bool = True
    forbid_unsourced_phone_numbers: bool = True
    forbid_unsourced_addresses: bool = True
    forbid_unsourced_legal_requirements: bool = True
    forbid_unsourced_medical_instructions: bool = True
    require_uncertainty_when_sources_missing: bool = True
    require_sensitive_domain_disclaimer: bool = True


class GroundedPromptPack(BaseModel):
    system_prompt: str
    context_block: str
    user_prompt: str
    source_count: int
    warnings: list[str] = Field(default_factory=list)


def build_source_hierarchy_prompt(
    policy: SourceGroundingPolicy | None = None,
) -> str:
    active_policy = policy or SourceGroundingPolicy()
    rules = [
        "Source hierarchy: official published sources > curated guides based on official "
        "sources > verified institutional contributors > verified experienced contributors "
        "> approved ordinary community posts.",
        "Official published sources outrank individual comments, including consul or "
        "consular worker comments.",
        "Community content may be described only as practical experience, not official law.",
        "Pending, rejected, flagged, unsafe, retrieval-disallowed, or unverified content must "
        "not be treated as source context.",
    ]
    if active_policy.require_source_for_official_claims:
        rules.append("Make official factual claims only when they are supported by source context.")
    if active_policy.forbid_unsourced_phone_numbers:
        rules.append("Do not invent or provide unsourced phone numbers.")
    if active_policy.forbid_unsourced_addresses:
        rules.append("Do not invent or provide unsourced addresses.")
    if active_policy.forbid_unsourced_legal_requirements:
        rules.append(
            "Do not fabricate laws, visa rules, document requirements, deadlines, or official "
            "procedures."
        )
    if active_policy.forbid_unsourced_medical_instructions:
        rules.append("Do not fabricate medical instructions or treatment advice.")
    return "\n".join(f"- {rule}" for rule in rules)


def format_source_context(items: list[SourceContextItem]) -> str:
    if not items:
        return (
            "No trusted source context was provided. The answer must limit itself to general "
            "safety-oriented next steps, identify uncertain points, and recommend official "
            "verification."
        )

    formatted_items = []
    for index, item in enumerate(items, start=1):
        metadata = [
            f"source_id={item.source_id}",
            f"title={item.title}",
            f"source_type={item.source_type}",
            f"trust_level={item.trust_level}",
        ]
        if item.url:
            metadata.append(f"url={item.url}")
        if item.published_at:
            metadata.append(f"published_at={item.published_at}")
        if item.language:
            metadata.append(f"language={item.language}")
        formatted_items.append(
            "\n".join(
                [
                    f"[Source {index}]",
                    "; ".join(metadata),
                    f"excerpt: {item.excerpt}",
                ]
            )
        )
    return "\n\n".join(formatted_items)


def build_grounded_system_prompt(
    policy: SourceGroundingPolicy | None = None,
) -> str:
    active_policy = policy or SourceGroundingPolicy()
    lines = [
        "You are QminiGuide.",
        build_source_hierarchy_prompt(active_policy),
        "Use the provided source context as the only basis for official facts.",
        "If source context is missing or insufficient, say what is uncertain instead of "
        "guessing.",
        "Separate source-grounded facts from practical next steps, and label uncertainty "
        "clearly.",
        "Use this answer structure: Direct short answer, Source-grounded facts, Practical "
        "next steps, Checklist if useful, Unverified or uncertain points, When to escalate, "
        "and Source notes.",
        "For emergency, document, police, visa, work, or medical topics, be cautious and "
        "recommend official or qualified human escalation.",
    ]
    if active_policy.allow_general_safety_guidance_without_source:
        lines.append(
            "General safety-oriented next steps are allowed without source context, but "
            "official details still require verification."
        )
    if active_policy.require_sensitive_domain_disclaimer:
        lines.append(
            "Include this disclaimer for sensitive domains: this is not certified legal, "
            "medical, immigration, emergency, or translation advice."
        )
    return "\n".join(lines)


def build_grounded_prompt_pack(
    user_message: str,
    source_context: list[SourceContextItem] | None = None,
    policy: SourceGroundingPolicy | None = None,
    user_profile_context: str | None = None,
) -> GroundedPromptPack:
    active_sources = source_context or []
    warnings: list[str] = []
    if not active_sources:
        warnings.append(
            "No trusted source context supplied; answer must avoid official factual claims "
            "and recommend official verification."
        )

    context_parts = ["Trusted source context:", format_source_context(active_sources)]
    if user_profile_context:
        context_parts.extend(["User/profile context:", user_profile_context])

    user_prompt = "\n".join(
        [
            "User request:",
            user_message,
            "",
            "Answer using these headings exactly:",
            "1. Direct short answer",
            "2. Source-grounded facts",
            "3. Practical next steps",
            "4. Checklist, if applicable",
            "5. Unverified or uncertain points",
            "6. When to escalate",
            "7. Source notes",
        ]
    )

    return GroundedPromptPack(
        system_prompt=build_grounded_system_prompt(policy),
        context_block="\n".join(context_parts),
        user_prompt=user_prompt,
        source_count=len(active_sources),
        warnings=warnings,
    )


def build_grounded_llm_request(
    user_message: str,
    source_context: list[SourceContextItem] | None = None,
    policy: SourceGroundingPolicy | None = None,
    user_profile_context: str | None = None,
    model: str = "mock-qazaqchina-local",
    max_tokens: int = 600,
    temperature: float = 0.0,
) -> LLMRequest:
    prompt_pack = build_grounded_prompt_pack(
        user_message=user_message,
        source_context=source_context,
        policy=policy,
        user_profile_context=user_profile_context,
    )
    return LLMRequest(
        messages=[
            LLMMessage(role="system", content=prompt_pack.system_prompt),
            LLMMessage(role="system", content=prompt_pack.context_block),
            LLMMessage(role="user", content=prompt_pack.user_prompt),
        ],
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        metadata={"mode": "source_grounded_manual_chat"},
    )
