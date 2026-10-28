from backend.app.checklist_engine.models import ChecklistTemplateItem
from backend.app.domain.enums import ChecklistItemStatus, LanguageCode, RiskLevel, UserScenario

OFFICIAL_SOURCE_RISK_LEVELS = {
    RiskLevel.legal_sensitive,
    RiskLevel.work_status_sensitive,
    RiskLevel.medical_sensitive,
    RiskLevel.emergency,
}

ESCALATION_RISK_LEVELS = {
    RiskLevel.emergency,
    RiskLevel.unsafe,
    RiskLevel.prompt_injection,
    RiskLevel.legal_sensitive,
    RiskLevel.work_status_sensitive,
    RiskLevel.medical_sensitive,
}

ESCALATION_FLAGS = {
    "source_governance_failed",
    "source_conflict",
    "prompt_injection",
    "unsafe_request",
    "unsafe_work_advice",
    "emergency",
    "missing_official_source",
    "high_risk_without_official_source",
    "citation_verification_failed",
    "human_escalation_required",
}

STATUS_LABELS = {
    LanguageCode.ru: {
        ChecklistItemStatus.not_started: "Не начато",
        ChecklistItemStatus.in_progress: "В процессе",
        ChecklistItemStatus.done: "Готово",
        ChecklistItemStatus.blocked: "Заблокировано",
        ChecklistItemStatus.skipped: "Пропущено",
    },
    LanguageCode.kk: {
        ChecklistItemStatus.not_started: "Басталмады",
        ChecklistItemStatus.in_progress: "Орындалуда",
        ChecklistItemStatus.done: "Дайын",
        ChecklistItemStatus.blocked: "Бөгелді",
        ChecklistItemStatus.skipped: "Өткізілді",
    },
    LanguageCode.zh: {
        ChecklistItemStatus.not_started: "未开始",
        ChecklistItemStatus.in_progress: "进行中",
        ChecklistItemStatus.done: "已完成",
        ChecklistItemStatus.blocked: "受阻",
        ChecklistItemStatus.skipped: "已跳过",
    },
    LanguageCode.en: {
        ChecklistItemStatus.not_started: "Not started",
        ChecklistItemStatus.in_progress: "In progress",
        ChecklistItemStatus.done: "Done",
        ChecklistItemStatus.blocked: "Blocked",
        ChecklistItemStatus.skipped: "Skipped",
    },
}


def checklist_requires_official_source(
    scenario: UserScenario,
    risk_level: RiskLevel,
) -> bool:
    return scenario in {
        UserScenario.work,
        UserScenario.medical,
        UserScenario.emergency,
    } or risk_level in OFFICIAL_SOURCE_RISK_LEVELS


def checklist_requires_escalation_step(
    risk_level: RiskLevel,
    safety_flags: list[str],
) -> bool:
    return risk_level in ESCALATION_RISK_LEVELS or any(
        flag in ESCALATION_FLAGS for flag in safety_flags
    )


def checklist_priority_for_item(item: ChecklistTemplateItem, risk_level: RiskLevel) -> str:
    if item.escalation_relevant or risk_level in {
        RiskLevel.emergency,
        RiskLevel.work_status_sensitive,
        RiskLevel.medical_sensitive,
        RiskLevel.legal_sensitive,
    }:
        return "high"
    if item.source_required or risk_level == RiskLevel.medium:
        return "medium"
    return "low"


def should_include_item(
    item: ChecklistTemplateItem,
    risk_level: RiskLevel,
    safety_flags: list[str],
) -> bool:
    del risk_level, safety_flags
    return item.required


def localized_status_label(status: ChecklistItemStatus, language: LanguageCode) -> str:
    labels = STATUS_LABELS.get(language, STATUS_LABELS[LanguageCode.ru])
    return labels[status]
