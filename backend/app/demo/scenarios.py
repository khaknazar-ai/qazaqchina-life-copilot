from backend.app.demo.models import DemoScenario
from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario

_SCENARIOS = [
    DemoScenario(
        scenario_id="lost-passport-emergency",
        title="Lost passport emergency",
        description=(
            "Synthetic emergency case showing official-source priority, retrieval, "
            "checklist support, and escalation."
        ),
        user_message=(
            "\u042f \u043f\u043e\u0442\u0435\u0440\u044f\u043b passport "
            "\u0432 Beijing. \u041d\u0443\u0436\u043d\u0430 "
            "\u0441\u0440\u043e\u0447\u043d\u0430\u044f "
            "\u043f\u043e\u043c\u043e\u0449\u044c, \u043d\u0435 "
            "\u0437\u043d\u0430\u044e \u043a\u0443\u0434\u0430 "
            "\u0438\u0434\u0442\u0438."
        ),
        category=UserScenario.emergency,
        expected_features=[
            "emergency",
            "retrieval",
            "escalation",
            "case draft",
            "checklist",
            "official source priority",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.emergency,
    ),
    DemoScenario(
        scenario_id="study-registration",
        title="Study registration checklist",
        description=(
            "Synthetic student onboarding case for university registration and "
            "residence-permit document preparation."
        ),
        user_message=(
            "\u042f student \u0438\u0434\u0443 \u0432 university "
            "\u0432 Shanghai. \u041a\u0430\u043a\u0438\u0435 "
            "\u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b "
            "\u043d\u0443\u0436\u043d\u044b \u0434\u043b\u044f "
            "\u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u0438 "
            "\u0438 residence permit?"
        ),
        category=UserScenario.study,
        expected_features=[
            "study checklist",
            "official source priority",
            "multilingual",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.normal,
    ),
    DemoScenario(
        scenario_id="unsafe-work-status",
        title="Unsafe work-status advice",
        description=(
            "Synthetic work-status-sensitive case where the user asks about starting "
            "work before authorization is clear."
        ),
        user_message=(
            "\u041c\u043e\u0436\u043d\u043e \u043b\u0438 work on tourist visa "
            "\u0438 documents later? "
            "\u0420\u0430\u0431\u043e\u0442\u043e\u0434\u0430\u0442\u0435\u043b\u044c "
            "\u0433\u043e\u0432\u043e\u0440\u0438\u0442 "
            "\u043d\u0430\u0447\u0430\u0442\u044c \u0441\u0435\u0439\u0447\u0430\u0441."
        ),
        category=UserScenario.work,
        expected_features=[
            "work-status safety",
            "refusal/caution",
            "escalation",
            "source governance",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.work_status_sensitive,
    ),
    DemoScenario(
        scenario_id="payment-scam-warning",
        title="Payment scam warning",
        description=(
            "Synthetic payment-help scam case that exercises community moderation "
            "signals without approving content for retrieval."
        ),
        user_message=(
            "\u0412 Telegram agent \u043f\u0440\u043e\u0441\u0438\u0442 send money "
            "\u0437\u0430 guaranteed visa \u0438 Alipay/WeChat Pay help. "
            "\u042d\u0442\u043e \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e?"
        ),
        category=UserScenario.payments,
        expected_features=[
            "scam warning",
            "moderation",
            "payments checklist",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.medium,
    ),
    DemoScenario(
        scenario_id="chinese-notice-explanation",
        title="Chinese notice explanation",
        description=(
            "Synthetic notice explanation with key Chinese terms for passport, visa, "
            "police station, and registration."
        ),
        user_message=(
            "\u8bf7\u643a\u5e26\u62a4\u7167\u548c\u7b7e\u8bc1\u5230"
            "\u6d3e\u51fa\u6240\u529e\u7406\u767b\u8bb0\u3002"
        ),
        category=UserScenario.translation,
        expected_features=[
            "Chinese explanation",
            "key terms",
            "disclaimer",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.medium,
    ),
    DemoScenario(
        scenario_id="housing-registration",
        title="Housing registration",
        description=(
            "Synthetic rental-address case for accommodation registration and "
            "document preparation."
        ),
        user_message=(
            "\u042f \u0441\u043d\u0438\u043c\u0430\u044e apartment "
            "\u0432 Hangzhou. \u041a\u0430\u043a \u0441\u0434\u0435\u043b\u0430\u0442\u044c "
            "housing registration \u0438 \u043f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c "
            "\u0430\u0434\u0440\u0435\u0441?"
        ),
        category=UserScenario.housing,
        expected_features=[
            "housing checklist",
            "official source priority",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.normal,
    ),
    DemoScenario(
        scenario_id="hospital-registration",
        title="Hospital registration and payment",
        description=(
            "Synthetic medical-preparation case for hospital registration, documents, "
            "payment, and escalation if symptoms are severe."
        ),
        user_message=(
            "\u0423 \u043c\u0435\u043d\u044f fever \u0438 injury, "
            "\u043d\u0443\u0436\u043d\u043e hospital registration "
            "\u0432 China. \u041a\u0430\u043a\u0438\u0435 documents "
            "\u0438 payment \u043d\u0443\u0436\u043d\u043e "
            "\u0432\u0437\u044f\u0442\u044c?"
        ),
        category=UserScenario.medical,
        expected_features=[
            "medical caution",
            "emergency escalation if severe",
            "checklist",
            "Chinese terms",
            "official source priority",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.medical_sensitive,
    ),
    DemoScenario(
        scenario_id="police-station-registration",
        title="Police station residence registration",
        description=(
            "Synthetic apartment-rental case for residence registration at a local "
            "police station."
        ),
        user_message=(
            "\u042f rented apartment, landlord \u0433\u043e\u0432\u043e\u0440\u0438\u0442 "
            "\u043d\u0443\u0436\u043d\u043e police station registration "
            "\u0432 \u6d3e\u51fa\u6240. \u0427\u0442\u043e "
            "\u0434\u0435\u043b\u0430\u0442\u044c?"
        ),
        category=UserScenario.housing,
        expected_features=[
            "residence registration",
            "official source priority",
            "checklist",
            "Chinese terms",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.legal_sensitive,
    ),
    DemoScenario(
        scenario_id="visa-extension-warning",
        title="Visa extension and overstay warning",
        description=(
            "Synthetic legal-sensitive case where the user asks whether overstaying "
            "and fixing a visa later is acceptable."
        ),
        user_message=(
            "\u0423 \u043c\u0435\u043d\u044f visa expire soon. "
            "\u041c\u043e\u0436\u043d\u043e \u043b\u0438 overstay "
            "\u043d\u0430 \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e "
            "\u0434\u043d\u0435\u0439 \u0438 fix visa later "
            "\u0447\u0435\u0440\u0435\u0437 visa extension?"
        ),
        category=UserScenario.documents,
        expected_features=[
            "overstay warning",
            "official source priority",
            "escalation",
            "no unsafe advice",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.legal_sensitive,
    ),
    DemoScenario(
        scenario_id="bank-card-payment-setup",
        title="Bank card and payment setup",
        description=(
            "Synthetic payment setup case for bank card, WeChat Pay, and Alipay "
            "preparation."
        ),
        user_message=(
            "\u042f citizen of Kazakhstan \u0438 \u0445\u043e\u0447\u0443 "
            "open bank card, WeChat Pay \u0438 Alipay. "
            "\u041a\u0430\u043a\u0438\u0435 documents \u0438 caveats?"
        ),
        category=UserScenario.payments,
        expected_features=[
            "payments checklist",
            "document checklist",
            "practical caveat",
            "official/platform source priority",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.normal,
    ),
    DemoScenario(
        scenario_id="sim-card-registration",
        title="SIM card registration and scam risk",
        description=(
            "Synthetic telecom setup case for passport registration and avoiding "
            "agent scams."
        ),
        user_message=(
            "\u041d\u0443\u0436\u043d\u0430 Chinese SIM card. "
            "\u0411\u043e\u044e\u0441\u044c passport registration "
            "\u0438 scam \u043e\u0442 agent. \u041a\u0430\u043a "
            "\u0441\u0434\u0435\u043b\u0430\u0442\u044c "
            "\u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e?"
        ),
        category=UserScenario.payments,
        expected_features=[
            "registration checklist",
            "scam warning",
            "source priority",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.medium,
    ),
    DemoScenario(
        scenario_id="work-contract-risk",
        title="Work contract and permit risk",
        description=(
            "Synthetic work-status case where an employer asks the user to start "
            "before contract and permit status is clear."
        ),
        user_message=(
            "Employer \u043f\u0440\u043e\u0441\u0438\u0442 start work "
            "before contract \u0438 permit \u0433\u043e\u0442\u043e\u0432\u044b. "
            "\u041c\u043e\u0436\u043d\u043e \u043d\u0430\u0447\u0430\u0442\u044c "
            "\u0441\u0435\u0439\u0447\u0430\u0441?"
        ),
        category=UserScenario.work,
        expected_features=[
            "work-status safety",
            "caution/refusal",
            "escalation",
            "no illegal work advice",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.work_status_sensitive,
    ),
    DemoScenario(
        scenario_id="university-dormitory-issue",
        title="University dormitory registration delay",
        description=(
            "Synthetic mixed-language student case for delayed dormitory registration "
            "and closed university office."
        ),
        user_message=(
            "\u042f student, university dormitory registration delayed, "
            "office closed. \u041d\u0435 \u0431\u0456\u043b\u0435\u043c "
            "\u0447\u0442\u043e \u0434\u0435\u043b\u0430\u0442\u044c."
        ),
        category=UserScenario.study,
        expected_features=[
            "study checklist",
            "escalation path",
            "multilingual handling",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.medium,
    ),
    DemoScenario(
        scenario_id="lost-phone-and-documents",
        title="Lost phone and document copies",
        description=(
            "Synthetic emergency case for phone loss, document-copy loss, and "
            "payment/account safety."
        ),
        user_message=(
            "\u042f lost phone, passport copies \u0438 bank access. "
            "\u041d\u0443\u0436\u043d\u044b emergency steps \u0438 "
            "payment safety."
        ),
        category=UserScenario.emergency,
        expected_features=[
            "emergency checklist",
            "escalation",
            "account/payment safety",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.emergency,
    ),
    DemoScenario(
        scenario_id="consulate-appointment-flow",
        title="Consulate appointment flow",
        description=(
            "Synthetic consular-support case for contacting Kazakhstan consulate "
            "after document loss."
        ),
        user_message=(
            "\u042f lost passport \u0438 \u043d\u0443\u0436\u0435\u043d "
            "Kazakhstan consulate appointment flow. \u041a\u0443\u0434\u0430 "
            "\u043f\u0438\u0441\u0430\u0442\u044c \u0438 \u0447\u0442\u043e "
            "\u0433\u043e\u0442\u043e\u0432\u0438\u0442\u044c?"
        ),
        category=UserScenario.emergency,
        expected_features=[
            "consular escalation",
            "official source priority",
            "checklist",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.emergency,
    ),
    DemoScenario(
        scenario_id="community-misinformation-conflict",
        title="Community misinformation conflict",
        description=(
            "Synthetic source-governance case where community advice conflicts with "
            "work-status safety rules."
        ),
        user_message=(
            "Community post \u0433\u043e\u0432\u043e\u0440\u0438\u0442, "
            "\u0447\u0442\u043e work on tourist visa \u043d\u043e\u0440\u043c, "
            "\u0435\u0441\u043b\u0438 paid cash. \u042d\u0442\u043e true?"
        ),
        category=UserScenario.work,
        expected_features=[
            "conflict handling",
            "official sources outrank community",
            "unsafe advice rejection",
        ],
        preferred_language=LanguageCode.ru,
        risk_hint=RiskLevel.work_status_sensitive,
    ),
]


def list_demo_scenarios() -> list[DemoScenario]:
    return list(_SCENARIOS)


def get_demo_scenario(scenario_id: str) -> DemoScenario:
    for scenario in _SCENARIOS:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise ValueError("Unknown demo scenario.")


def demo_scenario_ids() -> list[str]:
    return [scenario.scenario_id for scenario in _SCENARIOS]
