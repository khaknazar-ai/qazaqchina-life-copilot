"""Reviewed deterministic UI copy. Source quotations are never machine translated."""

LANGUAGES = {"en": 0, "ru": 1, "kk": 2, "zh": 3}

# Entries keep English as the offline/default API language when none is supplied.
COPY: dict[str, tuple[str, str, str, str]] = {
    "work_steps": (
        "Keep written offers, contracts, permits, notices and relevant messages so a qualified "
        "reviewer can assess the case. Ask the employer to explain the proposed work status "
        "in writing.",
        "Сохраните письменное предложение, договор, разрешения, уведомления и переписку для "
        "специалиста. Попросите работодателя письменно пояснить предлагаемый статус работы.",
        "Маманға көрсету үшін жазбаша ұсынысты, шартты, рұқсаттарды, хабарламалар мен хаттарды "
        "сақтаңыз. Жұмыс берушіден ұсынылған еңбек мәртебесін жазбаша түсіндіруді сұраңыз.",
        "保存书面录用条件、合同、许可、通知和相关聊天记录，供专业人士审核；请雇主书面说明拟议的工作资格。",
    ),
    "medical_steps": (
        "If available, prepare identification, insurance details, medication and allergy "
        "information, and a payment method. Confirm appointment and billing steps with "
        "hospital staff.",
        "Если возможно, подготовьте удостоверение личности, страховку, сведения о лекарствах "
        "и аллергии, способ оплаты. Запись и расчёт уточните у сотрудников больницы.",
        "Мүмкін болса, жеке куәлікті, сақтандыруды, дәрілер мен аллергия туралы мәліметті және "
        "төлем тәсілін дайындаңыз. Қабылдау мен есеп айырысуды аурухана қызметкерлерінен "
        "нақтылаңыз.",
        "如有可能，准备身份证件、保险资料、用药和过敏信息以及支付方式，并向医院工作人员核实挂号和结算流程。",
    ),
    "title": (
        "Grounded Answer",
        "Ответ с опорой на источники",
        "Дереккөздерге негізделген жауап",
        "有来源支持的回答",
    ),
    "scenario": (
        "Scenario",
        "Сценарий",
        "Жағдай",
        "场景",
    ),
    "risk": (
        "Risk level",
        "Уровень риска",
        "Тәуекел деңгейі",
        "风险等级",
    ),
    "language": (
        "Language",
        "Язык",
        "Тіл",
        "语言",
    ),
    "short": (
        "Direct short answer",
        "Краткий ответ",
        "Қысқаша жауап",
        "简短回答",
    ),
    "facts": (
        "What is grounded in trusted sources",
        "Официальные и проверенные источники",
        "Ресми және тексерілген дереккөздер",
        "官方及经审核的来源",
    ),
    "steps": (
        "Recommended next steps",
        "Рекомендуемые следующие шаги",
        "Ұсынылатын келесі қадамдар",
        "建议的下一步",
    ),
    "checklist": (
        "Checklist",
        "Что подготовить",
        "Не дайындау керек",
        "准备清单",
    ),
    "human": (
        "When to escalate / contact official help",
        "Когда обратиться к человеку или официальной службе",
        "Адамға немесе ресми қызметке қашан жүгіну керек",
        "何时联系人工或官方机构",
    ),
    "uncertainty": (
        "Uncertainty / what needs verification",
        "Что требует уточнения",
        "Нені нақтылау керек",
        "需要核实的信息",
    ),
    "sources": (
        "Source notes",
        "Сведения об источниках",
        "Дереккөздер туралы",
        "来源信息",
    ),
    "community": (
        "Community experience",
        "Опыт сообщества",
        "Қауымдастық тәжірибесі",
        "社区经验",
    ),
    "warnings": (
        "Warnings",
        "Предупреждения",
        "Ескертулер",
        "提醒",
    ),
    "quote": (
        "Original source excerpt",
        "Фрагмент источника на языке оригинала",
        "Дереккөзден түпнұсқа тіліндегі үзінді",
        "来源原文摘录",
    ),
    "no_facts": (
        "No trusted source-grounded facts are available for this request.",
        "Для этого запроса нет подтверждённых сведений из проверенных источников.",
        "Бұл сұрауға тексерілген дереккөздермен расталған мәлімет жоқ.",
        "此请求尚无可信来源支持的信息。",
    ),
    "no_steps": (
        "No deterministic next steps were generated.",
        "Следующие шаги требуют уточнения ситуации.",
        "Келесі қадамдар үшін жағдайды нақтылау керек.",
        "需要先明确情况才能建议下一步。",
    ),
    "no_checklist": (
        "No checklist was generated for this request.",
        "Список подготовки для этого запроса пока не сформирован.",
        "Бұл сұрауға дайындық тізімі әзірге жасалмаған.",
        "尚未生成此请求的准备清单。",
    ),
    "routine_human": (
        "Contact official support if the issue remains unresolved.",
        "Обратитесь в официальную поддержку, если вопрос не решён.",
        "Мәселе шешілмесе, ресми қолдау қызметіне жүгініңіз.",
        "如果问题仍未解决，请联系官方支持。",
    ),
    "verify": (
        "Confirm current requirements with an official source before acting.",
        "Перед действиями уточните актуальные требования в официальном источнике.",
        "Әрекет етпес бұрын қолданыстағы талаптарды ресми дереккөзден нақтылаңыз.",
        "行动前请通过官方来源核实最新要求。",
    ),
    "no_sources": (
        ("Source coverage is limited: no trusted registry source was selected for this answer."),
        (
            "Для ответа не найдено подходящих проверенных источников; конкретные "
            "требования нужно уточнить."
        ),
        "Жауапқа сай тексерілген дереккөз табылмады; нақты талаптарды анықтау керек.",
        "未找到适合此回答的可信来源；具体要求仍需核实。",
    ),
    "no_grounding": (
        (
            "I do not have trusted source coverage for this request, so I can only give "
            "conservative safety-oriented next steps and recommend official verification."
        ),
        (
            "У меня нет проверенных источников для этого запроса. Ниже — осторожные общие"
            " шаги; требования уточните в официальной службе."
        ),
        (
            "Бұл сұрауға тексерілген дереккөз жоқ. Төменде сақтыққа негізделген жалпы "
            "қадамдар берілген; талаптарды ресми қызметтен нақтылаңыз."
        ),
        "此请求缺少可信来源。以下仅为保守的一般步骤；具体要求请向官方机构核实。",
    ),
    "disclaimer": (
        (
            "This is not legal, medical, or official advice; confirm sensitive decisions "
            "with official or qualified human support."
        ),
        (
            "Приложение не является официальным органом, юристом или врачом. Важные "
            "решения подтвердите у профильного специалиста или официальной службы."
        ),
        (
            "Қосымша ресми орган, заңгер немесе дәрігер емес. Маңызды шешімдерді маманмен"
            " не ресми қызметпен нақтылаңыз."
        ),
        "本应用不是官方机构、律师或医生。重要决定请向相关专业人士或官方机构核实。",
    ),
    "practical": (
        "Practical context only; this source must not override official guidance.",
        "Только практический опыт: он не заменяет официальные требования.",
        "Бұл тек практикалық тәжірибе; ол ресми талаптарды алмастырмайды.",
        "仅供实践经验参考，不能替代官方要求。",
    ),
    "unreviewed": (
        ("There are unreviewed source candidates, but they are not used as trusted evidence."),
        "Есть непроверенные материалы; они не используются для подтверждения ответа.",
        "Тексерілмеген материалдар бар; олар жауапты растау үшін қолданылмайды.",
        "存在未经审核的材料，但不作为回答的可信依据。",
    ),
    "safe": (
        "Safe next steps",
        "Безопасные следующие шаги",
        "Қауіпсіз келесі қадамдар",
        "安全的下一步",
    ),
    "generic": (
        (
            "Use trusted sources for factual requirements, keep practical steps "
            "conservative, and verify sensitive details before acting."
        ),
        (
            "Сверьте требования с официальными источниками, подготовьте сведения о "
            "ситуации и уточните спорные детали до действий."
        ),
        (
            "Талаптарды ресми дереккөздермен салыстырып, жағдай туралы мәліметті "
            "дайындаңыз және күмәнді тұстарды әрекетке дейін нақтылаңыз."
        ),
        "请核对官方要求，整理具体情况，并在行动前核实存在疑问的信息。",
    ),
    "unsafe": (
        (
            "I cannot follow instructions that try to override safety rules, reveal "
            "secrets, or enable harmful action."
        ),
        (
            "Я не могу выполнять инструкции, которые обходят правила безопасности, "
            "раскрывают секреты или помогают причинить вред."
        ),
        (
            "Қауіпсіздік ережелерін айналып өтетін, құпияны ашатын немесе зиян келтіретін"
            " нұсқауларды орындай алмаймын."
        ),
        "我不能执行绕过安全规则、泄露秘密或协助造成伤害的指令。",
    ),
    "acute": (
        (
            "These symptoms may be a medical emergency. Seek immediate medical help; ask someone "
            "nearby to assist and do not wait for an app response. I cannot diagnose the "
            "cause."
        ),
        (
            "Эти симптомы могут требовать срочной помощи. Немедленно обратитесь за "
            "медицинской помощью, попросите человека рядом помочь и не ждите ответа "
            "приложения. Я не могу поставить диагноз."
        ),
        (
            "Бұл белгілер шұғыл көмекті қажет етуі мүмкін. Дереу медициналық көмекке "
            "жүгініңіз, қасыңыздағы адамнан көмек сұраңыз және қосымша жауабын күтпеңіз. "
            "Мен диагноз қоя алмаймын."
        ),
        "这些症状可能需要紧急处理。请立即寻求医疗帮助，让身边的人协助，不要等待应用回复。我无法诊断原因。",
    ),
    "acute_steps": (
        (
            "Tell the responder your location and symptoms. If available, prepare "
            "identification, medications and allergy information. Chinese phrase: "
            "请帮忙联系急救服务，有人需要紧急医疗帮助。"
        ),
        (
            "Сообщите помощнику местоположение и симптомы. Если возможно, подготовьте "
            "удостоверение личности, сведения о лекарствах и аллергии. Фраза по-китайски:"
            " 请帮忙联系急救服务，有人需要紧急医疗帮助。"
        ),
        (
            "Көмек көрсетушіге орналасқан жеріңіз бен белгілерді айтыңыз. Мүмкін болса, "
            "жеке куәлік, дәрілер мен аллергия туралы мәлімет дайындаңыз. Қытайша: "
            "请帮忙联系急救服务，有人需要紧急医疗帮助。"
        ),
        "向救援人员说明位置和症状。如方便，准备身份证件、用药及过敏信息。求助用语：请帮忙联系急救服务，有人需要紧急医疗帮助。",
    ),
    "emergency": (
        (
            "Move to safety if possible and contact local emergency help immediately. "
            "This app is not emergency dispatch."
        ),
        (
            "Если возможно, перейдите в безопасное место и немедленно обратитесь в "
            "местную экстренную службу. Приложение не является диспетчерской экстренной "
            "помощи."
        ),
        (
            "Мүмкін болса, қауіпсіз жерге барып, жергілікті шұғыл көмек қызметіне дереу "
            "хабарласыңыз. Бұл қосымша шұғыл көмек диспетчері емес."
        ),
        "如有可能，请前往安全地点并立即联系当地紧急救援机构。本应用不是紧急调度服务。",
    ),
    "loss": (
        (
            "Treat this as urgent: keep yourself safe, preserve identity and loss "
            "details, and verify the current passport/document-loss process with official"
            " or consular help."
        ),
        (
            "Обеспечьте свою безопасность, сохраните копии документов и сведения об "
            "утрате. Уточните актуальный порядок действий в консульстве или официальной "
            "службе."
        ),
        (
            "Қауіпсіздігіңізді қамтамасыз етіп, құжат көшірмелері мен жоғалу мән-жайларын"
            " сақтаңыз. Әрекет тәртібін консулдықтан не ресми қызметтен нақтылаңыз."
        ),
        "请确保自身安全，保留证件副本和遗失详情，并向领事机构或官方部门核实当前处理流程。",
    ),
    "loss_steps": (
        (
            "Keep identity copies, loss details and report numbers. Contact the relevant "
            "embassy or consulate for current instructions. Chinese phrase: "
            "我的护照丢了，请问我该联系谁？"
        ),
        (
            "Подготовьте копии документов, место и время утраты, номера обращений. "
            "Свяжитесь с посольством или консульством. Фраза по-китайски: "
            "我的护照丢了，请问我该联系谁？"
        ),
        (
            "Құжат көшірмесін, жоғалған орын мен уақытты, өтініш нөмірлерін дайындаңыз. "
            "Елшілікке не консулдыққа хабарласыңыз. Қытайша: 我的护照丢了，请问我该联系谁？"
        ),
        "准备证件副本、遗失地点和时间、报案或受理编号，并联系相关使领馆。求助用语：我的护照丢了，请问我该联系谁？",
    ),
    "work": (
        (
            "Do not rely only on an employer's claim; verify lawful work status, "
            "contract, and permit requirements with official or qualified help before "
            "starting work. Confirm official requirements before acting."
        ),
        (
            "Не полагайтесь только на обещание работодателя. До начала работы уточните "
            "право на труд, договор и разрешительные требования в официальной службе или "
            "у профильного специалиста."
        ),
        (
            "Жұмыс берушінің сөзіне ғана сенбеңіз. Жұмысты бастамас бұрын еңбек ету "
            "құқығын, шарт пен рұқсат талаптарын ресми қызметтен не маманнан нақтылаңыз."
        ),
        "不要仅依赖雇主承诺。开始工作前，请向官方部门或专业人士核实工作资格、合同及许可要求。",
    ),
    "medical": (
        (
            "For severe or worsening symptoms, seek urgent medical care; otherwise verify"
            " hospital, insurance, and payment steps with official hospital staff."
        ),
        (
            "При серьёзных или усиливающихся симптомах нужна срочная медицинская помощь. "
            "В остальных случаях уточните запись, страховку и оплату у сотрудников "
            "больницы."
        ),
        (
            "Ауыр не күшейіп жатқан белгілер болса, шұғыл медициналық көмекке жүгініңіз. "
            "Басқа жағдайда қабылдау, сақтандыру және төлемді аурухана қызметкерлерінен "
            "нақтылаңыз."
        ),
        "症状严重或加重时请及时就医；其他情况请向医院工作人员核实挂号、保险和支付流程。",
    ),
    "study": (
        (
            "Use the university international office or current official notice as the "
            "deciding source for registration, dormitory, and document steps."
        ),
        (
            "Порядок зачисления, общежития и документов уточняйте в международном отделе "
            "университета и по актуальным официальным объявлениям."
        ),
        (
            "Қабылдау, жатақхана және құжат тәртібін университеттің халықаралық бөлімінен"
            " және ресми хабарландырулардан нақтылаңыз."
        ),
        "有关报到、宿舍和材料要求，请以学校国际事务办公室及最新官方通知为准。",
    ),
    "documents": (
        (
            "Confirm the document service and current requirements with the issuing "
            "authority or consulate; routine renewal is not automatically an emergency."
        ),
        (
            "Уточните нужную услугу и актуальные требования в органе выдачи или "
            "консульстве. Плановая замена документа сама по себе не является экстренной "
            "ситуацией."
        ),
        (
            "Қажетті қызмет пен қолданыстағы талаптарды құжат беретін органнан не "
            "консулдықтан нақтылаңыз. Жоспарлы жаңарту өздігінен төтенше жағдай емес."
        ),
        "请向签发机构或领事机构核实所需服务和当前要求；常规换发本身不属于紧急情况。",
    ),
    "setup": (
        (
            "Use the official payment app to review account setup and card-linking "
            "requirements. Follow its current verification instructions; never share your"
            " security codes."
        ),
        (
            "В официальном платёжном приложении проверьте настройку аккаунта и привязку "
            "карты. Следуйте актуальным инструкциям проверки личности и никому не "
            "сообщайте защитные коды."
        ),
        (
            "Ресми төлем қосымшасынан аккаунт ашу мен картаны байланыстыру талаптарын "
            "қараңыз. Жеке басты тексеру нұсқауларын орындап, қауіпсіздік кодтарын "
            "ешкімге бермеңіз."
        ),
        "请在官方支付应用中查看账户设置和银行卡绑定要求，按当前身份验证提示操作，勿向他人透露安全验证码。",
    ),
    "failure": (
        (
            "Check the exact error in the official payment app and contact platform or "
            "bank support. Avoid repeated charges until the transaction status is clear."
        ),
        (
            "Проверьте точный текст ошибки в официальном приложении и обратитесь в "
            "поддержку платформы или банка. До выяснения статуса избегайте повторного "
            "списания."
        ),
        (
            "Ресми қосымшадағы қатені тексеріп, платформа не банк қолдауына жүгініңіз. "
            "Мәртебе анықталғанша төлемді қайталамаңыз."
        ),
        "请查看官方支付应用中的具体错误，并联系平台或银行客服；在交易状态明确前避免重复扣款。",
    ),
    "refund": (
        (
            "Find the transaction in the official app and review the merchant/platform "
            "refund process. Keep receipts and confirm current eligibility and timing "
            "with support."
        ),
        (
            "Найдите операцию в официальном приложении и порядок возврата у продавца или "
            "платформы. Сохраните чек; условия и сроки уточните в поддержке."
        ),
        (
            "Ресми қосымшадан операцияны және сатушының не платформаның қайтару тәртібін "
            "қараңыз. Түбіртекті сақтап, шарттар мен мерзімді қолдау қызметінен "
            "нақтылаңыз."
        ),
        "请在官方应用中找到交易并查看商家或平台退款流程，保留凭证，向客服核实适用条件及时间。",
    ),
    "scam": (
        (
            "Protect your accounts first: do not share codes or send more money, preserve"
            " evidence, and use official platform, bank, or local official channels."
        ),
        (
            "Не сообщайте коды и не отправляйте дополнительные деньги. Сохраните "
            "переписку и сведения о платеже; обратитесь в официальную поддержку "
            "платформы, банк или местные органы."
        ),
        (
            "Кодтарды бермеңіз және қосымша ақша жібермеңіз. Хаттар мен төлем деректерін "
            "сақтап, платформаның ресми қолдауына, банкке не жергілікті органдарға "
            "жүгініңіз."
        ),
        "不要透露验证码或继续转账。保存聊天和付款证据，通过官方渠道联系平台、银行或当地有关部门。",
    ),
    "general_payment": (
        (
            "Clarify whether you need account setup, help with a failed payment, a "
            "refund, or help with suspected fraud; use the official app or bank for "
            "current instructions."
        ),
        (
            "Уточните, нужна ли настройка аккаунта, помощь с ошибкой оплаты, возврат или "
            "разбор подозрительного платежа. Актуальные инструкции получите в официальном"
            " приложении или банке."
        ),
        (
            "Аккаунт баптау, төлем қатесі, қайтару не күмәнді төлем бойынша көмек керек "
            "пе — нақтылаңыз. Нұсқауларды ресми қосымшадан не банктен алыңыз."
        ),
        "请说明需要账户设置、支付失败、退款还是疑似诈骗方面的帮助，并通过官方应用或银行核实操作。",
    ),
}


