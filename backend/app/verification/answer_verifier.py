import re
from typing import Any

from backend.app.cloud_ai.grounded_review import BoundClaimReview
from backend.app.domain.sources import Citation, retrieval_status_allowed
from backend.app.verification.models import (
    AnswerVerificationReport,
    AnswerVerificationRequest,
    VerificationIssue,
)

SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}

OFFICIAL_OR_CURATED_SOURCE_TYPES = {"official", "curated_guide"}
TRUSTED_SOURCE_TYPES = {
    "official",
    "curated_guide",
    "verified_institutional_contributor",
    "verified_experienced_contributor",
    "ordinary_community",
}
COMMUNITY_SOURCE_TYPES = {
    "verified_institutional_contributor",
    "verified_experienced_contributor",
    "ordinary_community",
}
UNTRUSTED_SOURCE_TYPES = {
    "untrusted",
    "candidate",
    "source_candidate",
    "unreviewed_candidate",
    "unreviewed_web_candidate",
    "web_candidate",
    "pending_candidate",
}
UNTRUSTED_LEVELS = {"level_6_untrusted", "untrusted", "unreviewed_candidate"}
UNREVIEWED_STATUSES = {"pending", "needs_review", "rejected", "flagged"}

HIGH_RISK_LEVELS = {
    "high",
    "legal_sensitive",
    "work_status_sensitive",
    "medical_sensitive",
    "emergency",
    "unsafe",
    "prompt_injection",
}
HIGH_RISK_HINTS = {
    "passport",
    "document",
    "visa",
    "overstay",
    "registration",
    "work",
    "medical",
    "hospital",
    "police",
    "emergency",
}
SENSITIVE_DOMAIN_TERMS = {
    "виз",
    "паспорт",
    "разрешен",
    "регистрац",
    "работ",
    "лечени",
    "лекарств",
    "виза",
    "тіркеу",
    "жұмыс",
    "емдеу",
    "дәрі",
    "签证",
    "护照",
    "居留",
    "登记",
    "工作",
    "治疗",
    "药",
    "passport",
    "visa",
    "permit",
    "residence",
    "registration",
    "police",
    "immigration",
    "public security",
    "embassy",
    "consulate",
    "work",
    "contract",
    "medical",
    "hospital",
    "doctor",
    "law",
    "legal",
    "administrative",
}
CLAIM_TERMS = {
    "обязан",
    "обязательно",
    "разрешено",
    "можно работать",
    "законно",
    "запрещено",
    "міндетті",
    "рұқсат етіледі",
    "жұмыс істеуге болады",
    "必须",
    "允许",
    "可以合法",
    "可以工作",
    "违法",
    "must",
    "have to",
    "need to",
    "required to",
    "requires",
    "mandatory",
    "allowed to",
    "can legally",
    "cannot legally",
    "is illegal",
    "is legal",
    "is valid",
    "is invalid",
    "fine of",
    "penalty is",
}
OFFICIAL_ACTION_TERMS = {
    "работ",
    "оплат",
    "подать",
    "тірке",
    "жұмыс",
    "төле",
    "工作",
    "登记",
    "申请",
    "缴",
    "支付",
    "治疗",
    "服药",
    "report",
    "submit",
    "register",
    "apply",
    "obtain",
    "pay",
    "leave",
    "start work",
    "work",
    "file",
    "present",
    "bring",
}
UNCERTAINTY_TERMS = {
    "уточн",
    "проверь",
    "проверить",
    "не подтвержден",
    "могут отличаться",
    "нақты",
    "тексер",
    "расталмаған",
    "核实",
    "确认",
    "无法确认",
    "可能不同",
    "verify",
    "confirm",
    "check",
    "may vary",
    "can change",
    "source coverage",
    "limited",
    "i do not have",
    "i don't have",
    "current requirement",
    "current official",
    "before acting",
    "not legal advice",
    "not medical advice",
    "qualified",
}
ESCALATION_TERMS = {
    "официаль",
    "консуль",
    "врач",
    "человек",
    "экстрен",
    "сроч",
    "ресми",
    "дәрігер",
    "консул",
    "маман",
    "шұғыл",
    "官方",
    "领事",
    "医生",
    "人工",
    "紧急",
    "急救",
    "official",
    "consulate",
    "embassy",
    "police",
    "hospital",
    "emergency",
    "qualified",
    "human",
    "local authority",
    "public security",
    "immigration",
    "doctor",
    "lawyer",
}

PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[\s().-]*)?(?:\d[\s().-]*){7,}\d")
ADDRESS_PATTERNS = [
    re.compile(
        r"\b\d{1,5}\s+[A-Z][A-Za-z0-9.' -]{2,60}\s+"
        r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Boulevard|Blvd|District|Building|Room)\b"
    ),
    re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,40}(?:路|街|大道|巷)\s*\d{1,5}\s*号?"),
]
DEADLINE_PATTERNS = [
    re.compile(r"\b\d+\s+(?:hours?|days?|weeks?|months?)\b", re.I),
    re.compile(
        r"\b\d+\s*(?:час(?:а|ов)?|дн(?:я|ей)|день|недел\w*|месяц\w*|сағат|күн|апта|ай)\b", re.I
    ),
    re.compile(r"\d+\s*(?:个工作日|工作日|小时|天|周|个月)"),
    re.compile(r"\bwithin\s+\d{1,3}\s+(?:hours?|days?|weeks?|months?)\b", re.I),
    re.compile(r"\b(?:by|before)\s+\d{4}-\d{1,2}-\d{1,2}\b", re.I),
    re.compile(
        r"\b(?:by|before)\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
        r"[a-z]*\s+\d{1,2}(?:,\s*\d{4})?\b",
        re.I,
    ),
]
FEE_PATTERNS = [
    re.compile(r"\d+(?:[.,]\d+)?\s*(?:元|人民币|юан\w*|рубл\w*|теңге)", re.I),
    re.compile(r"(?:RMB|CNY|USD|HKD|\$|¥)\s?\d+(?:\.\d{2})?", re.I),
    re.compile(r"\b\d+(?:\.\d{2})?\s?(?:RMB|CNY|yuan|USD|dollars?)\b", re.I),
]
LEGAL_REQUIREMENT_PATTERN = re.compile(
    r"\b(?:must|required to|mandatory to|have to|need to)\s+"
    r"(?:report|register|submit|apply|obtain|leave|pay|start work|work|file|present)\b",
    re.I,
)


def build_answer_verification_request(
    answer_text: str,
    scenario: str | None = None,
    risk_level: str | None = None,
    domain: str | None = None,
    evidence: list | None = None,
    source_notes: list | None = None,
    unreviewed_candidate_count: int = 0,
    coverage_warnings: list[str] | None = None,
) -> AnswerVerificationRequest:
    return AnswerVerificationRequest(
        answer_text=answer_text,
        scenario=scenario,
        risk_level=risk_level,
        domain=domain,
        evidence=[_to_plain_dict(item) for item in evidence or []],
        source_notes=[_to_plain_dict(item) for item in source_notes or []],
        unreviewed_candidate_count=max(0, int(unreviewed_candidate_count or 0)),
        coverage_warnings=list(coverage_warnings or []),
    )


