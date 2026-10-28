"""User-facing policy messages; diagnostic identifiers stay language independent."""

from backend.app.answer_quality.localization import copy
from backend.app.safety_policy.rules import (
    COMMUNITY_CONFLICT_WARNING,
    EMERGENCY_WARNING,
    MEDICAL_WARNING,
    OFFICIAL_SOURCE_WARNING,
    SCAM_WARNING,
    UNCERTAINTY_WARNING,
)

COPY_KEYS = {
    EMERGENCY_WARNING: "emergency",
    SCAM_WARNING: "scam",
    UNCERTAINTY_WARNING: "no_sources",
    "Unreviewed sources cannot be used as trusted evidence.": "unreviewed",
    "Verify the requirement with an official or curated source.": "verify",
    "Prefer official/curated guidance over community experience.": "practical",
    "Recommend official verification when sources are missing or uncertain.": "verify",
    (
        "For urgent symptoms, contact qualified medical professionals or official medical services."
    ): "medical",
    (
        "Contact local emergency services or official authorities if immediate danger exists."
    ): "emergency",
}

DISPLAY = {
    OFFICIAL_SOURCE_WARNING: (
        (
            "Для утверждений о праве, визе, работе, полиции, медицине или экстренных "
            "действиях нужны официальные или проверенные редакцией источники."
        ),
        (
            "Құқық, виза, жұмыс, полиция, медицина немесе шұғыл әрекеттер туралы "
            "тұжырымдарға ресми не редакция тексерген дереккөздер қажет."
        ),
        ("有关法律、签证、工作、警方、医疗或紧急情况的确定性信息，必须有官方或经审核的来源支持。"),
    ),
    COMMUNITY_CONFLICT_WARNING: (
        (
            "Официальные и проверенные редакцией источники важнее сообщений "
            "сообщества. Непроверенные сообщения не являются авторитетным основанием."
        ),
        (
            "Ресми және редакция тексерген дереккөздер қауымдастық пікірінен жоғары "
            "тұрады. Тексерілмеген пікірлер беделді негіз емес."
        ),
        "官方及经审核的来源优先于社区说法；未经核实的社区信息不具有权威性。",
    ),
    MEDICAL_WARNING: (
        (
            "Приложение не ставит диагноз. При серьёзных симптомах нужна срочная "
            "помощь врача или другого профильного медицинского специалиста."
        ),
        (
            "Қосымша диагноз қоймайды. Ауыр белгілер болса, дәрігердің не тиісті "
            "медицина маманының шұғыл көмегі қажет."
        ),
        ("本应用不提供诊断。症状可能严重时，应立即寻求医生或相关医疗专业人员的帮助。"),
    ),
    (
        "The app cannot replace police, ambulance, consular, hospital, or other "
        "official emergency response."
    ): (
        (
            "Приложение не заменяет полицию, скорую помощь, консульство, больницу и "
            "другие официальные экстренные службы."
        ),
        (
            "Қосымша полицияны, жедел жәрдемді, консулдықты, аурухананы және басқа "
            "ресми шұғыл қызметтерді алмастырмайды."
        ),
        "本应用不能替代警方、救护、领事、医院或其他官方紧急服务。",
    ),
    ("Use the human support queue only as a follow-up record, not emergency dispatch."): (
        ("Очередь поддержки служит для последующего разбора; она не вызывает экстренную помощь."),
        "Қолдау кезегі кейінгі қарауға арналған; ол шұғыл көмек шақырмайды.",
        "人工支持队列仅用于后续跟进记录，不会调度紧急救援。",
    ),
    "Preserve key facts and documents if it is safe to do so.": (
        "Сохраните важные сведения и документы, если это безопасно.",
        "Қауіпсіз болса, маңызды мәліметтер мен құжаттарды сақтаңыз.",
        "在安全的情况下保留关键事实和文件。",
    ),
    (
        "Create an escalation request when status, deadline, employment, police, "
        "or document risk is high."
    ): (
        (
            "Если высок риск, связанный со статусом, сроком, работой, полицией или "
            "документами, создайте обращение к специалисту."
        ),
        (
            "Мәртебе, мерзім, жұмыс, полиция не құжат бойынша тәуекел жоғары болса, "
            "маманға өтініш жасаңыз."
        ),
        "涉及身份、期限、就业、警方或证件的高风险情况，请提交人工协助请求。",
    ),
    ("Give safe administrative steps only, such as preparing documents and seeking care."): (
        ("Ограничьтесь безопасной подготовкой документов и обращением за медицинской помощью."),
        "Құжаттарды қауіпсіз дайындап, медициналық көмекке жүгініңіз.",
        "仅采取安全的事务性步骤，例如准备资料和寻求医疗服务。",
    ),
    ("Use human escalation for language, document, or navigation help, not diagnosis."): (
        (
            "Попросите человека помочь с языком, документами или маршрутом "
            "обращения; диагноз ставит медицинский специалист."
        ),
        (
            "Тіл, құжат не қайда жүгіну бойынша адамнан көмек сұраңыз; диагнозды "
            "медицина маманы қояды."
        ),
        "人工协助可用于语言、材料或就医指引；诊断应由医疗专业人员提供。",
    ),
    "Do not send more money while the request is unclear.": (
        "Не отправляйте дополнительные деньги, пока требование не проверено.",
        "Талап тексерілмейінше қосымша ақша жібермеңіз.",
        "在要求尚未核实前，不要继续转账。",
    ),
    ("Preserve screenshots, receipts, usernames, phone numbers, and transaction records."): (
        (
            "Сохраните скриншоты, чеки, имена аккаунтов, номера телефонов и сведения "
            "об операциях; не публикуйте личные данные."
        ),
        (
            "Скриншоттарды, түбіртектерді, аккаунт аттарын, телефон нөмірлерін және "
            "операцияларды сақтаңыз; жеке деректерді жарияламаңыз."
        ),
        "保存截图、收据、账户名称、电话号码和交易记录；不要公开个人信息。",
    ),
    ("Ask for human review when money, landlord, employer, or account access risk is involved."): (
        (
            "Попросите специалиста проверить ситуацию, если есть риск для денег, "
            "аренды, работы или доступа к аккаунту."
        ),
        ("Ақша, жалға алу, жұмыс не аккаунтқа кіру тәуекелі болса, маманнан тексеруді сұраңыз."),
        "如涉及资金、房东、雇主或账户访问风险，请请求人工审核。",
    ),
    "Compare the claim against official or curated sources.": (
        ("Сверьте утверждение с официальными или проверенными редакцией источниками."),
        "Тұжырымды ресми не редакция тексерген дереккөздермен салыстырыңыз.",
        "请将该说法与官方或经审核的来源进行比对。",
    ),
    (
        "Warn the user when community information is unverified or conflicts "
        "with higher-trust sources."
    ): (
        (
            "Не полагайтесь на сообщения сообщества, которые не проверены или "
            "противоречат более надёжным источникам."
        ),
        ("Тексерілмеген не сенімдірек дереккөздерге қайшы қауымдастық пікіріне сүйенбеңіз."),
        "不要依赖未经核实或与更可信来源冲突的社区信息。",
    ),
    "Escalate source conflicts for human review.": (
        "Передайте противоречия между источниками человеку для проверки.",
        "Дереккөздер арасындағы қайшылықтарды адамға тексеруге жіберіңіз.",
        "请将来源之间的冲突交由人工审核。",
    ),
    "Answer only within the available trusted evidence.": (
        ("Используйте только сведения, подтверждённые доступными проверенными источниками."),
        ("Қолжетімді тексерілген дереккөздер растайтын мәліметті ғана пайдаланыңыз."),
        "请仅依据现有可信证据中的信息。",
    ),
}


def localize_messages(messages: list[str], language: str) -> list[str]:
    index = {"ru": 0, "kk": 1, "zh": 2}.get(language)
    if index is None:
        return list(messages)
    localized = []
    for message in messages:
        if message in COPY_KEYS:
            localized.append(copy(COPY_KEYS[message], language))
        elif message in DISPLAY:
            localized.append(DISPLAY[message][index])
        else:
            # Preserve a new safety requirement until its reviewed translation exists.
            localized.append(message)
    return localized
