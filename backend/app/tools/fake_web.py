from backend.app.retrieval.planner import RetrievalPlan
from backend.app.tools.models import ToolCallRequest, ToolCallResult
from backend.app.tools.policies import (
    add_plan_warnings_to_candidate,
    candidate_from_fake_result,
    evaluate_tool_request_safety,
)


class FakeWebSearchTool:
    def search(
        self,
        request: ToolCallRequest,
        plan: RetrievalPlan | None = None,
    ) -> ToolCallResult:
        safety_level, warnings, blocked_reason = evaluate_tool_request_safety(request, plan)
        if blocked_reason is not None:
            return ToolCallResult(
                tool_name=request.tool_name,
                query=request.query,
                safety_level=safety_level,
                warnings=warnings,
                blocked_reason=blocked_reason,
                used_network=False,
            )

        candidates = [
            add_plan_warnings_to_candidate(candidate, plan)
            for candidate in _fake_candidates_for_request(request)[: request.max_results]
        ]
        return ToolCallResult(
            tool_name=request.tool_name,
            query=request.query,
            safety_level=safety_level,
            candidates=candidates,
            warnings=warnings,
            used_network=False,
        )


def _fake_candidates_for_request(request: ToolCallRequest):
    normalized = f"{request.scenario or ''} {request.query}".casefold()
    language = request.language

    if _contains_any(normalized, ["passport", "consulate", "embassy", "document loss"]):
        return [
            candidate_from_fake_result(
                title="Embassy passport loss instructions",
                url="https://embassy.example/passport-loss",
                snippet=(
                    "Fake official-style candidate for reporting passport loss and "
                    "checking current consular instructions."
                ),
                language=language,
            ),
            candidate_from_fake_result(
                title="Traveler passport-loss story",
                url="https://forum.example/community-story",
                snippet=(
                    "Fake forum candidate with practical experience only; "
                    "not official procedure."
                ),
                language=language,
            ),
        ]

    if _contains_any(normalized, ["work", "contract", "employer", "permit"]):
        return [
            candidate_from_fake_result(
                title="Work authorization public service guide",
                url="https://example.gov.cn/work-authorization",
                snippet=(
                    "Fake official-style candidate about matching work activity to "
                    "lawful authorization."
                ),
                language=language,
            ),
            candidate_from_fake_result(
                title="Worker contract checklist experience",
                url="https://forum.example/work-contract-story",
                snippet="Fake community candidate for practical document questions only.",
                language=language,
            ),
        ]

    if _contains_any(normalized, ["visa", "registration", "police", "overstay"]):
        return [
            candidate_from_fake_result(
                title="Public security residence registration notice",
                url="https://example.gov.cn/residence-registration",
                snippet=(
                    "Fake official-style candidate about residence registration and "
                    "visa-related public service checks."
                ),
                language=language,
            ),
            candidate_from_fake_result(
                title="Blog note about registration timing",
                url="https://blog.example/registration-story",
                snippet=(
                    "Fake blog candidate that must not be treated as legal or "
                    "official guidance."
                ),
                language=language,
            ),
        ]

    if _contains_any(normalized, ["hospital", "medical", "injury", "fever"]):
        return [
            candidate_from_fake_result(
                title="Hospital registration preparation page",
                url="https://hospital.example/registration",
                snippet=(
                    "Fake official-style candidate for hospital registration preparation "
                    "and emergency escalation."
                ),
                language=language,
            ),
            candidate_from_fake_result(
                title="Visitor hospital payment experience",
                url="https://forum.example/hospital-payment-story",
                snippet="Fake community candidate for practical payment experience only.",
                language=language,
            ),
        ]

    if _contains_any(normalized, ["payment", "scam", "bank card", "wechat", "alipay", "sim"]):
        return [
            candidate_from_fake_result(
                title="Payment platform security reminders",
                url="https://wechat.example/security",
                snippet=(
                    "Fake platform-style candidate about avoiding verification-code "
                    "sharing and scams."
                ),
                language=language,
            ),
            candidate_from_fake_result(
                title="Community scam pattern report",
                url="https://forum.example/payment-scam-story",
                snippet="Fake community candidate for scam pattern examples requiring review.",
                language=language,
            ),
        ]

    if _contains_any(normalized, ["study", "student", "university", "dormitory"]):
        return [
            candidate_from_fake_result(
                title="University international registration page",
                url="https://university.example.edu/registration",
                snippet=(
                    "Fake university-style candidate about student registration and "
                    "international office steps."
                ),
                language=language,
            ),
            candidate_from_fake_result(
                title="Student dormitory check-in experience",
                url="https://forum.example/student-dormitory-story",
                snippet="Fake student experience candidate for practical context only.",
                language=language,
            ),
        ]

    return [
        candidate_from_fake_result(
            title="Curated local life preparation page",
            url="https://guide.example/life-preparation",
            snippet="Fake general-life candidate for review before source registry ingestion.",
            language=language,
        ),
        candidate_from_fake_result(
            title="Community local life checklist",
            url="https://forum.example/local-life-checklist",
            snippet="Fake community candidate with practical experience only.",
            language=language,
        ),
    ]


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)
