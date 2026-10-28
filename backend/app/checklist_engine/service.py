from backend.app.checklist_engine.models import (
    ChecklistGenerationRequest,
    ChecklistGenerationResult,
    ChecklistProfileContext,
    ChecklistTemplateItem,
)
from backend.app.checklist_engine.policies import (
    checklist_priority_for_item,
    checklist_requires_escalation_step,
    checklist_requires_official_source,
    should_include_item,
)
from backend.app.checklist_engine.templates import template_items_for_scenario
from backend.app.checklist_engine.validation import validate_checklist
from backend.app.domain.checklists import Checklist, ChecklistItem
from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario

PRIORITY_VALUES = {"high": 1, "medium": 2, "low": 3}


class ChecklistEngineService:
    def generate(self, request: ChecklistGenerationRequest) -> ChecklistGenerationResult:
        return self.generate_for_scenario(
            scenario=request.scenario,
            risk_level=request.risk_level,
            language=request.language,
            user_profile=request.user_profile,
            selected_source_ids=request.selected_source_ids,
            safety_flags=request.safety_flags,
            approved_context=request.approved_context,
            preparation_only=request.preparation_only,
        )

    def generate_for_scenario(
        self,
        scenario: UserScenario,
        risk_level: RiskLevel = RiskLevel.normal,
        language: LanguageCode = LanguageCode.ru,
        user_profile=None,
        selected_source_ids: list[str] | None = None,
        safety_flags: list[str] | None = None,
        approved_context: ChecklistProfileContext | None = None,
        preparation_only: bool = False,
    ) -> ChecklistGenerationResult:
        context = approved_context or ChecklistProfileContext(
            city=getattr(user_profile, "city", None),
        )
        selected_source_ids = selected_source_ids or []
        safety_flags = safety_flags or []
        templates = template_items_for_scenario(scenario)
        if preparation_only:
            from backend.app.workspace.checklist_plan import preparation_steps

            # Existing localized preparation copy now flows through the same engine.
            templates = [ChecklistTemplateItem(
                item_id=key, title=title, description=title,
                group="urgent" if risk_level == RiskLevel.emergency else (
                    "first_week" if key == "enrollment" else "before_arrival"
                ),
            ) for key, title in preparation_steps(scenario, language)]
            # A preparation template is not reviewed guidance or a citation binding.
            selected_source_ids = []
        template_items = [
            item
            for item in templates
            if should_include_item(item, risk_level, safety_flags)
        ]
        template_items = self._ensure_policy_items(
            template_items=template_items,
            scenario=scenario,
            risk_level=risk_level,
            safety_flags=safety_flags,
            language=language,
        )
        checklist = Checklist(
            checklist_id=f"phase18-{scenario.value}-{risk_level.value}-{language.value}",
            title=f"{_language_prefix(language)} {scenario.value} checklist",
            scenario=scenario,
            language=language,
            items=[
                self._to_checklist_item(
                    template_item=item,
                    scenario=scenario,
                    risk_level=risk_level,
                    selected_source_ids=selected_source_ids,
                    context=context,
                )
                for item in template_items
            ],
        )
        report = validate_checklist(
            checklist=checklist,
            scenario=scenario,
            risk_level=risk_level,
            selected_source_ids=selected_source_ids,
            safety_flags=safety_flags,
        )
        return ChecklistGenerationResult(
            checklist=checklist,
            warnings=[finding.summary for finding in report.findings] + (
                ["reviewed_guidance_unavailable", "documents_and_duration_need_confirmation"]
                + (["context_missing_city"] if not context.city else [])
                if preparation_only else []
            ),
            source_ids=list(selected_source_ids),
            escalation_recommended=checklist_requires_escalation_step(
                risk_level,
                safety_flags,
            ),
        )

    def _ensure_policy_items(
        self,
        template_items: list[ChecklistTemplateItem],
        scenario: UserScenario,
        risk_level: RiskLevel,
        safety_flags: list[str],
        language: LanguageCode,
    ) -> list[ChecklistTemplateItem]:
        items = list(template_items)
        combined_text = " ".join(
            f"{item.title} {item.description or ''}".casefold() for item in items
        )
        if checklist_requires_official_source(scenario, risk_level):
            if not _has_official_confirmation(combined_text):
                items.append(
                    ChecklistTemplateItem(
                        item_id="official-confirmation",
                        title=_localized_policy_copy("official-confirmation", language)[0],
                        description=_localized_policy_copy("official-confirmation", language)[1],
                        source_required=True,
                        group="urgent" if risk_level != RiskLevel.normal else "before_arrival",
                    )
                )
        if checklist_requires_escalation_step(risk_level, safety_flags):
            if not any(item.escalation_relevant for item in items) and not (
                _has_escalation_step(combined_text)
            ):
                items.append(
                    ChecklistTemplateItem(
                        item_id="human-escalation",
                        title=_localized_policy_copy("human-escalation", language)[0],
                        description=_localized_policy_copy("human-escalation", language)[1],
                        escalation_relevant=True,
                        group="urgent",
                    )
                )
        return items

    def _to_checklist_item(
        self,
        template_item: ChecklistTemplateItem,
        scenario: UserScenario,
        risk_level: RiskLevel,
        selected_source_ids: list[str],
        context: ChecklistProfileContext | None = None,
    ) -> ChecklistItem:
        priority = checklist_priority_for_item(template_item, risk_level)
        source_ids = [
            source_id for source_id in selected_source_ids if not source_id.startswith("COM-")
        ]
        community_source_ids = [
            source_id for source_id in selected_source_ids if source_id.startswith("COM-")
        ]
        return ChecklistItem(
            item_id=f"{scenario.value}-{template_item.item_id}",
            title=template_item.title,
            description=" · ".join(filter(None, [
                _description_with_risk_note(template_item),
                context.city if context else None,
                context.purpose if context else None,
                context.institution if context else None,
            ])),
            priority=PRIORITY_VALUES[priority],
            scenario=scenario,
            risk_level=risk_level,
            source_ids=source_ids if template_item.source_required else [],
            community_source_ids=community_source_ids,
            group=template_item.group,
            required_documents=template_item.required_documents,
            estimated_time=template_item.estimated_time,
            action="support" if template_item.escalation_relevant else "chat",
        )


