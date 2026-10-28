"""Evidence-bound applicability for independently reviewed interpretations."""

import re
from datetime import date

from backend.app.domain.enums import SourceType
from backend.app.domain.sources import trust_level_rank
from backend.app.memory.redaction import redact_sensitive_text
from backend.app.moderation.checks import detect_prompt_injection
from backend.app.source_conflicts.errors import ConflictValidationError
from backend.app.source_conflicts.models import (
    ConditionalBranch,
    ConflictCase,
    ResolutionApplicability,
    ResolutionProposal,
    canonical_scope,
    normalize_scope,
)


def _checked_quote(quote: str, content: str) -> str:
    redacted, warnings = redact_sensitive_text(quote)
    if (
        not quote.strip()
        or len(quote) > 4000
        or quote not in content
        or warnings
        or redacted != quote
        or detect_prompt_injection(quote)
    ):
        raise ConflictValidationError("Conditions require safe exact source quotations")
    return normalize_scope(quote)


def _explicit_token(value: str, quote: str) -> bool:
    expression = re.escape(normalize_scope(value))
    token = re.search(r"(?<!\w)" + expression + r"(?!\w)", quote)
    if token is None:
        return False
    prefix = quote[max(0, token.start() - 35) : token.start()]
    return not re.search(
        r"(?:\bnot|\bexcept|\bexcluding|\bother than|\bне|\bкроме|除外|不适用于)\s*$",
        prefix,
    )


def branches_disjoint(first: ConditionalBranch, second: ConditionalBranch) -> bool:
    for key in first.conditions.keys() & second.conditions.keys():
        left = canonical_scope(key, first.conditions[key].value)
        right = canonical_scope(key, second.conditions[key].value)
        if left != right and not (
            re.search(r"(?<!\w)" + re.escape(left) + r"(?!\w)", right)
            or re.search(r"(?<!\w)" + re.escape(right) + r"(?!\w)", left)
        ):
            return True
    return bool(
        (first.valid_until and second.valid_from and first.valid_until < second.valid_from)
        or (second.valid_until and first.valid_from and second.valid_until < first.valid_from)
    )


