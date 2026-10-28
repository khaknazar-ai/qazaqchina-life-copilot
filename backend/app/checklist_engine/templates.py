from backend.app.checklist_engine.models import ChecklistTemplateItem
from backend.app.domain.enums import UserScenario


def template_items_for_scenario(scenario: UserScenario) -> list[ChecklistTemplateItem]:
    templates = {
        UserScenario.tourism: [
            _item(
                "passport-validity",
                "Check passport validity",
                "Confirm your passport is valid and keep booking details available.",
            ),
            _item(
                "official-entry-rules",
                "Confirm entry documents and visa/entry requirements from official source",
                "Check current entry or visa rules before travel.",
                source_required=True,
            ),
            _item(
                "hotel-address",
                "Confirm accommodation registration and save hotel/address information",
                "Keep hotel name, address, and phone available.",
            ),
            _item(
                "emergency-contacts",
                "Prepare emergency contacts",
                "Save local emergency and consular contacts.",
            ),
            _item(
                "payment-translation-basics",
                "Set up payment and translation basics",
                "Prepare backup payment and simple translation support.",
            ),
        ],
        UserScenario.kazakhstan_entry: [
            _item(
                "citizenship-and-passport-type",
                "Confirm citizenship country and passport type",
                'Visa conditions may differ by nationality and ordinary, ' \
                'service, or diplomatic passport.',
            ),
            _item(
                "visa-regime-and-stay",
                "Check the current visa regime and permitted stay",
                "Use the official Kazakhstan MFA table for the exact passport type and trip dates.",
                source_required=True,
            ),
            _item(
                "entry-purpose-and-activity",
                "Match the visa or entry basis to the actual purpose",
                "Do not assume visitor entry allows work, study, or residence.",
                source_required=True,
            ),
            _item(
                "evisa-invitation",
                "Check official e-Visa eligibility and invitation requirements if relevant",
                "Confirm eligibility by citizenship and purpose on the official visa portal.",
                source_required=True,
            ),
            _item(
                "arrival-notification",
                "Confirm arrival notification and accommodation steps",
                "Ask the hotel, host, or relevant official service what applies to this stay.",
                source_required=True,
            ),
        ],
        UserScenario.study: [
            _item(
                "enrollment-documents",
                "Verify admission/enrollment documents",
                "Prepare passport, admission notice, photos, and school forms.",
            ),
            _item(
                "student-official-requirements",
                "Confirm visa/residence permit requirements",
                "Check official or university international office instructions.",
                source_required=True,
            ),
            _item(
                "university-registration",
                "Prepare university registration documents",
                "Bring required forms and copies to registration.",
            ),
            _item(
                "international-office-contact",
                "Save university international office contact",
                "Keep office address, phone, and hours.",
            ),
            _item(
                "housing-insurance",
                "Check housing and address steps plus health insurance",
                "Confirm dorm, rental, and insurance requirements.",
            ),
        ],
        UserScenario.work: [
            _item(
                "legal-work-authorization",
                "Confirm legal work authorization and lawful work status before starting work",
                "Do not start paid work until work authorization is clear.",
                source_required=True,
                escalation_relevant=True,
            ),
            _item(
                "employer-documents",
                "Verify employer documents and contract",
                "Confirm employer process, contract terms, and permit steps.",
            ),
            _item(
                "avoid-tourist-work",
                "Do not work on tourist or invalid status",
                "Avoid any work if documents or authorization are unclear.",
                escalation_relevant=True,
            ),
            _item(
                "copies-contract-permits",
                "Keep copies of contract and permits",
                "Store copies of signed contract, permits, and official notices.",
            ),
            _item(
                "escalate-uncertain-work",
                "Escalate uncertain work-status cases",
                "Ask a qualified human or official source if status is unclear.",
                escalation_relevant=True,
            ),
        ],
        UserScenario.medical: [
            _item(
                "hospital-emergency-department",
                "Identify hospital/clinic and emergency department",
                "Confirm the right hospital entrance or emergency department.",
            ),
            _item(
                "passport-insurance-payment",
                "Bring passport/ID and insurance/payment info",
                "Prepare ID, payment method, insurance, and medication list.",
            ),
            _item(
                "avoid-community-medical-only",
                "Do not rely on community medical advice only",
                "Use community tips only for practical preparation.",
            ),
            _item(
                "medical-professional-confirmation",
                "Confirm diagnosis/treatment with medical professional",
                "Do not self-diagnose or take medicine without a clinician.",
                source_required=True,
            ),
            _item(
                "urgent-symptoms-emergency",
                "Use emergency care for urgent symptoms",
                "Seek urgent care for severe or worsening symptoms.",
                escalation_relevant=True,
            ),
        ],
        UserScenario.emergency: [
            _item(
                "immediate-safety",
                "Ensure immediate safety",
                "Move to a safe place and stay calm.",
            ),
            _item(
                "local-emergency-contact",
                "Contact local emergency services if urgent",
                "Call local emergency services when there is immediate danger.",
                escalation_relevant=True,
            ),
            _item(
                "consular-emergency",
                "Contact Kazakhstan embassy/consulate if passport/legal emergency",
                "Use official consular support for lost passport or legal emergency.",
                source_required=True,
                escalation_relevant=True,
            ),
            _item(
                "incident-details",
                "Document incident details",
                "Record time, place, people involved, and report numbers.",
            ),
            _item(
                "urgent-human-case",
                "Create urgent human escalation case",
                "Ask for human or official emergency support.",
                escalation_relevant=True,
            ),
        ],
        UserScenario.payments: [
            _item(
                "bank-app-requirements",
                "Prepare bank/payment app requirements",
                "Prepare passport, phone number, bank card, or platform verification details.",
            ),
            _item(
                "official-platform-rules",
                "Verify official bank/platform rules",
                "Use only official bank, Alipay, or WeChat Pay guidance.",
                source_required=True,
            ),
            _item(
                "backup-payment",
                "Keep backup payment method",
                "Carry backup cash or card while setup is pending.",
            ),
            _item(
                "protect-verification-codes",
                "Protect verification codes",
                "Never share SMS, bank, Alipay, or WeChat Pay verification codes.",
            ),
            _item(
                "avoid-unknown-agents",
                "Avoid sending money to unknown agents",
                "Do not send money to strangers offering payment setup.",
            ),
            _item(
                "flag-scams",
                "Flag scams",
                "Treat guaranteed setup or money-transfer requests as scam risk.",
            ),
        ],
        UserScenario.housing: [
            _item(
                "landlord-contract",
                "Verify landlord/contract terms",
                "Check name, address, rent, deposit, and refund terms.",
            ),
            _item(
                "registration-requirements",
                "Confirm registration requirements",
                "Ask how accommodation registration will be handled.",
                source_required=True,
            ),
            _item(
                "payment-contract-copies",
                "Keep copies of payments and contract",
                "Save receipts, chat records, and signed documents.",
            ),
            _item(
                "inspect-before-payment",
                "Inspect apartment before payment",
                "Check keys, utilities, safety, and condition.",
            ),
            _item(
                "avoid-cash-only",
                "Avoid undocumented cash-only arrangements",
                "Avoid cash-only deals without receipts or contract records.",
            ),
        ],
    }
    return list(templates.get(scenario, _fallback_items()))


