import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field, field_validator

from backend.app.official_source_review.models import OfficialSourceCandidate
from backend.app.source_coverage.taxonomy import OFFICIAL_SOURCE_TIERS

OfficialSourceIntakeStatus = Literal[
    "missing",
    "template_only",
    "invalid",
    "valid_metadata_only",
    "ready_for_review",
    "blocked_sensitive_data",
    "blocked_secret_pattern",
]

FindingSeverity = Literal["info", "warning", "blocker"]

REQUIRED_INTAKE_METADATA = [
    "domain",
    "proposed_trust_tier",
    "title_or_document_ref",
    "url_or_document_ref",
    "claimed_publisher",
    "jurisdiction_or_scope",
    "language",
    "freshness_or_version_note",
]

EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
SECRET_TERM_PATTERN = re.compile(
    r"\b(api[_-]?key|token|secret|password|bearer|openai_api_key|google_api_key)\b",
    re.IGNORECASE,
)
SK_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class OfficialSourceIntakeFinding(BaseModel):
    finding_id: str
    severity: FindingSeverity
    title: str
    description: str
    recommendation: str | None = None


class OfficialSourceIntakeCandidate(BaseModel):
    intake_id: str
    domain: str
    proposed_trust_tier: str
    source_title: str | None = None
    source_url: str | None = None
    source_document_ref: str | None = None
    claimed_publisher: str | None = None
    jurisdiction_or_scope: str | None = None
    language: str | None = None
    freshness_note: str | None = None
    source_version_note: str | None = None
    related_gap_id: str | None = None
    related_acquisition_task_id: str | None = None
    notes: list[str] = Field(default_factory=list)
    not_trusted_until_reviewed: bool = True


