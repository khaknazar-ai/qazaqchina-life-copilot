from enum import StrEnum


class LanguageCode(StrEnum):
    ru = "ru"
    kk = "kk"
    zh = "zh"
    en = "en"
    unknown = "unknown"


class UserScenario(StrEnum):
    tourism = "tourism"
    kazakhstan_entry = "kazakhstan_entry"
    study = "study"
    work = "work"
    business = "business"
    medical = "medical"
    emergency = "emergency"
    documents = "documents"
    housing = "housing"
    payments = "payments"
    transport = "transport"
    translation = "translation"
    community_experience = "community_experience"
    unclear = "unclear"


class RiskLevel(StrEnum):
    normal = "normal"
    medium = "medium"
    legal_sensitive = "legal_sensitive"
    work_status_sensitive = "work_status_sensitive"
    medical_sensitive = "medical_sensitive"
    emergency = "emergency"
    unsafe = "unsafe"
    prompt_injection = "prompt_injection"


class SourceType(StrEnum):
    official = "official"
    curated_guide = "curated_guide"
    verified_institutional_contributor = "verified_institutional_contributor"
    verified_experienced_contributor = "verified_experienced_contributor"
    ordinary_community = "ordinary_community"
    untrusted = "untrusted"


class TrustLevel(StrEnum):
    level_1_official = "level_1_official"
    level_2_curated = "level_2_curated"
    level_3_verified_institutional = "level_3_verified_institutional"
    level_4_verified_experienced = "level_4_verified_experienced"
    level_5_ordinary_community = "level_5_ordinary_community"
    level_6_untrusted = "level_6_untrusted"


class VerifiedContributorRole(StrEnum):
    ordinary_user = "ordinary_user"
    verified_student = "verified_student"
    verified_worker = "verified_worker"
    verified_business_visitor = "verified_business_visitor"
    verified_medical_visitor = "verified_medical_visitor"
    verified_consular_worker = "verified_consular_worker"
    verified_vice_consul = "verified_vice_consul"
    verified_consul = "verified_consul"
    admin_curator = "admin_curator"


class VerificationStatus(StrEnum):
    unverified = "unverified"
    verification_requested = "verification_requested"
    verified = "verified"
    verification_rejected = "verification_rejected"
    verification_expired = "verification_expired"
    revoked = "revoked"


class ModerationStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    needs_review = "needs_review"
    rejected = "rejected"
    flagged = "flagged"


class ChecklistItemStatus(StrEnum):
    not_started = "not_started"
    in_progress = "in_progress"
    done = "done"
    blocked = "blocked"
    skipped = "skipped"


class CaseStatus(StrEnum):
    open = "open"
    waiting_for_user = "waiting_for_user"
    escalated = "escalated"
    resolved = "resolved"
    closed = "closed"


class EscalationReason(StrEnum):
    legal_sensitive = "legal_sensitive"
    work_status_sensitive = "work_status_sensitive"
    medical_sensitive = "medical_sensitive"
    emergency = "emergency"
    source_conflict = "source_conflict"
    low_confidence = "low_confidence"
    missing_critical_info = "missing_critical_info"
    user_requested_human = "user_requested_human"
    safety_risk = "safety_risk"