def all_supported_scenarios() -> list[UserScenario]:
    return [
        UserScenario.tourism,
        UserScenario.kazakhstan_entry,
        UserScenario.study,
        UserScenario.work,
        UserScenario.medical,
        UserScenario.emergency,
        UserScenario.payments,
        UserScenario.housing,
        UserScenario.unclear,
    ]


def _fallback_items() -> list[ChecklistTemplateItem]:
    return [
        _item(
            "clarify-scenario",
            "Clarify scenario",
            "Describe the city, document status, and immediate goal.",
        ),
        _item(
            "gather-documents",
            "Gather documents",
            "Prepare passport, notices, contracts, or screenshots.",
        ),
        _item(
            "check-official-source",
            "Check official source",
            "Use official or curated guidance before community tips.",
            source_required=True,
        ),
        _item(
            "human-review-if-high-risk",
            "Ask for human review if high risk",
            "Escalate if the case is legal, work-status, medical, or emergency.",
            escalation_relevant=True,
        ),
    ]


def _item(
    item_id: str,
    title: str,
    description: str,
    source_required: bool = False,
    escalation_relevant: bool = False,
) -> ChecklistTemplateItem:
    return ChecklistTemplateItem(
        item_id=item_id,
        title=title,
        description=description,
        source_required=source_required,
        escalation_relevant=escalation_relevant,
    )
