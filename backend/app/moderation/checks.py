import re

from backend.app.domain.community import CommunityPost
from backend.app.moderation.models import ModerationFinding

EMAIL_PATTERN = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
API_KEY_PATTERN = re.compile(r"\b(?:sk|api)[-_]?[a-z0-9]{20,}\b", re.IGNORECASE)

PII_PATTERNS = (
    "passport number",
    "\u043d\u043e\u043c\u0435\u0440 \u043f\u0430\u0441\u043f\u043e\u0440\u0442\u0430",
    "my phone",
    "\u043c\u043e\u0439 \u0442\u0435\u043b\u0435\u0444\u043e\u043d",
    "phone number",
    "email",
    "\u043f\u043e\u0447\u0442\u0430",
)

SPAM_OR_SCAM_PATTERNS = (
    "guaranteed visa",
    "100% visa",
    "send money",
    "\u043f\u0435\u0440\u0435\u0432\u0435\u0434\u0438 \u0434\u0435\u043d\u044c\u0433\u0438",
    "telegram @",
    "whatsapp",
    "crypto",
    "investment",
)

UNSAFE_WORK_ADVICE_PATTERNS = (
    "work on tourist visa",
    "start working first",
    "documents later",
    "nobody checks",
    "\u0431\u0435\u0437\u0432\u0438\u0437",
    "\u0442\u0443\u0440\u0438\u0441\u0442\u0438\u0447\u0435\u0441\u043a",
    "\u043f\u043e\u0442\u043e\u043c \u043e\u0444\u043e\u0440\u043c",
    "\u043d\u0438\u043a\u0442\u043e \u043d\u0435 \u043f\u0440\u043e\u0432\u0435\u0440",
)

LEGAL_OR_WORK_STATUS_RISK_PATTERNS = (
    "visa overstay",
    "overstay",
    "illegal work",
    "deportation",
    "\u0448\u0442\u0440\u0430\u0444",
    "\u043f\u0440\u043e\u0441\u0440\u043e\u0447\u0438\u043b",
    "\u0434\u0435\u043f\u043e\u0440\u0442\u0430\u0446",
    (
        "\u0440\u0430\u0431\u043e\u0442\u043e\u0434\u0430\u0442\u0435\u043b\u044c "
        "\u0441\u043a\u0430\u0437\u0430\u043b \u043d\u0430\u0447\u0430\u0442\u044c"
    ),
)

MEDICAL_RISK_PATTERNS = (
    "diagnose",
    "take antibiotics",
    "take medicine without doctor",
    "\u043d\u0435 \u0445\u043e\u0434\u0438 \u043a \u0432\u0440\u0430\u0447\u0443",
    "antibiotics",
    "hospital emergency",
)

EMERGENCY_MISINFORMATION_PATTERNS = (
    "don't call police",
    "do not report lost passport",
    "ignore police",
    "\u043d\u0435 \u043e\u0431\u0440\u0430\u0449\u0430\u0439\u0441\u044f "
    "\u0432 \u043f\u043e\u043b\u0438\u0446\u0438\u044e",
    "\u043d\u0435 \u0441\u043e\u043e\u0431\u0449\u0430\u0439",
    "\u0441\u043f\u0440\u044f\u0447\u044c",
)

HATE_OR_HARASSMENT_PATTERNS = (
    "hate group",
    "kill them",
    "\u0443\u0433\u0440\u043e\u0437",
    "\u043e\u0441\u043a\u043e\u0440\u0431",
)

PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "reveal system prompt",
    "reveal your system prompt",
    "show api key",
    "jailbreak",
    "disregard rules",
)


def normalize_text(text: str) -> str:
    return " ".join(text.casefold().split())


def collect_post_text(post: CommunityPost) -> str:
    parts = [
        post.title,
        post.city or "",
        post.scenario.value,
        post.language.value,
        post.situation,
        post.what_happened,
        post.what_helped or "",
        " ".join(post.required_documents),
        " ".join(post.mistakes_to_avoid),
        post.advice_for_others or "",
        " ".join(post.tags),
        post.author.self_declared_role or "",
    ]
    return "\n".join(part for part in parts if part)