def _description_with_risk_note(template_item: ChecklistTemplateItem) -> str | None:
    if template_item.risk_note:
        return f"{template_item.description or ''} {template_item.risk_note}".strip()
    return template_item.description


def _has_official_confirmation(text: str) -> bool:
    return "official" in text or "professional" in text or "consular" in text


def _has_escalation_step(text: str) -> bool:
    return "escalat" in text or "human" in text or "emergency support" in text


def _language_prefix(language: LanguageCode) -> str:
    return {
        LanguageCode.ru: "Практический",
        LanguageCode.kk: "Практикалық",
        LanguageCode.zh: "实用",
        LanguageCode.en: "Practical",
        LanguageCode.unknown: "Practical",
    }[language]


_POLICY_ITEM_COPY = {
    "official-confirmation": {
        LanguageCode.ru: (
            "Уточнить требования в официальном источнике",
            (
                "Перед действием проверьте требования консульства, ведомства "
                "или профильного специалиста."
            ),
        ),
        LanguageCode.kk: (
            "Талаптарды ресми дереккөзден нақтылау",
            "Әрекет жасамас бұрын консулдықтың, мекеменің немесе маманның талаптарын тексеріңіз.",
        ),
        LanguageCode.zh: (
            "向官方渠道确认要求",
            "采取行动前，请核实领事机构、相关部门或专业人士的要求。",
        ),
        LanguageCode.en: (
            "Confirm requirements with an official source",
            "Check consular, institutional, or professional guidance before acting.",
        ),
    },
    "human-escalation": {
        LanguageCode.ru: (
            "Обратиться за помощью к специалисту",
            (
                "Попросите профильного специалиста, официальную службу или "
                "экстренную помощь проверить ситуацию."
            ),
        ),
        LanguageCode.kk: (
            "Маманнан көмек сұрау",
            "Жағдайды профильді маманға, ресми қызметке немесе шұғыл көмекке көрсетіңіз.",
        ),
        LanguageCode.zh: (
            "请专业人员协助处理",
            "请相关专业人士、官方机构或紧急服务协助核实情况。",
        ),
        LanguageCode.en: (
            "Ask a specialist for help",
            (
                "Ask a qualified professional, official service, or emergency "
                "support to review the situation."
            ),
        ),
    },
}


def _localized_policy_copy(item_id: str, language: LanguageCode) -> tuple[str, str]:
    copies = _POLICY_ITEM_COPY[item_id]
    return copies.get(language, copies[LanguageCode.en])