def verify_answer(
    request: AnswerVerificationRequest, *, reviewed_claims: BoundClaimReview | None = None,
    citations: list[Citation] | None = None,
) -> AnswerVerificationReport:
    issues: list[VerificationIssue] = []
    answer_text = request.answer_text.strip()
    bound_review = None
    if reviewed_claims is not None:
        if type(reviewed_claims) is BoundClaimReview and reviewed_claims.valid_for(
            request.answer_text, request.evidence, citations or [], risk_level=request.risk_level,
        ):
            bound_review = reviewed_claims
        else:
            issues.append(VerificationIssue(
                severity="error", code="semantic_review_binding_invalid",
                message="The reviewed claims no longer match the answer, citations or evidence.",
            ))

    if _is_missing_answer(answer_text):
        issues.append(
            VerificationIssue(
                severity="error",
                code="missing_answer",
                message="Answer is empty or too short to contain a direct answer.",
                suggested_action="Add a short direct answer before details.",
            )
        )

    high_risk = is_high_risk_verification_context(
        request.scenario,
        request.risk_level,
        request.domain,
    )
    if high_risk and not answer_has_escalation_language(answer_text):
        issues.append(
            VerificationIssue(
                severity="error",
                code="high_risk_missing_escalation",
                message=(
                    "High-risk answer does not point the user to official, emergency, "
                    "medical, legal, or qualified human help."
                ),
                suggested_action="Add official or qualified-human escalation guidance.",
            )
        )
    if high_risk and not answer_has_uncertainty_language(answer_text):
        issues.append(
            VerificationIssue(
                severity="warning",
                code="high_risk_missing_uncertainty",
                message=(
                    "High-risk answer lacks clear uncertainty or current-source "
                    "verification language."
                ),
                suggested_action="Add wording that sensitive details must be verified.",
            )
        )

    issues.extend(source_notes_reference_only_evidence(request.source_notes, request.evidence))
    issues.extend(
        detect_unreviewed_candidate_citation(
            request.answer_text,
            request.source_notes,
            request.unreviewed_candidate_count,
        )
    )

    sensitive_claims = detect_sensitive_claim_patterns(answer_text)
    unsupported_sensitive_claims = [
        claim
        for claim in sensitive_claims
        if not evidence_contains_terms(request.evidence, [_claim_body(claim)])
        and not _review_supports_sentence(bound_review, claim)
    ]
    if unsupported_sensitive_claims:
        issues.append(
            VerificationIssue(
                severity="error",
                code="unsupported_official_claim",
                message=(
                    "Answer appears to make official, legal, administrative, work, "
                    "passport, visa, or medical claims not supported by official/curated evidence."
                ),
                suggested_action=(
                    "Use official or curated evidence, or rewrite as uncertainty and "
                    "official-verification guidance."
                ),
            )
        )

    unsupported_details = [
        detail
        for detail in detect_exact_detail_patterns(answer_text)
        if not evidence_contains_terms(request.evidence, [detail])
        and not _review_supports_detail(bound_review, answer_text, detail)
    ]
    for detail in unsupported_details:
        issues.append(
            VerificationIssue(
                severity="error",
                code="unsupported_exact_detail",
                message=(
                    "An exact detail is not present in trusted evidence; its value is withheld."
                ),
                suggested_action="Remove the exact detail or support it with trusted evidence.",
            )
        )

    for warning in request.coverage_warnings:
        if str(warning).strip():
            issues.append(
                VerificationIssue(
                    severity="warning",
                    code="coverage_warning",
                    message=str(warning).strip(),
                    suggested_action="Keep uncertainty language and prefer stronger evidence.",
                )
            )

    unsupported_claim_count = sum(
        1
        for issue in issues
        if issue.code in {"unsupported_official_claim", "unsupported_exact_detail"}
    )
    max_severity = _max_severity(issues)
    return AnswerVerificationReport(
        passed=max_severity != "error",
        max_severity=max_severity,
        scenario=request.scenario,
        risk_level=request.risk_level,
        domain=request.domain,
        evidence_count=len(request.evidence),
        trusted_source_count=len(trusted_evidence_source_ids(request.evidence)),
        source_note_count=len(request.source_notes),
        unreviewed_candidate_count=request.unreviewed_candidate_count,
        unsupported_claim_count=unsupported_claim_count,
        issues=issues,
    )


def verification_report_to_jsonable(report: AnswerVerificationReport) -> dict:
    return report.model_dump(mode="json")


def verification_report_to_markdown(report: AnswerVerificationReport) -> str:
    lines = [
        "# Answer Verification Report",
        "",
        f"- Passed: {report.passed}",
        f"- Max severity: {report.max_severity}",
        f"- Scenario: {report.scenario or 'unspecified'}",
        f"- Risk level: {report.risk_level or 'unspecified'}",
        f"- Domain: {report.domain or 'unspecified'}",
        f"- Evidence count: {report.evidence_count}",
        f"- Trusted source count: {report.trusted_source_count}",
        f"- Source note count: {report.source_note_count}",
        f"- Unreviewed candidate count: {report.unreviewed_candidate_count}",
        f"- Unsupported claim count: {report.unsupported_claim_count}",
        "",
        "## Issues",
    ]
    if not report.issues:
        lines.append("- None")
    else:
        for issue in report.issues:
            source_text = f" source={issue.source_id}" if issue.source_id else ""
            action_text = (
                f" Suggested action: {issue.suggested_action}" if issue.suggested_action else ""
            )
            lines.append(
                f"- {issue.severity.upper()} {issue.code}:{source_text} "
                f"{issue.message}{action_text}"
            )
    return "\n".join(lines) + "\n"