def validate_conditions(
    case: ConflictCase, proposal: ResolutionProposal, *, required: bool = False
) -> None:
    if not proposal.conditions:
        if required:
            raise ConflictValidationError(
                "Different conditions require explicit evidence-bound scopes"
            )
        return  # Legacy drafts may be saved, but cannot be approved.
    if proposal.outcome != "different_conditions" or len(proposal.conditions) < 2:
        raise ConflictValidationError(
            "Conditions require two or more separate applicability branches"
        )
    sources = {snapshot.source.source_id: snapshot.source for snapshot in case.sources}
    assigned: set[str] = set()
    for branch in proposal.conditions:
        ids = set(branch.source_ids)
        if len(ids) != len(branch.source_ids) or not ids.issubset(sources) or assigned & ids:
            raise ConflictValidationError("Each original source must belong to exactly one branch")
        assigned.update(ids)
        if not any(
            sources[sid].source_type in {SourceType.official, SourceType.curated_guide}
            for sid in ids
        ):
            raise ConflictValidationError("Every branch needs authoritative support")
        for dimension, evidence in branch.conditions.items():
            if re.search(
                r"[,;|/]|\b(?:or|except|other|unknown|any|all|foreign|non-chinese|"
                r"participating|partner|all-purpose)\b|или|кроме|немесе|或",
                evidence.value,
                re.I,
            ) or (
                dimension in {"document", "activity", "basis"}
                and re.search(r"\band\b|\bжәне\b|\bи\b|&", evidence.value)
            ):
                raise ConflictValidationError(
                    "Use one explicit scope value, never a compound or broad group"
                )
            if dimension == "city" and evidence.value in {
                "china",
                "mainland china",
                "китай",
                "中国",
            }:
                raise ConflictValidationError("A national jurisdiction is not a city condition")
            if set(evidence.quotes) != ids:
                raise ConflictValidationError("Each branch source must support every condition")
            for sid, quote in evidence.quotes.items():
                text = _checked_quote(quote, sources[sid].content or "")
                if not _explicit_token(evidence.value, text):
                    raise ConflictValidationError(
                        "Condition values must occur explicitly in their evidence"
                    )
                if (
                    dimension == "city"
                    and sources[sid].city
                    and (
                        canonical_scope("city", sources[sid].city)
                        != canonical_scope("city", evidence.value)
                    )
                ):
                    raise ConflictValidationError(
                        "Condition city conflicts with original source metadata"
                    )
                if (
                    dimension == "city"
                    and case.city
                    and canonical_scope("city", case.city)
                    != canonical_scope("city", evidence.value)
                ):
                    raise ConflictValidationError("Condition city conflicts with the case scope")
        for sid in ids:
            if sources[sid].city and (
                "city" not in branch.conditions
                or canonical_scope("city", branch.conditions["city"].value)
                != canonical_scope("city", sources[sid].city)
            ):
                raise ConflictValidationError(
                    "City-specific evidence requires an explicit city condition"
                )
        bounds = [bound for bound in (branch.valid_from, branch.valid_until) if bound]
        if bounds:
            if set(branch.date_quotes) != ids:
                raise ConflictValidationError(
                    "Effective intervals require evidence for every source"
                )
            for sid, quote in branch.date_quotes.items():
                text = _checked_quote(quote, sources[sid].content or "")
                anchors = (
                    (
                        branch.valid_from,
                        r"(?:effective (?:from|on)|valid from|applies from|"
                        r"действует с|қолданылады бастап|自|生效日期[:：]?)",
                    ),
                    (
                        branch.valid_until,
                        r"(?:effective (?:until|through)|valid (?:until|through)|"
                        r"applies through|действует до|有效期至|截至)",
                    ),
                )
                if any(
                    bound and not re.search(anchor + r"\s*" + re.escape(bound.isoformat()), text)
                    for bound, anchor in anchors
                ):
                    raise ConflictValidationError(
                        "Exact dates must be explicitly stated as effective dates in the original"
                    )
        elif branch.date_quotes:
            raise ConflictValidationError("Date evidence requires an explicit effective interval")
    if assigned != set(sources):
        raise ConflictValidationError("Conditions must account for every source in the case")
    for index, first in enumerate(proposal.conditions):
        if any(not branches_disjoint(first, second) for second in proposal.conditions[index + 1 :]):
            raise ConflictValidationError(
                "Applicability branches overlap or their separation is unknown"
            )


def branch_matches(branch: ConditionalBranch, context: ResolutionApplicability) -> bool:
    for dimension, evidence in branch.conditions.items():
        value = getattr(context, dimension)
        if value is None or canonical_scope(dimension, value) != canonical_scope(
            dimension, evidence.value
        ):
            return False
    if branch.valid_from is not None or branch.valid_until is not None:
        if context.on_date is None:
            return False
        if (
            not (branch.valid_from or date.min)
            <= context.on_date
            <= (branch.valid_until or date.max)
        ):
            return False
    return True


def resolve_sources(
    case: ConflictCase, applicability: ResolutionApplicability | None
) -> tuple[list[str], int | None] | None:
    proposal = case.proposal
    if proposal is None:
        return None
    if proposal.outcome == "prefer_source":
        return proposal.preferred_source_ids, None
    if proposal.outcome != "different_conditions" or applicability is None:
        return None
    validate_conditions(case, proposal, required=True)
    matches = [
        index
        for index, branch in enumerate(proposal.conditions)
        if branch_matches(branch, applicability)
    ]
    if len(matches) != 1:
        return None
    index = matches[0]
    ids = set(proposal.conditions[index].source_ids)
    authoritative = [
        snapshot.source
        for snapshot in case.sources
        if snapshot.source.source_id in ids
        and snapshot.source.source_type in {SourceType.official, SourceType.curated_guide}
    ]
    best = min(trust_level_rank(source.trust_level) for source in authoritative)
    return sorted(
        source.source_id for source in authoritative if trust_level_rank(source.trust_level) == best
    ), index
