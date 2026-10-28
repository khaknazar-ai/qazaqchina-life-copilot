from backend.app.privacy.models import RetentionPolicy


def default_retention_policies() -> list[RetentionPolicy]:
    return [
        RetentionPolicy(
            category="conversation_turns",
            default_retention_days=90,
            description=(
                "Proposed local/dev default for conversation metadata and text. "
                "Production retention requires legal/privacy review."
            ),
            delete_on_request=True,
            requires_admin_review=True,
        ),
        RetentionPolicy(
            category="feedback",
            default_retention_days=180,
            description="Citizen feedback queue records for answer/source quality review.",
            delete_on_request=True,
            requires_admin_review=True,
        ),
        RetentionPolicy(
            category="escalation",
            default_retention_days=365,
            description="Escalation records retained for safety and operations review.",
            delete_on_request=True,
            requires_admin_review=True,
        ),
        RetentionPolicy(
            category="photo_metadata",
            default_retention_days=30,
            description="Photo intake metadata only; raw images are not stored.",
            delete_on_request=True,
            requires_admin_review=True,
        ),
        RetentionPolicy(
            category="admin_audit",
            default_retention_days=365,
            description="Admin audit events for accountable source and queue operations.",
            delete_on_request=False,
            requires_admin_review=True,
        ),
        RetentionPolicy(
            category="source_review_audit",
            default_retention_days=365,
            description="Source review audit events for governance and rollback review.",
            delete_on_request=False,
            requires_admin_review=True,
        ),
        RetentionPolicy(
            category="generated_reports",
            default_retention_days=30,
            description="Local/dev generated reports under reports/generated only.",
            delete_on_request=True,
            requires_admin_review=False,
        ),
        RetentionPolicy(
            category="privacy_delete_requests",
            default_retention_days=365,
            description="Delete/privacy request workflow records and redacted request text.",
            delete_on_request=False,
            requires_admin_review=True,
        ),
    ]