def is_high_risk_verification_context(
    scenario: str | None,
    risk_level: str | None,
    domain: str | None,
) -> bool:
    if _normalize_token(risk_level) in HIGH_RISK_LEVELS:
        return True
    combined = _normalize_text(" ".join(part or "" for part in [scenario, domain]))
    return any(hint in combined for hint in HIGH_RISK_HINTS)


def evidence_source_ids(evidence: list[dict]) -> set[str]:
    return {
        source_id for item in evidence if (source_id := _source_id(item)) and source_id != "unknown"
    }


def trusted_evidence_source_ids(evidence: list[dict]) -> set[str]:
    return {
        source_id
        for item in evidence
        if (source_id := _source_id(item)) and _is_trusted_evidence(item)
    }


def source_notes_reference_only_evidence(
    source_notes: list[dict],
    evidence: list[dict],
) -> list[VerificationIssue]:
    known_ids = evidence_source_ids(evidence)
    trusted_ids = trusted_evidence_source_ids(evidence)
    issues: list[VerificationIssue] = []
    for note in source_notes:
        source_id = _source_id(note)
        if not source_id or source_id == "unknown":
            continue
        if source_id not in known_ids:
            issues.append(
                VerificationIssue(
                    severity="error",
                    code="unknown_source_note",
                    message="Source note references a source ID that is not in evidence.",
                    source_id=source_id,
                    suggested_action="Remove the source note or add matching trusted evidence.",
                )
            )
        elif source_id not in trusted_ids:
            issues.append(
                VerificationIssue(
                    severity="error",
                    code="untrusted_evidence_cited",
                    message="Source note references evidence blocked by the source policy.",
                    source_id=source_id,
                    suggested_action="Remove the blocked source and regenerate the answer.",
                )
            )
    return issues


def detect_unreviewed_candidate_citation(
    answer_text: str,
    source_notes: list[dict],
    unreviewed_candidate_count: int,
) -> list[VerificationIssue]:
    issues: list[VerificationIssue] = []
    for note in source_notes:
        if _is_unreviewed_or_untrusted(note):
            issues.append(
                VerificationIssue(
                    severity="error",
                    code="unreviewed_candidate_cited",
                    message=(
                        "Source note cites an unreviewed, pending, rejected, flagged, "
                        "or retrieval-disallowed candidate as trusted evidence."
                    ),
                    source_id=_source_id(note),
                    suggested_action="Keep candidates in review metadata only; do not cite them.",
                )
            )

    if unreviewed_candidate_count > 0 and _suggests_candidate_is_trusted(answer_text):
        issues.append(
            VerificationIssue(
                severity="error",
                code="unreviewed_candidate_cited",
                message=(
                    "Answer wording appears to rely on unreviewed source candidates as "
                    "trusted evidence."
                ),
                suggested_action=(
                    "Rewrite to say candidates are unreviewed and are not trusted evidence."
                ),
            )
        )
    return issues


def detect_sensitive_claim_patterns(answer_text: str) -> list[str]:
    claims: list[str] = []
    for sentence in _sentences(answer_text):
        normalized = _normalize_text(sentence)
        if not any(term in normalized for term in SENSITIVE_DOMAIN_TERMS):
            continue
        if not any(term in normalized for term in CLAIM_TERMS):
            continue
        if answer_has_uncertainty_language(sentence) and not any(
            action in normalized for action in OFFICIAL_ACTION_TERMS
        ):
            continue
        claims.append(sentence.strip())
    return list(dict.fromkeys(claims))