def detect_pii(text: str) -> list[ModerationFinding]:
    normalized = normalize_text(text)
    matched_terms = _matched_terms(normalized, PII_PATTERNS)
    if EMAIL_PATTERN.search(text):
        matched_terms.append("email_address")
    if PHONE_PATTERN.search(text):
        matched_terms.append("phone_number")
    if API_KEY_PATTERN.search(text):
        matched_terms.append("api_key_like")
    return _finding(
        finding_type="pii",
        severity="medium",
        summary="Post may contain private contact, identity, or secret-like data.",
        matched_terms=matched_terms,
    )


def detect_spam_or_scam(text: str) -> list[ModerationFinding]:
    return _pattern_finding(
        text=text,
        patterns=SPAM_OR_SCAM_PATTERNS,
        finding_type="spam_or_scam",
        severity="high",
        summary="Post contains spam or scam-like promotion patterns.",
    )


def detect_unsafe_work_advice(text: str) -> list[ModerationFinding]:
    return _pattern_finding(
        text=text,
        patterns=UNSAFE_WORK_ADVICE_PATTERNS,
        finding_type="unsafe_work_advice",
        severity="high",
        summary="Post contains unsafe work-status advice markers.",
    )


def detect_legal_or_work_status_risk(text: str) -> list[ModerationFinding]:
    return _pattern_finding(
        text=text,
        patterns=LEGAL_OR_WORK_STATUS_RISK_PATTERNS,
        finding_type="legal_or_work_status_risk",
        severity="medium",
        summary="Post discusses legal, visa, deportation, or work-status risk.",
    )


def detect_medical_risk(text: str) -> list[ModerationFinding]:
    return _pattern_finding(
        text=text,
        patterns=MEDICAL_RISK_PATTERNS,
        finding_type="medical_risk",
        severity="high",
        summary="Post contains medical advice or urgent medical risk markers.",
    )


def detect_emergency_misinformation(text: str) -> list[ModerationFinding]:
    return _pattern_finding(
        text=text,
        patterns=EMERGENCY_MISINFORMATION_PATTERNS,
        finding_type="emergency_misinformation",
        severity="high",
        summary="Post contains emergency misinformation or reporting avoidance markers.",
    )


def detect_hate_or_harassment(text: str) -> list[ModerationFinding]:
    return _pattern_finding(
        text=text,
        patterns=HATE_OR_HARASSMENT_PATTERNS,
        finding_type="hate_or_harassment",
        severity="high",
        summary="Post contains hate, threat, or harassment markers.",
    )


def detect_prompt_injection(text: str) -> list[ModerationFinding]:
    return _pattern_finding(
        text=text,
        patterns=PROMPT_INJECTION_PATTERNS,
        finding_type="prompt_injection",
        severity="high",
        summary="Post contains prompt-injection instructions.",
    )


def _pattern_finding(
    text: str,
    patterns: tuple[str, ...],
    finding_type: str,
    severity: str,
    summary: str,
) -> list[ModerationFinding]:
    matched_terms = _matched_terms(normalize_text(text), patterns)
    return _finding(
        finding_type=finding_type,
        severity=severity,
        summary=summary,
        matched_terms=matched_terms,
    )


def _matched_terms(normalized_text: str, patterns: tuple[str, ...]) -> list[str]:
    return [pattern for pattern in patterns if pattern in normalized_text]


def _finding(
    finding_type: str,
    severity: str,
    summary: str,
    matched_terms: list[str],
) -> list[ModerationFinding]:
    if not matched_terms:
        return []
    return [
        ModerationFinding(
            finding_type=finding_type,
            severity=severity,
            summary=summary,
            matched_terms=list(dict.fromkeys(matched_terms)),
        )
    ]
