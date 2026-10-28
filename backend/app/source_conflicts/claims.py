"""Compare explicit rule claims without inventing missing applicability.

Extractors normalize units, polarity and population before constructing claims.
This module only compares complete, matching scopes and records suggestions for
review. It does not decide which rule is legally applicable or change source trust.
"""

import hashlib
import json
from collections import defaultdict
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.agent.classification import has_active_prompt_injection
from backend.app.domain.enums import RiskLevel, SourceType, TrustLevel, UserScenario
from backend.app.domain.sources import SourceReference, is_retrievable_source
from backend.app.memory.redaction import redact_sensitive_text
from backend.app.source_conflicts.detection_models import DetectedConflict

MAX_COMPARISON_CLAIMS = 512
MAX_COMPARISON_SOURCES = 64
MAX_COMPARISON_SOURCE_CHARS = 40_000
MAX_COMPARISON_SUGGESTIONS = 32

_CANONICAL_TRUST = {
    SourceType.official: TrustLevel.level_1_official,
    SourceType.curated_guide: TrustLevel.level_2_curated,
    SourceType.verified_institutional_contributor: TrustLevel.level_3_verified_institutional,
    SourceType.verified_experienced_contributor: TrustLevel.level_4_verified_experienced,
    SourceType.ordinary_community: TrustLevel.level_5_ordinary_community,
}
_AUTHORITATIVE_TYPES = {SourceType.official, SourceType.curated_guide}
_RISK_PRIORITY = {
    RiskLevel.normal: 0,
    RiskLevel.medium: 1,
    RiskLevel.legal_sensitive: 2,
    RiskLevel.work_status_sensitive: 3,
    RiskLevel.medical_sensitive: 4,
    RiskLevel.emergency: 5,
    RiskLevel.unsafe: 6,
    RiskLevel.prompt_injection: 7,
}