def detect_exact_detail_patterns(answer_text: str) -> list[str]:
    details: list[str] = []
    for match in PHONE_PATTERN.findall(answer_text):
        if len(_digits_only(match)) >= 8:
            details.append(_clean_match(match))
    for pattern in [*ADDRESS_PATTERNS, *DEADLINE_PATTERNS, *FEE_PATTERNS]:
        details.extend(_clean_match(match.group(0)) for match in pattern.finditer(answer_text))
    details.extend(
        _clean_match(match.group(0)) for match in LEGAL_REQUIREMENT_PATTERN.finditer(answer_text)
    )
    return [detail for detail in dict.fromkeys(details) if detail]


def evidence_contains_terms(evidence: list[dict], terms: list[str]) -> bool:
    eligible = [
        item
        for item in evidence
        if _source_type(item) in OFFICIAL_OR_CURATED_SOURCE_TYPES and _is_trusted_evidence(item)
    ]
    evidence_texts = [_normalize_text(_evidence_text([item])) for item in eligible]
    for term in terms:
        normalized_term = _normalize_text(term)
        term_digits = _digits_only(term)
        if len(term_digits) >= 8:
            if not any(term_digits in _digits_only(text) for text in evidence_texts):
                return False
            continue
        if not any(normalized_term in text for text in evidence_texts):
            return False
    return True


def answer_has_uncertainty_language(answer_text: str) -> bool:
    normalized = _normalize_text(answer_text)
    return any(term in normalized for term in UNCERTAINTY_TERMS)


def answer_has_escalation_language(answer_text: str) -> bool:
    normalized = _normalize_text(answer_text)
    return any(term in normalized for term in ESCALATION_TERMS)


def _official_or_curated_evidence_source_ids(evidence: list[dict]) -> set[str]:
    return {
        source_id
        for item in evidence
        if (source_id := _source_id(item))
        and _source_type(item) in OFFICIAL_OR_CURATED_SOURCE_TYPES
        and not _is_unreviewed_or_untrusted(item)
    }


def _is_missing_answer(answer_text: str) -> bool:
    if not answer_text:
        return True
    words = re.findall(r"[A-Za-z0-9\u0400-\u04ff\u4e00-\u9fff]+", answer_text)
    return len(words) < 4 or len(answer_text) < 18


def _is_trusted_evidence(item: dict) -> bool:
    source_type = _source_type(item)
    if source_type not in TRUSTED_SOURCE_TYPES:
        return False
    if _is_unreviewed_or_untrusted(item):
        return False
    if source_type in COMMUNITY_SOURCE_TYPES:
        status = _status(item)
        return status in {"", "approved"}
    return True


def _is_unreviewed_or_untrusted(item: dict) -> bool:
    source_id = _source_id(item).casefold()
    source_type = _source_type(item)
    trust_level = _trust_level(item)
    status = _status(item)
    requires_review = bool(item.get("requires_review", False))
    allow_ai_retrieval = _allow_ai_retrieval(item)
    if source_id.startswith("cand-") or "candidate" in source_id:
        return True
    if source_type in UNTRUSTED_SOURCE_TYPES:
        return True
    if trust_level in UNTRUSTED_LEVELS:
        return True
    if status in UNREVIEWED_STATUSES or not retrieval_status_allowed(
        _nested_text_value(item, "moderation_status"),
        _nested_text_value(item, "status_override") or _nested_text_value(item, "status"),
    ):
        return True
    if requires_review:
        return True
    return allow_ai_retrieval is False


def _suggests_candidate_is_trusted(answer_text: str) -> bool:
    normalized = _normalize_text(answer_text)
    trusted_candidate_phrases = {
        "candidate source confirms",
        "candidate source says",
        "unreviewed candidate confirms",
        "unreviewed candidate says",
        "source candidate confirms",
        "source candidate says",
        "trusted candidate",
        "trusted source candidate",
        "based on candidate",
        "according to candidate",
        "candidate evidence",
    }
    if not any(phrase in normalized for phrase in trusted_candidate_phrases):
        return False
    safe_negations = {
        "not used as trusted evidence",
        "not trusted evidence",
        "unreviewed source candidates are present but must not be cited",
    }
    return not any(phrase in normalized for phrase in safe_negations)