class OfficialSourceIntakeReport(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    intake_path: str | None
    intake_exists: bool
    template_only: bool
    total_candidates: int
    ready_for_review_count: int
    blocked_count: int
    warning_count: int
    blocker_count: int
    status: OfficialSourceIntakeStatus
    candidates: list[OfficialSourceIntakeCandidate]
    findings: list[OfficialSourceIntakeFinding]
    sanitized_summary: dict[str, object]
    ready_for_closed_beta: bool = False
    ready_for_public_launch: bool = False
    used_network: bool = False
    used_external_provider: bool = False
    notes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def _generated_at_must_be_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class OfficialSourceIntakeService:
    def __init__(
        self,
        project_root: Path | str = ".",
        intake_path: Path | str | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.intake_path = Path(intake_path) if intake_path is not None else None

    def default_local_intake_path(self) -> Path:
        return (
            self.project_root
            / "configs"
            / "source_review"
            / "official_source_candidate_intake.local.json"
        )

    def load_intake(self, path: Path | str) -> dict:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("official source intake must be a JSON object")
        return loaded

    def validate_intake_data(self, data: dict) -> list[OfficialSourceIntakeFinding]:
        findings: list[OfficialSourceIntakeFinding] = []
        raw_candidates = _raw_candidate_items(data)
        if not raw_candidates:
            findings.append(
                OfficialSourceIntakeFinding(
                    finding_id="INTAKE-NO-CANDIDATES",
                    severity="warning",
                    title="No intake candidates found.",
                    description="The intake file has no candidate metadata entries.",
                    recommendation="Add candidates before review can begin.",
                )
            )
            return findings

        for index, raw_candidate in enumerate(raw_candidates, start=1):
            if not isinstance(raw_candidate, dict):
                findings.append(
                    OfficialSourceIntakeFinding(
                        finding_id=f"INTAKE-CANDIDATE-{index}-INVALID",
                        severity="blocker",
                        title="Candidate entry is invalid.",
                        description="Each candidate entry must be a JSON object.",
                        recommendation="Replace the entry with structured candidate metadata.",
                    )
                )
                continue
            candidate = _candidate_from_raw(raw_candidate, index)
            missing = _missing_required_metadata(candidate)
            if missing:
                findings.append(
                    OfficialSourceIntakeFinding(
                        finding_id=f"INTAKE-CANDIDATE-{index}-MISSING-METADATA",
                        severity="warning",
                        title="Required candidate metadata is incomplete.",
                        description=(
                            "Missing metadata: "
                            f"{', '.join(missing)}. Intake remains metadata-only."
                        ),
                        recommendation=(
                            "Complete metadata before sending the candidate to official "
                            "source review."
                        ),
                    )
                )
            if candidate.proposed_trust_tier not in OFFICIAL_SOURCE_TIERS:
                findings.append(
                    OfficialSourceIntakeFinding(
                        finding_id=f"INTAKE-CANDIDATE-{index}-TRUST-TIER",
                        severity="blocker",
                        title="Proposed trust tier is not an official tier.",
                        description=(
                            "Official source intake accepts only official trust tiers."
                        ),
                        recommendation=(
                            "Use an official_law, official_regulation, "
                            "official_policy_document, official_agency_page, "
                            "official_consulate_or_embassy_page, or "
                            "official_university_page tier."
                        ),
                    )
                )
            if candidate.source_url and not _is_plausible_url(candidate.source_url):
                findings.append(
                    OfficialSourceIntakeFinding(
                        finding_id=f"INTAKE-CANDIDATE-{index}-URL",
                        severity="blocker",
                        title="Candidate URL is not syntactically plausible.",
                        description="The intake validator checks URL shape without fetching it.",
                        recommendation="Use an http or https URL captured by a reviewer.",
                    )
                )
        return findings

    def detect_sensitive_or_secret_data(
        self,
        data: dict,
    ) -> list[OfficialSourceIntakeFinding]:
        findings: list[OfficialSourceIntakeFinding] = []
        for path, value in _iter_string_values(data):
            category = _sensitive_category(value)
            if category is None:
                continue
            if category == "secret":
                findings.append(
                    OfficialSourceIntakeFinding(
                        finding_id=f"INTAKE-SECRET-{len(findings) + 1}",
                        severity="blocker",
                        title="Secret-like value detected in intake data.",
                        description=f"Secret-like content was detected at `{path}`.",
                        recommendation=(
                            "Remove API keys, bearer values, passwords, private keys, and "
                            "token-like values before using local intake."
                        ),
                    )
                )
            else:
                findings.append(
                    OfficialSourceIntakeFinding(
                        finding_id=f"INTAKE-SENSITIVE-{len(findings) + 1}",
                        severity="blocker",
                        title="Sensitive personal data detected in intake data.",
                        description=f"Personal contact-like content was detected at `{path}`.",
                        recommendation=(
                            "Remove private emails, phone numbers, and personal contact "
                            "details from intake metadata."
                        ),
                    )
                )
        return findings

    def build_candidates_from_intake(
        self,
        data: dict,
    ) -> list[OfficialSourceIntakeCandidate]:
        candidates: list[OfficialSourceIntakeCandidate] = []
        for index, raw_candidate in enumerate(_raw_candidate_items(data), start=1):
            if not isinstance(raw_candidate, dict):
                continue
            candidates.append(_candidate_from_raw(raw_candidate, index))
        return candidates

    def build_review_candidates(
        self,
        candidates: list[OfficialSourceIntakeCandidate],
    ) -> list[OfficialSourceCandidate]:
        review_candidates: list[OfficialSourceCandidate] = []
        for candidate in candidates:
            review_candidates.append(
                OfficialSourceCandidate(
                    candidate_id=f"official-source-candidate-{candidate.intake_id}",
                    domain=candidate.domain,
                    source_title=candidate.source_title,
                    source_url=candidate.source_url,
                    source_document_ref=candidate.source_document_ref,
                    proposed_trust_tier=candidate.proposed_trust_tier,
                    claimed_publisher=candidate.claimed_publisher,
                    jurisdiction_or_scope=candidate.jurisdiction_or_scope,
                    language=candidate.language,
                    related_gap_id=candidate.related_gap_id,
                    related_acquisition_task_id=candidate.related_acquisition_task_id,
                    status="submitted",
                    not_trusted_until_approved=True,
                    notes=[
                        *candidate.notes,
                        "Created from official source intake metadata.",
                        "Not trusted evidence until official source review and publishing.",
                    ],
                )
            )
        return review_candidates

    def generate_report(self) -> OfficialSourceIntakeReport:
        path = self.intake_path or self.default_local_intake_path()
        if not path.exists():
            findings = [
                OfficialSourceIntakeFinding(
                    finding_id="INTAKE-MISSING",
                    severity="info",
                    title="Local intake file is missing.",
                    description="Missing local intake is safe and does not create evidence.",
                    recommendation="Create an ignored local intake file only when ready.",
                )
            ]
            return _report(
                path=path,
                intake_exists=False,
                template_only=False,
                status="missing",
                candidates=[],
                findings=findings,
            )

        try:
            data = self.load_intake(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            findings = [
                OfficialSourceIntakeFinding(
                    finding_id="INTAKE-INVALID",
                    severity="blocker",
                    title="Local intake file cannot be parsed.",
                    description=(
                        "Intake file is invalid JSON/object metadata: "
                        f"{type(exc).__name__}."
                    ),
                    recommendation="Fix the local intake JSON structure before review.",
                )
            ]
            return _report(
                path=path,
                intake_exists=True,
                template_only=False,
                status="invalid",
                candidates=[],
                findings=findings,
            )

        template_only = bool(data.get("template_only") or data.get("example_only"))
        candidates = self.build_candidates_from_intake(data)
        safety_findings = self.detect_sensitive_or_secret_data(data)
        if template_only:
            findings = [
                OfficialSourceIntakeFinding(
                    finding_id="INTAKE-TEMPLATE-ONLY",
                    severity="info",
                    title="Intake file is template/example only.",
                    description="Template/example intake is safe but cannot support review.",
                    recommendation="Create an ignored local intake file for real metadata.",
                ),
                *safety_findings,
            ]
        else:
            findings = [*self.validate_intake_data(data), *safety_findings]
        status = _status_for_report(template_only, candidates, findings)
        return _report(
            path=path,
            intake_exists=True,
            template_only=template_only,
            status=status,
            candidates=candidates,
            findings=findings,
        )


def official_source_intake_report_to_jsonable(
    report: OfficialSourceIntakeReport,
) -> dict:
    return report.model_dump(mode="json")


def official_source_intake_report_to_markdown(
    report: OfficialSourceIntakeReport,
) -> str:
    lines = [
        "# Official Source Candidate Intake Report",
        "",
        "## Executive Decision",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Status: {report.status}",
        f"- Intake exists: {report.intake_exists}",
        f"- Template only: {report.template_only}",
        f"- Total candidates: {report.total_candidates}",
        f"- Ready for review count: {report.ready_for_review_count}",
        f"- Blocked count: {report.blocked_count}",
        f"- Warning count: {report.warning_count}",
        f"- Blocker count: {report.blocker_count}",
        f"- Ready for closed beta: {report.ready_for_closed_beta}",
        f"- Ready for public launch: {report.ready_for_public_launch}",
        f"- Used network: {report.used_network}",
        f"- Used external provider: {report.used_external_provider}",
        "",
        "Intake candidates are not trusted evidence.",
        "No automatic publishing occurred. Local intake must not be committed.",
        "",
        "## Intake File Status",
        "",
        f"- Intake path: `{report.intake_path or 'none'}`",
        f"- Intake exists: {report.intake_exists}",
        f"- Template/example only: {report.template_only}",
        "",
        "## Candidate Metadata Summary",
        "",
        f"- Candidate domains: {', '.join(report.sanitized_summary.get('domains', [])) or 'none'}",
        (
            "- Proposed trust tiers: "
            f"{', '.join(report.sanitized_summary.get('trust_tiers', [])) or 'none'}"
        ),
        (
            "- Candidate URL hosts: "
            f"{', '.join(report.sanitized_summary.get('url_hosts', [])) or 'none'}"
        ),
        "",
        "| Intake ID | Domain | Trust tier | URL captured | Document captured | Ready |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for candidate in report.candidates:
        lines.append(
            f"| {candidate.intake_id} | {candidate.domain} | "
            f"{candidate.proposed_trust_tier} | {bool(candidate.source_url)} | "
            f"{bool(candidate.source_document_ref)} | "
            f"{_candidate_ready_for_review(candidate)} |"
        )

    lines.extend(["", "## Readiness For Review", ""])
    if report.ready_for_review_count:
        lines.append(
            "- Some candidates have complete metadata for review intake, but none are trusted."
        )
    else:
        lines.append("- No candidate is ready for review.")

    lines.extend(["", "## Blockers And Warnings", ""])
    if report.findings:
        for finding in report.findings:
            lines.extend(
                [
                    f"### {finding.finding_id}",
                    "",
                    f"- Severity: {finding.severity}",
                    f"- Title: {finding.title}",
                    f"- Description: {finding.description}",
                    f"- Recommendation: {finding.recommendation or 'None'}",
                    "",
                ]
            )
    else:
        lines.append("- None.")

    lines.extend(
        [
            "",
            "## Safety Limits",
            "",
            "- Intake files must not be cited in citizen answers.",
            "- Official URL presence does not prove official status.",
            "- Claimed publisher must be verified during review.",
            "- Review checklist is still required.",
            "- Source publishing remains separate.",
            "- No automatic publishing.",
            "- No network/provider used.",
            "- Closed beta/public launch remain false.",
            "",
            "## Notes",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines) + "\n"


def _report(
    path: Path,
    intake_exists: bool,
    template_only: bool,
    status: str,
    candidates: list[OfficialSourceIntakeCandidate],
    findings: list[OfficialSourceIntakeFinding],
) -> OfficialSourceIntakeReport:
    ready_count = 0 if template_only or _has_blockers(findings) else sum(
        1 for candidate in candidates if _candidate_ready_for_review(candidate)
    )
    warning_count = sum(1 for finding in findings if finding.severity == "warning")
    blocker_count = sum(1 for finding in findings if finding.severity == "blocker")
    return OfficialSourceIntakeReport(
        intake_path=str(path),
        intake_exists=intake_exists,
        template_only=template_only,
        total_candidates=len(candidates),
        ready_for_review_count=ready_count,
        blocked_count=max(0, len(candidates) - ready_count),
        warning_count=warning_count,
        blocker_count=blocker_count,
        status=status,
        candidates=candidates,
        findings=findings,
        sanitized_summary=_sanitized_summary(candidates),
        ready_for_closed_beta=False,
        ready_for_public_launch=False,
        used_network=False,
        used_external_provider=False,
        notes=[
            "Official source intake is metadata validation only.",
            "Intake candidates are not trusted evidence.",
            "Candidate URL presence does not prove official status.",
            "No URL fetching, network access, provider call, registry write, or "
            "publishing occurred.",
            "Local intake files must remain ignored unless deliberately promoted through review.",
        ],
    )


def _status_for_report(
    template_only: bool,
    candidates: list[OfficialSourceIntakeCandidate],
    findings: list[OfficialSourceIntakeFinding],
) -> str:
    if any(finding.finding_id.startswith("INTAKE-SECRET") for finding in findings):
        return "blocked_secret_pattern"
    if any(finding.finding_id.startswith("INTAKE-SENSITIVE") for finding in findings):
        return "blocked_sensitive_data"
    if any(finding.severity == "blocker" for finding in findings):
        return "invalid"
    if template_only:
        return "template_only"
    if candidates and all(_candidate_ready_for_review(candidate) for candidate in candidates):
        return "ready_for_review"
    return "valid_metadata_only"


def _raw_candidate_items(data: dict) -> list[Any]:
    raw_candidates = data.get("candidates")
    if isinstance(raw_candidates, list):
        return raw_candidates
    if isinstance(raw_candidates, dict):
        return [raw_candidates]
    if any(key in data for key in ("domain", "proposed_trust_tier", "source_url")):
        return [data]
    return []


def _candidate_from_raw(raw_candidate: dict, index: int) -> OfficialSourceIntakeCandidate:
    domain = _safe_text(raw_candidate.get("domain")) or "unknown"
    trust_tier = _safe_text(raw_candidate.get("proposed_trust_tier")) or "unknown"
    intake_id = _safe_text(raw_candidate.get("intake_id")) or f"intake-candidate-{index}"
    return OfficialSourceIntakeCandidate(
        intake_id=intake_id,
        domain=domain,
        proposed_trust_tier=trust_tier,
        source_title=_safe_text(raw_candidate.get("source_title")),
        source_url=_safe_url(raw_candidate.get("source_url")),
        source_document_ref=_safe_text(raw_candidate.get("source_document_ref")),
        claimed_publisher=_safe_text(raw_candidate.get("claimed_publisher")),
        jurisdiction_or_scope=_safe_text(raw_candidate.get("jurisdiction_or_scope")),
        language=_safe_text(raw_candidate.get("language")),
        freshness_note=_safe_text(raw_candidate.get("freshness_note")),
        source_version_note=_safe_text(raw_candidate.get("source_version_note")),
        related_gap_id=_safe_text(raw_candidate.get("related_gap_id")),
        related_acquisition_task_id=_safe_text(
            raw_candidate.get("related_acquisition_task_id")
        ),
        notes=[note for note in (_safe_text(item) for item in _raw_notes(raw_candidate)) if note],
        not_trusted_until_reviewed=True,
    )


def _raw_notes(raw_candidate: dict) -> list[Any]:
    notes = raw_candidate.get("notes", [])
    if isinstance(notes, list):
        return notes
    if notes:
        return [notes]
    return []


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    stripped = value.strip()
    if not stripped:
        return None
    if _sensitive_category(stripped) is not None:
        return "[redacted]"
    return stripped


def _safe_url(value: Any) -> str | None:
    text = _safe_text(value)
    if text is None or text == "[redacted]":
        return text
    parsed = urlparse(text)
    if not parsed.scheme and not parsed.netloc:
        return text
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _is_plausible_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _missing_required_metadata(candidate: OfficialSourceIntakeCandidate) -> list[str]:
    missing: list[str] = []
    if not candidate.domain or candidate.domain == "unknown":
        missing.append("domain")
    if not candidate.proposed_trust_tier or candidate.proposed_trust_tier == "unknown":
        missing.append("proposed_trust_tier")
    if not (candidate.source_title or candidate.source_document_ref):
        missing.append("title_or_document_ref")
    if not (candidate.source_url or candidate.source_document_ref):
        missing.append("url_or_document_ref")
    if not candidate.claimed_publisher:
        missing.append("claimed_publisher")
    if not candidate.jurisdiction_or_scope:
        missing.append("jurisdiction_or_scope")
    if not candidate.language:
        missing.append("language")
    if not (candidate.freshness_note or candidate.source_version_note):
        missing.append("freshness_or_version_note")
    return missing


def _candidate_ready_for_review(candidate: OfficialSourceIntakeCandidate) -> bool:
    if _missing_required_metadata(candidate):
        return False
    if candidate.proposed_trust_tier not in OFFICIAL_SOURCE_TIERS:
        return False
    if candidate.source_url and not _is_plausible_url(candidate.source_url):
        return False
    return candidate.not_trusted_until_reviewed


def _has_blockers(findings: list[OfficialSourceIntakeFinding]) -> bool:
    return any(finding.severity == "blocker" for finding in findings)


def _iter_string_values(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_string_values(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_string_values(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def _sensitive_category(value: str) -> str | None:
    if EMAIL_PATTERN.search(value) or PHONE_PATTERN.search(value):
        return "sensitive"
    if (
        SECRET_TERM_PATTERN.search(value)
        or SK_KEY_PATTERN.search(value)
        or PRIVATE_KEY_PATTERN.search(value)
        or _looks_high_entropy_secret(value)
    ):
        return "secret"
    return None


def _looks_high_entropy_secret(value: str) -> bool:
    compact = re.sub(r"\s+", "", value)
    if len(compact) < 32 or compact.startswith(("http://", "https://")):
        return False
    if not re.fullmatch(r"[A-Za-z0-9_+=/.-]+", compact):
        return False
    unique_ratio = len(set(compact)) / len(compact)
    if unique_ratio < 0.45:
        return False
    return _shannon_entropy(compact) > 4.0


def _shannon_entropy(value: str) -> float:
    counts = {character: value.count(character) for character in set(value)}
    return -sum((count / len(value)) * math.log2(count / len(value)) for count in counts.values())


def _sanitized_summary(candidates: list[OfficialSourceIntakeCandidate]) -> dict[str, object]:
    return {
        "domains": _unique([candidate.domain for candidate in candidates]),
        "trust_tiers": _unique([candidate.proposed_trust_tier for candidate in candidates]),
        "url_hosts": _unique(
            [
                urlparse(candidate.source_url).netloc
                for candidate in candidates
                if candidate.source_url and _is_plausible_url(candidate.source_url)
            ]
        ),
        "not_trusted_until_reviewed_count": sum(
            1 for candidate in candidates if candidate.not_trusted_until_reviewed
        ),
    }


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