class RuleClaim(BaseModel):
    """One literal claim and its explicit, extractor-defined applicability."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str = Field(min_length=1, max_length=120)
    source: SourceReference
    quote: str = Field(min_length=1, max_length=900)
    value: str = Field(min_length=1, max_length=160)
    dimensions: dict[str, str] = Field(min_length=1, max_length=32)
    scenario: UserScenario
    risk_level: RiskLevel
    valid_from: date | None = None
    valid_until: date | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "RuleClaim":
        if not self.rule_id.strip() or not self.quote.strip() or not self.value.strip():
            raise ValueError("Rule, quote and value must contain text")
        if any(
            not key.strip() or not value.strip() or len(key) > 120 or len(value) > 160
            for key, value in self.dimensions.items()
        ):
            raise ValueError("Applicability dimensions must contain bounded text")
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError("The validity interval cannot end before it starts")
        return self


def compare_claims(
    claims: list[RuleClaim], *, max_suggestions: int = MAX_COMPARISON_SUGGESTIONS
) -> list[DetectedConflict]:
    """Suggest differing values only when all supplied applicability matches.

    Inputs beyond the complete-input bounds fail closed. Repeated claims for an
    identical source are allowed; differing versions with the same source ID are
    rejected rather than choosing one arbitrarily. Only authoritative sources can
    anchor a comparison, so community experience never becomes an authority.
    Contributor credentials must already be checked by the server source registry;
    this comparator cannot verify a role from SourceReference alone.
    """
    if not claims or len(claims) > MAX_COMPARISON_CLAIMS or max_suggestions <= 0:
        return []
    limit = min(max_suggestions, MAX_COMPARISON_SUGGESTIONS)
    sources: dict[str, SourceReference] = {}
    fingerprints: dict[str, str] = {}
    collisions: set[str] = set()
    for claim in claims:
        source = claim.source
        fingerprint = source.model_dump_json()
        if source.source_id in fingerprints and fingerprints[source.source_id] != fingerprint:
            collisions.add(source.source_id)
        else:
            fingerprints[source.source_id] = fingerprint
            sources[source.source_id] = source
    if len(sources) > MAX_COMPARISON_SOURCES:
        return []
    eligible_ids = {
        source_id
        for source_id, source in sources.items()
        if source_id not in collisions and _eligible_source(source)
    }
    groups: dict[tuple, list[RuleClaim]] = defaultdict(list)
    seen_claims: set[tuple] = set()
    for claim in claims:
        if claim.source.source_id not in eligible_ids or not _eligible_claim(claim):
            continue
        scope_key = _scope_key(claim)
        claim_key = (
            scope_key,
            claim.source.source_id,
            _normalize(claim.value),
            claim.quote,
            claim.valid_from,
            claim.valid_until,
        )
        if claim_key in seen_claims:
            continue
        seen_claims.add(claim_key)
        groups[scope_key].append(claim)

    suggestions: list[DetectedConflict] = []
    seen_pairs: set[tuple] = set()
    for scope_key, matching in sorted(groups.items()):
        ambiguous_ids = _ambiguous_source_ids(matching)
        ordered = sorted(
            (claim for claim in matching if claim.source.source_id not in ambiguous_ids),
            key=lambda claim: (
                claim.source.source_id,
                _normalize(claim.value),
                claim.quote,
                claim.valid_from or date.min,
                claim.valid_until or date.max,
            ),
        )
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                if not _comparable(left, right):
                    continue
                pair_key = (scope_key, left.source.source_id, right.source.source_id)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                suggestions.append(_suggestion(left, right))
                if len(suggestions) == limit:
                    return suggestions
    return suggestions


def _normalize(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())


def _scope_key(claim: RuleClaim) -> tuple:
    return (
        _normalize(claim.rule_id),
        claim.scenario.value,
        _normalize(claim.source.city),
        claim.source.scenario.value if claim.source.scenario else "",
        tuple(
            sorted((_normalize(key), _normalize(value)) for key, value in claim.dimensions.items())
        ),
    )


def _eligible_source(source: SourceReference) -> bool:
    content = source.content or ""
    return (
        bool(source.source_id.strip())
        and _CANONICAL_TRUST.get(source.source_type) == source.trust_level
        and is_retrievable_source(source)
        and bool(content.strip())
        and len(content) <= MAX_COMPARISON_SOURCE_CHARS
        and not has_active_prompt_injection(content)
    )


def _eligible_claim(claim: RuleClaim) -> bool:
    # Exact provenance is mandatory: normalized or fabricated paraphrases are not quotes.
    if claim.quote not in (claim.source.content or ""):
        return False
    if redact_sensitive_text(claim.quote)[1]:
        return False
    scope_values = [claim.rule_id, claim.value, claim.source.city or ""]
    scope_values.extend(item for pair in claim.dimensions.items() for item in pair)
    if any(
        redact_sensitive_text(value)[1] or has_active_prompt_injection(value)
        for value in scope_values
    ):
        return False
    normalized_keys = [_normalize(key) for key in claim.dimensions]
    return len(normalized_keys) == len(set(normalized_keys))


def _comparable(left: RuleClaim, right: RuleClaim) -> bool:
    if left.source.source_id == right.source.source_id or _normalize(left.value) == _normalize(
        right.value
    ):
        return False
    if not (
        left.source.source_type in _AUTHORITATIVE_TYPES
        or right.source.source_type in _AUTHORITATIVE_TYPES
    ):
        return False
    return _validity_overlaps(left, right)


def _validity_overlaps(left: RuleClaim, right: RuleClaim) -> bool:
    # Publication dates describe the document, not necessarily the rule's validity.
    if left.valid_until and right.valid_from and left.valid_until < right.valid_from:
        return False
    if right.valid_until and left.valid_from and right.valid_until < left.valid_from:
        return False
    return True


def _ambiguous_source_ids(claims: list[RuleClaim]) -> set[str]:
    by_source: dict[str, list[RuleClaim]] = defaultdict(list)
    for claim in claims:
        by_source[claim.source.source_id].append(claim)
    ambiguous: set[str] = set()
    for source_id, matching in by_source.items():
        for index, left in enumerate(matching):
            if any(
                _normalize(left.value) != _normalize(right.value)
                and _validity_overlaps(left, right)
                for right in matching[index + 1 :]
            ):
                ambiguous.add(source_id)
                break
    return ambiguous


def _suggestion(left: RuleClaim, right: RuleClaim) -> DetectedConflict:
    scope = dict(left.dimensions)
    scope["source_city"] = _normalize(left.source.city) or "unspecified"
    scope["source_scenario"] = (
        left.source.scenario.value if left.source.scenario else "unspecified"
    )
    community = [
        source
        for source in (left.source, right.source)
        if source.source_type not in _AUTHORITATIVE_TYPES
    ]
    reason = (
        f"Possible contradiction: matching {left.rule_id.replace('_', ' ')} passages "
        f"state {left.value!r} and {right.value!r}. Check the exact scope, validity periods, "
        "publication dates and exceptions with a human reviewer. This suggestion does not "
        "establish a legal conflict or approve a resolution."
    )
    if community:
        reason += (
            " Community or institutional experience is context only; official and curated "
            "sources retain priority."
        )
        for source in community:
            scope[f"context_source_type:{source.source_id}"] = source.source_type.value
            scope[f"context_trust_level:{source.source_id}"] = source.trust_level.value
    if not all((left.valid_from, left.valid_until, right.valid_from, right.valid_until)):
        reason += " Complete effective dates are unknown; concurrent applicability needs review."
    key_payload = {
        "rule_id": _normalize(left.rule_id),
        "scope": _scope_key(left),
        "source_ids": [left.source.source_id, right.source.source_id],
        "quotes": [left.quote, right.quote],
        "values": [_normalize(left.value), _normalize(right.value)],
        "effective_dates": [
            str(left.valid_from) if left.valid_from else None,
            str(left.valid_until) if left.valid_until else None,
            str(right.valid_from) if right.valid_from else None,
            str(right.valid_until) if right.valid_until else None,
        ],
    }
    conflict_key = hashlib.sha256(
        json.dumps(key_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return DetectedConflict(
        topic=left.rule_id.replace("_", " ").capitalize(),
        source_ids=[left.source.source_id, right.source.source_id],
        quotes=[left.quote, right.quote],
        scenario=left.scenario,
        risk_level=max((left.risk_level, right.risk_level), key=_RISK_PRIORITY.__getitem__),
        city=left.source.city,
        reason=reason,
        rule_id=left.rule_id,
        conflict_kind="potential_contradiction",
        scope=scope,
        conflict_key=conflict_key,
    )