def _to_plain_dict(item: Any) -> dict:
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    source_reference = _source_reference(item)
    return {
        "source_id": str(getattr(source_reference, "source_id", "unknown")),
        "title": str(getattr(source_reference, "title", "")),
        "source_type": _enum_value(getattr(source_reference, "source_type", None)),
        "trust_level": _enum_value(getattr(source_reference, "trust_level", None)),
        "content": str(
            getattr(item, "content", "")
            or getattr(source_reference, "content", "")
            or getattr(source_reference, "excerpt", "")
            or ""
        ),
        "moderation_status": _enum_value(getattr(source_reference, "moderation_status", None)),
        "allow_ai_retrieval": bool(getattr(source_reference, "allow_ai_retrieval", True)),
    }


def _source_reference(item: Any) -> Any:
    if hasattr(item, "chunk") and hasattr(item.chunk, "source"):
        return item.chunk.source
    if hasattr(item, "source"):
        return item.source
    return item


def _source_id(item: dict) -> str:
    if item.get("source_id") is not None:
        return str(item.get("source_id"))
    source = item.get("source")
    if isinstance(source, dict) and source.get("source_id") is not None:
        return str(source.get("source_id"))
    return "unknown"


def _source_type(item: dict) -> str:
    return _nested_text_value(item, "source_type")


def _trust_level(item: dict) -> str:
    return _nested_text_value(item, "trust_level")


def _status(item: dict) -> str:
    return _nested_text_value(item, "status") or _nested_text_value(
        item,
        "moderation_status",
    )


def _allow_ai_retrieval(item: dict) -> bool:
    if "allow_ai_retrieval" in item:
        return bool(item["allow_ai_retrieval"])
    if "allow_retrieval" in item:
        return bool(item["allow_retrieval"])
    source = item.get("source")
    if isinstance(source, dict) and "allow_ai_retrieval" in source:
        return bool(source["allow_ai_retrieval"])
    return True


def _nested_text_value(item: dict, key: str) -> str:
    if item.get(key) is not None:
        return _normalize_token(item.get(key))
    source = item.get("source")
    if isinstance(source, dict) and source.get(key) is not None:
        return _normalize_token(source.get(key))
    return ""


def _evidence_text(evidence: list[dict]) -> str:
    values: list[str] = []
    for item in evidence:
        values.extend(_text_values(item))
    return " ".join(values)


def _text_values(item: dict) -> list[str]:
    values: list[str] = []
    for key in [
        "title",
        "excerpt",
        "content",
        "snippet",
        "supporting_quote",
        "claim",
    ]:
        value = item.get(key)
        if isinstance(value, str):
            values.append(value)
    for nested_key in ["source", "chunk"]:
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            values.extend(_text_values(nested))
    return values


def _claim_body(text: str) -> str:
    text = re.sub(r"^\s*-\s*\*\*[^\n]*?\*\*\s*", "", text)
    text = re.sub(r"\s*\[[A-Za-z0-9_,: -]+\]\s*$", "", text)
    return re.sub(r"^[\s#*>\-\d.)]+", "", text).strip().strip('"“”').rstrip(".。")


def _review_supports_sentence(review: BoundClaimReview | None, sentence: str) -> bool:
    if review is None:
        return False
    normalized = _normalize_text(_claim_body(sentence))
    return any(
        normalized == _normalize_text(_claim_body(part))
        for claim in review.claims for part in _sentences(claim)
    )


def _review_supports_detail(review: BoundClaimReview | None, answer: str, detail: str) -> bool:
    containing = [sentence for sentence in _sentences(answer) if detail in sentence]
    return bool(containing) and all(
        _review_supports_sentence(review, sentence) for sentence in containing
    )


def _sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|(?<=[。！？])\s*|\n+", text)
        if sentence.strip()
    ]


def _max_severity(issues: list[VerificationIssue]) -> str:
    if not issues:
        return "info"
    return max((issue.severity for issue in issues), key=lambda value: SEVERITY_ORDER[value])


def _normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").casefold().replace("_", " ").split())


def _normalize_token(value: Any) -> str:
    return str(value or "").casefold()


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _digits_only(value: str) -> str:
    return "".join(character for character in str(value) if character.isdigit())


def _clean_match(value: str) -> str:
    return " ".join(str(value).strip(".,;:()[]{} ").split())
