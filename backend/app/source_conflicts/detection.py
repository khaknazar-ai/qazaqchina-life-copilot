"""Suggest source-bound contradictions across explicit, comparable rule scopes.

Detection proposes review; it never resolves a disagreement or approves evidence.
Unknown applicability and complex conditions remain available for manual review.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from backend.app.agent.classification import has_active_prompt_injection
from backend.app.domain.enums import RiskLevel, SourceType, TrustLevel, UserScenario
from backend.app.domain.sources import SourceReference, is_retrievable_source
from backend.app.memory.redaction import redact_sensitive_text
from backend.app.source_conflicts.claims import MAX_COMPARISON_CLAIMS, RuleClaim, compare_claims
from backend.app.source_conflicts.detection_models import ConflictDetectionReport, DetectedConflict
from backend.app.source_conflicts.payment_rules import extract_payment_claims
from backend.app.source_conflicts.rule_text import rule_sentences

MAX_SOURCES = 64
MAX_SOURCE_CHARS = 40_000
MAX_SENTENCE_CHARS = 900
MAX_CLAIMS_PER_SOURCE = 8
MAX_SUGGESTIONS = 32

_SENTENCE = re.compile(r"[^.!?。！？\r\n]+(?:[.!?。！？]+|(?=\r|\n|$))")
_DEADLINE = re.compile(
    r"\bwithin\s+(\d{1,3})\s+(?:hours?|hrs?)\b|"
    r"(?:в\s+течение|не\s+позднее)\s+(\d{1,3})\s*час(?:а|ов)?\b|"
    r"(\d{1,3})\s*(?:个)?小时(?:之)?内",
    re.I,
)
_REGISTER = re.compile(
    r"\bregist(?:er\w*|ration)\b|регистрац\w*|зарегистрир\w*|住宿登记|居住登记",
    re.I,
)
_ACCOMMODATION = re.compile(
    r"\baccommodation\b|\bdomiciles?\b|\bresidences?\b|\bhotels?\b|"
    r"\bnon[- ]hotel\b|\boff[- ]campus\b|прожив\w*|пребыван\w*|"
    r"гостиниц\w*|отел\w*|жиль\w*|住宿|居住|旅馆|酒店|住所",
    re.I,
)
_FOREIGNER = re.compile(r"\bforeigners?\b|\bforeign nationals?\b|иностран\w*|外国人", re.I)
_STUDENT = re.compile(r"\bstudents?\b|студент\w*|学生|留学生", re.I)
_MANDATORY = re.compile(
    r"\b(?:must|shall|required|should)\b|\b(?:need|have) to\b|"
    r"обязан\w*|долж\w*|необходимо|требуется|应当|必须|应|须|需",
    re.I,
)
_AMBIGUOUS = re.compile(
    r"\b(?:if|unless|except|exceptions?|otherwise|only|exempt\w*|previously|formerly|"
    r"outdated|rumou?rs?|incorrect|misleading|allegedly)\b|\bused to\b|\bno longer\b|"
    r"\bsubject to\b|\bprovided that\b|\bdoes not apply\b|"
    r"\b(?:weekends?|weekdays?|holidays?|mondays?|tuesdays?|wednesdays?|thursdays?|"
    r"fridays?|saturdays?|sundays?)\b|"
    r"\b(?:before|after|from|until|since|during|as of)\s+(?:the year\s+)?(?:19|20)\d{2}\b|"
    r"если|только|кроме|исключени\w*|освобожд\w*|при\s+услови\w*|"
    r"выходн\w*|праздничн\w*|ранее|устарев\w*|неверн\w*|слух\w*|"
    r"(?:до|после|с|в)\s+(?:19|20)\d{2}\s*(?:года|году|г\.)|"
    r"除外|除非|如果|若|仅限|豁免|工作日|周末|节假日|此前|以前|曾经|不再|谣言|错误|"
    r"(?:19|20)\d{2}年",
    re.I,
)
_EXCLUDED_RULE = re.compile(
    r"\bvisas?\b|\b(?:residence|work) permits?\b|виз\w*|разрешени\w*|"
    r"签证|居留许可|工作许可|"
    r"\b(?:fees?|pay(?:ment|ments|ing)?|costs?|refunds?|processing)\b|"
    r"\bre[- ]regist(?:er\w*|ration)\b|\bregister again\b|повторн\w*|重新登记|"
    r"оплат\w*|стоимост\w*|сбор\w*|费用|缴费|处理|"
    r"\b(?:not required|need not|do not need|not necessary)\b|"
    r"не\s+(?:требуется|нужно|обязан\w*)|无需|无须|不需要|不必",
    re.I,
)
_NON_HOTEL = re.compile(
    r"\bnon[- ]hotel\b|\b(?:other than|outside|not in|not staying in)\s+hotels?\b|"
    r"вне\s+(?:гостиниц\w*|отел\w*)|не\s+в\s+(?:гостиниц\w*|отел\w*)|"
    r"(?:旅馆|酒店)以外|非(?:酒店|旅馆)|不在(?:酒店|旅馆)",
    re.I,
)
_RURAL = re.compile(r"\brural\b|сельск\w*|农村|乡村", re.I)
_URBAN = re.compile(r"\burban\b|городск\w*|城市|城镇", re.I)
_HOTEL = re.compile(r"\bhotels?\b|гостиниц\w*|отел\w*|旅馆|酒店", re.I)
_OFF_CAMPUS = re.compile(r"\boff[- ]campus\b|вне\s+кампуса|校外", re.I)
_PRIVATE_HOME = re.compile(
    r"\bprivate\s+(?:homes?|residences?|accommodation)\b|"
    r"частн\w*\s+(?:жиль\w*|дом\w*|квартир\w*)|私人住宅|私人住所",
    re.I,
)
_ARRIVAL = re.compile(r"\barrival\b|прибыт\w*|抵达|到达", re.I)
_CHECK_IN = re.compile(r"\bcheck[- ]in\b|\bmoving in\b|заселени\w*|入住", re.I)
_BEFORE_DEADLINE = re.compile(
    r"\bhours?\s+before\b|\bprior to\b|час\w*\s+до\b|小时前|小时之前",
    re.I,
)


@dataclass(frozen=True)
class _DeadlineClaim:
    source: SourceReference
    quote: str
    hours: int
    scope: tuple[str, str, str, str]


def detect_conflicts(sources: list[SourceReference]) -> list[DetectedConflict]:
    """Return bounded suggestions; original sources and review state stay untouched."""
    return detect_conflicts_report(sources).suggestions


def detect_conflicts_report(
    sources: list[SourceReference],
    *,
    priority_source_ids: set[str] | None = None,
) -> ConflictDetectionReport:
    """Expose bounded scan coverage; an empty result is never an exhaustive audit."""
    from backend.app.source_conflicts.service_rules import extract_service_claims
    from backend.app.source_conflicts.visa_rules import extract_visa_claims

    priority_ids = priority_source_ids or set()
    id_counts = Counter(source.source_id for source in sources)
    ordered = sorted(
        sources,
        key=lambda source: (source.source_id not in priority_ids, source.source_id),
    )
    bounded = ordered[:MAX_SOURCES]
    warnings = []
    skipped = {source.source_id for source in ordered[MAX_SOURCES:]}
    if len(sources) > MAX_SOURCES:
        warnings.append("source_limit_reached")
    candidates = sorted(
        (source for source in bounded if id_counts[source.source_id] == 1),
        key=lambda source: source.source_id,
    )
    duplicates = {sid for sid, count in id_counts.items() if count != 1}
    if duplicates:
        skipped.update(duplicates)
        warnings.append("duplicate_source_ids")
    findings = _detect_registration_conflicts(candidates)
    grouped_claims = defaultdict(list)
    for source in candidates:
        if len(source.content or "") > MAX_SOURCE_CHARS:
            skipped.add(source.source_id)
            if "source_text_limit_reached" not in warnings:
                warnings.append("source_text_limit_reached")
            continue
        for extract in (extract_visa_claims, extract_service_claims, extract_payment_claims):
            for claim in extract(source):
                grouped_claims[claim.rule_id].append(claim)
    for _rule, claims in sorted(grouped_claims.items()):
        if len(claims) > MAX_COMPARISON_CLAIMS:
            warnings.append("claim_limit_reached")
            skipped.update(claim.source.source_id for claim in claims)
            continue
        findings.extend(compare_claims(claims))
    if len(findings) >= MAX_SUGGESTIONS:
        warnings.append("suggestion_limit_reached")
    suggestions = sorted(
        findings, key=lambda finding: (finding.rule_id or "", finding.source_ids, finding.quotes)
    )[:MAX_SUGGESTIONS]
    return ConflictDetectionReport(
        suggestions=suggestions,
        coverage_status="partial" if warnings else "bounded_rules",
        input_source_count=len(sources),
        scanned_source_count=sum(source.source_id not in skipped for source in bounded),
        skipped_source_ids=sorted(skipped),
        warnings=list(dict.fromkeys(warnings)),
    )


def source_rule_ids(source: SourceReference) -> set[str]:
    """Return explicit rules this eligible source can contribute to a comparison."""
    from backend.app.source_conflicts.service_rules import extract_service_claims
    from backend.app.source_conflicts.visa_rules import extract_visa_claims

    if len(source.content or "") > MAX_SOURCE_CHARS or not _eligible(source):
        return set()
    extracts = (extract_visa_claims, extract_service_claims, extract_payment_claims)
    rule_ids = {
        claim.rule_id
        for extract in extracts
        for claim in extract(source)
    }
    if _claims(source):
        rule_ids.add("registration.deadline_hours")
    return rule_ids


def _detect_registration_conflicts(sources: list[SourceReference]) -> list[DetectedConflict]:
    candidates = sources[:MAX_SOURCES]
    id_counts = Counter(source.source_id for source in candidates)
    claims: list[_DeadlineClaim] = []
    for source in sorted(candidates, key=lambda item: item.source_id):
        if id_counts[source.source_id] != 1 or not _eligible(source):
            continue
        claims.extend(_claims(source))

    normalized_claims = [
        RuleClaim(
            rule_id="registration.deadline_hours",
            source=claim.source,
            quote=claim.quote,
            value=str(claim.hours),
            dimensions=dict(zip(("area", "lodging", "population", "anchor"), claim.scope)),
            scenario=UserScenario.housing,
            risk_level=RiskLevel.legal_sensitive,
        )
        for claim in claims
    ]
    return compare_claims(normalized_claims, max_suggestions=MAX_SUGGESTIONS)


def _eligible(source: SourceReference) -> bool:
    expected_trust = {
        SourceType.official: TrustLevel.level_1_official,
        SourceType.curated_guide: TrustLevel.level_2_curated,
        SourceType.verified_institutional_contributor: TrustLevel.level_3_verified_institutional,
        SourceType.verified_experienced_contributor: TrustLevel.level_4_verified_experienced,
        SourceType.ordinary_community: TrustLevel.level_5_ordinary_community,
    }.get(source.source_type)
    content = source.content or ""
    return (
        expected_trust is not None
        and source.trust_level == expected_trust
        and is_retrievable_source(source)
        and 0 < len(content) <= MAX_SOURCE_CHARS
        and bool(content.strip())
        and not has_active_prompt_injection(content)
    )


def _claims(source: SourceReference) -> list[_DeadlineClaim]:
    content = source.content or ""
    bounded = content[:MAX_SOURCE_CHARS]
    claims: list[_DeadlineClaim] = []
    sentences = list(_SENTENCE.finditer(bounded))
    safe_passages = set(rule_sentences(source))
    for index, match in enumerate(sentences):
        if len(content) > len(bounded) and match.end() == len(bounded):
            continue  # A truncated sentence may have lost a condition or exception.
        quote = match.group().strip()
        if not quote or quote not in safe_passages or len(quote) > MAX_SENTENCE_CHARS:
            continue
        if not all(
            pattern.search(quote)
            for pattern in (
                _REGISTER,
                _ACCOMMODATION,
                _FOREIGNER,
                _MANDATORY,
            )
        ):
            continue
        if _adjacent_condition(bounded, sentences, index):
            continue
        if (
            any(
                pattern.search(quote)
                for pattern in (
                    _AMBIGUOUS,
                    _EXCLUDED_RULE,
                    _BEFORE_DEADLINE,
                )
            )
            or redact_sensitive_text(quote)[1]
        ):
            continue
        deadlines = list(_DEADLINE.finditer(quote))
        if len(deadlines) != 1:
            continue  # Do not assign multiple rural/urban deadlines by proximity.
        hours = int(next(group for group in deadlines[0].groups() if group is not None))
        if not 0 < hours <= 336:
            continue
        scope = _scope(quote)
        if scope is None:
            continue
        claims.append(_DeadlineClaim(source, quote, hours, scope))
        if len(claims) == MAX_CLAIMS_PER_SOURCE:
            break
    return claims


def _adjacent_condition(content: str, sentences: list[re.Match], index: int) -> bool:
    current = sentences[index]
    for neighbor_index in (index - 1, index + 1):
        if not 0 <= neighbor_index < len(sentences):
            continue
        neighbor = sentences[neighbor_index]
        gap_start = min(current.end(), neighbor.end())
        gap_end = max(current.start(), neighbor.start())
        if re.search(r"\r?\n\s*\r?\n", content[gap_start:gap_end]):
            continue
        if _AMBIGUOUS.search(neighbor.group()) or _EXCLUDED_RULE.search(neighbor.group()):
            return True
    return False


def _scope(quote: str) -> tuple[str, str, str, str] | None:
    areas = [
        name for name, pattern in (("rural", _RURAL), ("urban", _URBAN)) if pattern.search(quote)
    ]
    if len(areas) > 1:
        return None
    lodging = [
        name
        for name, pattern in (
            ("non_hotel", _NON_HOTEL),
            ("off_campus", _OFF_CAMPUS),
            ("private_home", _PRIVATE_HOME),
        )
        if pattern.search(quote)
    ]
    if len(lodging) > 1:
        return None
    accommodation = lodging[0] if lodging else ("hotel" if _HOTEL.search(quote) else "general")
    anchors = [
        name
        for name, pattern in (("arrival", _ARRIVAL), ("check_in", _CHECK_IN))
        if pattern.search(quote)
    ]
    if len(anchors) > 1:
        return None
    return (
        areas[0] if areas else "general",
        accommodation,
        "student" if _STUDENT.search(quote) else "foreigner",
        anchors[0] if anchors else "unspecified",
    )
