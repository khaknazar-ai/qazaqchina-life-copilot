from pathlib import Path
from typing import Any

from backend.app.schemas.chat import ChatRequest
from backend.app.services.chat_service import ChatService
from backend.app.source_review_answer_constraints.chat_integration import (
    answer_contains_unpublished_candidate_reference,
    classify_source_review_chat_constraint,
    detect_source_review_constraint_domain,
)
from backend.app.source_review_regression.models import (
    SourceReviewRegressionCase,
    SourceReviewRegressionReport,
    SourceReviewRegressionResult,
)
from scripts.inspect_miniprogram_source_review_ui import (
    inspect_miniprogram_source_review_ui,
)

CONSTRAINED_REQUIRED_METADATA_FIELDS = [
    "has_source_review_constraints",
    "source_review_constraint",
    "required_official_verification_warning",
    "prohibited_claim_types",
    "citizen_visible_source_review_disclosure_allowed",
]

CONSTRAINED_PROHIBITED_PHRASES = [
    "you must submit exactly",
    "the deadline is always",
    "guaranteed approval",
    "this is legally sufficient",
    "official source under review says",
    "candidate source",
    "publish preview proves",
    "reviewer packet",
]

INTERNAL_AUTHORITY_MARKERS = [
    "source candidates under review prove",
    "publish preview proves",
    "reviewer packet proves",
    "review evidence proves",
    "official source under review says",
]


