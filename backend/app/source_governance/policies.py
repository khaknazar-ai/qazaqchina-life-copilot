from backend.app.domain.enums import RiskLevel, SourceType
from backend.app.domain.sources import SourceReference

HIGH_RISK_LEVELS = {
    RiskLevel.legal_sensitive,
    RiskLevel.work_status_sensitive,
    RiskLevel.medical_sensitive,
    RiskLevel.emergency,
    RiskLevel.unsafe,
    RiskLevel.prompt_injection,
}

COMMUNITY_OR_CONTRIBUTOR_SOURCE_TYPES = {
    SourceType.verified_institutional_contributor,
    SourceType.verified_experienced_contributor,
    SourceType.ordinary_community,
}

OFFICIAL_OR_CURATED_SOURCE_TYPES = {
    SourceType.official,
    SourceType.curated_guide,
}


def is_high_risk_level(risk_level: RiskLevel) -> bool:
    return risk_level in HIGH_RISK_LEVELS


def requires_official_or_curated_sources(risk_level: RiskLevel) -> bool:
    return is_high_risk_level(risk_level)


def is_community_or_contributor_source(source: SourceReference) -> bool:
    return source.source_type in COMMUNITY_OR_CONTRIBUTOR_SOURCE_TYPES


def is_official_or_curated_source(source: SourceReference) -> bool:
    return source.source_type in OFFICIAL_OR_CURATED_SOURCE_TYPES


def source_requires_community_label(source: SourceReference) -> bool:
    return is_community_or_contributor_source(source)