def copy(key: str, language: str | None) -> str:
    return COPY[key][LANGUAGES.get(str(language), 0)]


def localized_scenario(value: str, language: str | None) -> str:
    labels = {
        "tourism": ("Tourism", "Туризм", "Туризм", "旅游"),
        "kazakhstan_entry": (
            "Visit Kazakhstan",
            "Поездка в Казахстан",
            "Қазақстанға сапар",
            "赴哈萨克斯坦",
        ),
        "study": ("Study", "Учёба", "Оқу", "学习"),
        "work": ("Work", "Работа", "Жұмыс", "工作"),
        "business": ("Business", "Бизнес", "Бизнес", "商务"),
        "medical": ("Medical", "Медицина", "Медицина", "医疗"),
        "emergency": ("Emergency", "Экстренная ситуация", "Төтенше жағдай", "紧急情况"),
        "documents": ("Documents", "Документы", "Құжаттар", "证件"),
        "housing": ("Housing", "Жильё", "Тұрғын үй", "住房"),
        "payments": ("Payments", "Платежи", "Төлемдер", "支付"),
        "transport": ("Transport", "Транспорт", "Көлік", "交通"),
        "translation": ("Translation", "Перевод", "Аударма", "翻译"),
        "community_experience": (
            "Community experience",
            "Опыт сообщества",
            "Қауымдастық тәжірибесі",
            "社区经验",
        ),
        "unclear": ("Needs clarification", "Нужно уточнение", "Нақтылау қажет", "需要澄清"),
        "normal": ("Normal", "Обычный", "Қалыпты", "一般"),
        "medium": ("Medium", "Средний", "Орташа", "中等"),
        "legal_sensitive": (
            "Legal sensitive",
            "Юридически чувствительный",
            "Құқықтық тәуекел",
            "涉及法律",
        ),
        "work_status_sensitive": (
            "Work status sensitive",
            "Статус трудоустройства",
            "Еңбек мәртебесі",
            "涉及工作资格",
        ),
        "medical_sensitive": (
            "Medical sensitive",
            "Медицинский риск",
            "Медициналық тәуекел",
            "涉及医疗",
        ),
        "unsafe": ("Unsafe", "Небезопасный запрос", "Қауіпті сұрау", "不安全请求"),
        "prompt_injection": (
            "Unsafe instructions",
            "Подмена инструкций",
            "Нұсқауларды бұрмалау",
            "指令注入",
        ),
    }
    if str(language) not in {"ru", "kk", "zh"}:
        return value
    return labels.get(value, (value,) * 4)[LANGUAGES[str(language)]]
