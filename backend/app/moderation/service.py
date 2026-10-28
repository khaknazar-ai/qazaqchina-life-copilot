from backend.app.domain.community import CommunityPost
from backend.app.domain.enums import ModerationStatus
from backend.app.moderation.checks import (
    collect_post_text,
    detect_emergency_misinformation,
    detect_hate_or_harassment,
    detect_legal_or_work_status_risk,
    detect_medical_risk,
    detect_pii,
    detect_prompt_injection,
    detect_spam_or_scam,
    detect_unsafe_work_advice,
)
from backend.app.moderation.models import ModerationFinding, ModerationResult


class CommunityModerationService:
    def moderate_post(self, post: CommunityPost) -> ModerationResult:
        text = collect_post_text(post)
        findings = [
            *detect_pii(text),
            *detect_spam_or_scam(text),
            *detect_unsafe_work_advice(text),
            *detect_legal_or_work_status_risk(text),
            *detect_medical_risk(text),
            *detect_emergency_misinformation(text),
            *detect_hate_or_harassment(text),
            *detect_prompt_injection(text),
        ]
        return ModerationResult(
            status_recommendation=self.recommend_status(findings),
            allow_ai_retrieval_recommendation=False,
            findings=findings,
            needs_admin_review=True,
            review_reasons=self.review_reasons(findings),
        )

    def recommend_status(self, findings: list[ModerationFinding]) -> ModerationStatus:
        if any(finding.severity == "high" for finding in findings):
            return ModerationStatus.flagged
        return ModerationStatus.needs_review

    def review_reasons(self, findings: list[ModerationFinding]) -> list[str]:
        if not findings:
            return ["human_review_required_before_ai_retrieval"]
        return list(dict.fromkeys(finding.finding_type for finding in findings))