class SourceReviewConstraintRegressionService:
    def __init__(self, project_root: Path | str = ".") -> None:
        self.project_root = Path(project_root)
        self.chat_service = ChatService()
        self._miniprogram_report: dict[str, Any] | None = None

    def build_cases(self) -> list[SourceReviewRegressionCase]:
        return [
            SourceReviewRegressionCase(
                case_id="english-visa-extension",
                title="English visa extension remains constrained",
                query="How do I extend my visa in China?",
                expected_domain="visa_extension",
                should_be_constrained=True,
                expected_warning_required=True,
                prohibited_phrases=list(CONSTRAINED_PROHIBITED_PHRASES),
                required_metadata_fields=list(CONSTRAINED_REQUIRED_METADATA_FIELDS),
                notes=[
                    "Unpublished visa-extension candidates must not be cited.",
                    "High-risk visa questions must not get deadline or approval certainty.",
                ],
            ),
            SourceReviewRegressionCase(
                case_id="russian-visa-extension",
                title="Russian visa extension remains constrained",
                query="Как продлить визу в Китае?",
                expected_domain="visa_extension",
                should_be_constrained=True,
                expected_warning_required=True,
                prohibited_phrases=list(CONSTRAINED_PROHIBITED_PHRASES),
                required_metadata_fields=list(CONSTRAINED_REQUIRED_METADATA_FIELDS),
                notes=[
                    "Russian visa-extension phrasing must hit the same safety path.",
                ],
            ),
            SourceReviewRegressionCase(
                case_id="english-residence-registration",
                title="English residence registration remains constrained",
                query="How do I register my accommodation with the police?",
                expected_domain="residence_registration",
                should_be_constrained=True,
                expected_warning_required=True,
                prohibited_phrases=list(CONSTRAINED_PROHIBITED_PHRASES),
                required_metadata_fields=list(CONSTRAINED_REQUIRED_METADATA_FIELDS),
                notes=[
                    "Residence-registration chat must require official local verification.",
                ],
            ),
            SourceReviewRegressionCase(
                case_id="russian-residence-registration",
                title="Russian residence registration remains constrained",
                query="Как сделать регистрацию проживания в полиции в Китае?",
                expected_domain="residence_registration",
                should_be_constrained=True,
                expected_warning_required=True,
                prohibited_phrases=list(CONSTRAINED_PROHIBITED_PHRASES),
                required_metadata_fields=list(CONSTRAINED_REQUIRED_METADATA_FIELDS),
                notes=[
                    "Russian residence-registration phrasing must hit the same safety path.",
                ],
            ),
            SourceReviewRegressionCase(
                case_id="low-risk-sim-card",
                title="Low-risk SIM card query is not over-constrained",
                query="Where can I buy a SIM card?",
                expected_domain=None,
                should_be_constrained=False,
                expected_warning_required=False,
                expected_low_risk=True,
            ),
            SourceReviewRegressionCase(
                case_id="low-risk-dorm-packing",
                title="Low-risk dorm packing query is not over-constrained",
                query="What should I pack for university dorm life?",
                expected_domain=None,
                should_be_constrained=False,
                expected_warning_required=False,
                expected_low_risk=True,
            ),
            SourceReviewRegressionCase(
                case_id="low-risk-translation",
                title="Low-risk translation query is not over-constrained",
                query="Translate this sentence into Russian: hello.",
                expected_domain=None,
                should_be_constrained=False,
                expected_warning_required=False,
                expected_low_risk=True,
            ),
        ]

    def run_case(self, case: SourceReviewRegressionCase) -> SourceReviewRegressionResult:
        response = self.chat_service.create_response(
            ChatRequest(user_message=case.query, preferred_language="en")
        )
        response_data = response.model_dump(mode="json")
        answer = str(response_data.get("answer") or "")
        detected_domain = detect_source_review_constraint_domain(case.query)
        detected_constraint = classify_source_review_chat_constraint(case.query)
        constrained = bool(response_data.get("has_source_review_constraints"))
        warning = response_data.get("required_official_verification_warning")
        warning_present = bool(warning and warning in answer)
        prohibited_phrase_found = _contains_any(answer, case.prohibited_phrases)
        unpublished_candidate_cited = _unpublished_candidate_cited(response_data, answer)
        required_metadata_present = _required_metadata_present(
            response_data,
            case.required_metadata_fields,
        )
        miniprogram_renderable = self._miniprogram_renderable(case)

        findings = []
        if detected_domain != case.expected_domain:
            findings.append(
                f"Detected domain {detected_domain!r}; expected {case.expected_domain!r}."
            )
        if constrained != case.should_be_constrained:
            findings.append(
                f"Constrained={constrained}; expected {case.should_be_constrained}."
            )
        if warning_present != case.expected_warning_required:
            findings.append(
                "Official verification warning presence did not match expectation."
            )
        if prohibited_phrase_found:
            findings.append("Answer contained prohibited overconfident wording.")
        if unpublished_candidate_cited:
            findings.append("Answer or citation referenced unpublished candidate material.")
        if not required_metadata_present:
            findings.append("Required backend metadata fields were missing or empty.")
        if detected_constraint and detected_constraint.official_source_published:
            findings.append("Constraint unexpectedly treated source as published.")
        if detected_constraint and detected_constraint.allowed_mode == "direct_answer_allowed":
            findings.append("Constrained domain unexpectedly allowed direct answer mode.")
        if not miniprogram_renderable:
            findings.append("Mini Program static UI cannot render expected warning metadata.")
        if case.expected_low_risk and response_data.get("requires_official_source"):
            findings.append("Low-risk case was forced into official-source requirement.")
        if _contains_any(answer, INTERNAL_AUTHORITY_MARKERS):
            findings.append("Internal source-review progress was presented as authority.")

        return SourceReviewRegressionResult(
            case_id=case.case_id,
            passed=not findings,
            detected_domain=detected_domain,
            constrained=constrained,
            warning_present=warning_present,
            prohibited_phrase_found=prohibited_phrase_found,
            unpublished_candidate_cited=unpublished_candidate_cited,
            required_metadata_present=required_metadata_present,
            miniprogram_renderable=miniprogram_renderable,
            findings=findings,
        )

    def run(self) -> SourceReviewRegressionReport:
        cases = self.build_cases()
        results = [self.run_case(case) for case in cases]
        return SourceReviewRegressionReport(
            total_cases=len(cases),
            passed_cases=sum(result.passed for result in results),
            failed_cases=sum(not result.passed for result in results),
            constrained_cases=sum(result.constrained for result in results),
            low_risk_cases=sum(case.expected_low_risk for case in cases),
            unpublished_candidate_citation_count=sum(
                result.unpublished_candidate_cited for result in results
            ),
            prohibited_phrase_count=sum(
                result.prohibited_phrase_found for result in results
            ),
            miniprogram_renderable_count=sum(
                result.miniprogram_renderable for result in results
            ),
            ready_for_closed_beta=False,
            ready_for_public_launch=False,
            used_network=False,
            used_external_provider=False,
            cases=cases,
            results=results,
            notes=[
                "Source review constraint regression must not cite unpublished candidates.",
                "Source review progress is not official authority.",
                "Source candidates, reviewer packets, review evidence, and publish preview "
                "packages are not trusted evidence.",
                "Visa-extension and residence-registration remain constrained while "
                "published official source coverage is missing.",
                "Low-risk chat must not be over-constrained.",
                "Publish preview is not publishing and this suite performs no registry write.",
                "Closed beta and public launch remain false.",
                "No network, external provider, OCR, source publishing, or trusted registry "
                "write occurred.",
            ],
        )

    def _miniprogram_renderable(self, case: SourceReviewRegressionCase) -> bool:
        report = self._miniprogram_report_data()
        if case.should_be_constrained:
            metadata_references = report.get("metadata_references", {})
            return bool(
                report.get("source_review_warning_rendered")
                and report.get("required_warning_supported")
                and report.get("unpublished_candidates_hidden")
                and all(
                    metadata_references.get(field)
                    for field in case.required_metadata_fields
                )
            )
        return bool(report.get("low_risk_overwarning_guard_present"))

    def _miniprogram_report_data(self) -> dict[str, Any]:
        if self._miniprogram_report is None:
            self._miniprogram_report = inspect_miniprogram_source_review_ui(
                self.project_root
            )
        return self._miniprogram_report


def _required_metadata_present(
    response_data: dict[str, Any],
    fields: list[str],
) -> bool:
    if not fields:
        return True
    for field in fields:
        if field not in response_data:
            return False
        value = response_data[field]
        if field == "has_source_review_constraints" and value is not True:
            return False
        if field == "citizen_visible_source_review_disclosure_allowed" and value is not False:
            return False
        if field not in {
            "has_source_review_constraints",
            "citizen_visible_source_review_disclosure_allowed",
        } and not value:
            return False
    return True


def _unpublished_candidate_cited(response_data: dict[str, Any], answer: str) -> bool:
    if answer_contains_unpublished_candidate_reference(answer):
        return True
    citations = response_data.get("citations") or []
    citation_text = " ".join(str(citation) for citation in citations)
    return answer_contains_unpublished_candidate_reference(citation_text)


def _contains_any(text: str, phrases: list[str]) -> bool:
    normalized = " ".join(str(text or "").casefold().split())
    return any(phrase.casefold() in normalized for phrase in phrases)
