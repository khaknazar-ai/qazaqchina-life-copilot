"""Preparation plans, not invented jurisdictional requirements or published evidence."""

from backend.app.domain.enums import LanguageCode, UserScenario

LANGUAGES = (LanguageCode.ru, LanguageCode.kk, LanguageCode.zh, LanguageCode.en)
STEPS = {
    "travel_plan": (
        "Уточните маршрут, даты и условия поездки",
        "Бағытты, күндерді және сапар шарттарын нақтылаңыз",
        "确认行程、日期和出行条件",
        "Confirm the itinerary, dates and travel conditions",
    ),
    "arrival": (
        "Подготовьте сведения о проживании и прибытии",
        "Тұру және келу туралы мәліметтерді дайындаңыз",
        "准备住宿和抵达信息",
        "Prepare accommodation and arrival details",
    ),
    "kazakhstan_visa": (
        "Проверьте визовый режим по стране гражданства и типу паспорта",
        "Азаматтық елі мен паспорт түріне сай визалық режимді тексеріңіз",
        "按国籍和护照类型查询签证制度",
        "Check the visa regime for your citizenship and passport type",
    ),
    "kazakhstan_purpose": (
        "Сверьте цель, даты и срок поездки с официальными условиями въезда",
        "Сапар мақсатын, күндерін және мерзімін ресми кіру талаптарымен салыстырыңыз",
        "按官方入境条件核对旅行目的、日期和停留时间",
        "Check purpose, dates and stay length against official entry conditions",
    ),
    "kazakhstan_evisa": (
        "Если рассматриваете e-Visa, проверьте право на неё и приглашение по официальным правилам",
        "e-Visa қарастырсаңыз, оған жарамдылық пен шақыруды ресми талаптардан тексеріңіз",
        "如考虑电子签证，请按官方要求确认资格和邀请函",
        "If considering an e-Visa, check eligibility and invitation requirements officially",
    ),
    "kazakhstan_arrival": (
        "До поездки уточните у принимающей стороны правила прибытия и проживания",
        "Сапарға дейін қабылдаушы тараптан келу және тұру талаптарын нақтылаңыз",
        "出行前向接待方核实抵达和住宿要求",
        "Before travel, confirm arrival and accommodation steps with your host",
    ),
    "enrollment": (
        "Уточните порядок и сроки регистрации в университете",
        "Университеттегі тіркеу тәртібі мен мерзімін нақтылаңыз",
        "向学校确认报到流程和时间",
        "Ask the university about registration steps and dates",
    ),
    "student_documents": (
        "Сверьте документы для поступления и проживания с требованиями университета",
        "Оқу мен тұру құжаттарын университет талаптарымен салыстырыңыз",
        "向学校核对入学及住宿材料",
        "Check admission and accommodation documents with the university",
    ),
    "employer": (
        "Проверьте сведения о работодателе и условия предложения",
        "Жұмыс беруші туралы мәлімет пен ұсыныс шарттарын тексеріңіз",
        "核实雇主信息和聘用条件",
        "Verify employer details and the terms of the offer",
    ),
    "work_status": (
        "Уточните разрешённый статус работы до принятия решения",
        "Шешім қабылдамас бұрын жұмыс істеу мәртебесін нақтылаңыз",
        "决定前向官方确认工作资格",
        "Confirm work authorization with the official service before deciding",
    ),
    "meeting": (
        "Подтвердите встречу, организатора и деловую цель",
        "Кездесуді, ұйымдастырушыны және іскерлік мақсатты растаңыз",
        "确认会议、组织方和商务目的",
        "Confirm the meeting, organizer and business purpose",
    ),
    "business_documents": (
        "Подготовьте вопросы по договору, оплате и документам",
        "Шарт, төлем және құжаттар бойынша сұрақтарды дайындаңыз",
        "准备合同、付款和文件方面的问题",
        "Prepare questions about the contract, payment and documents",
    ),
    "hospital": (
        "Уточните запись и регистрацию в выбранной больнице",
        "Таңдалған ауруханаға жазылу мен тіркелуді нақтылаңыз",
        "向所选医院确认预约和挂号方式",
        "Confirm appointment and registration with the selected hospital",
    ),
    "medical_preparation": (
        "Подготовьте описание симптомов, лекарств и аллергий для врача",
        "Дәрігерге белгілер, дәрілер және аллергия туралы мәлімет дайындаңыз",
        "为医生准备症状、用药和过敏信息",
        "Prepare symptoms, medication and allergy information for the clinician",
    ),
    "safe_help": (
        "При непосредственной угрозе немедленно обратитесь за местной экстренной помощью",
        "Тікелей қауіп болса, дереу жергілікті шұғыл көмекке жүгініңіз",
        "如有迫在眉睫的危险，请立即联系当地紧急救援",
        "For immediate danger, contact local emergency help now",
    ),
    "emergency_facts": (
        "Сообщите помощнику место и ключевые обстоятельства; не ждите ответа приложения",
        "Көмек көрсетушіге орын мен мән-жайды айтыңыз; қосымша жауабын күтпеңіз",
        "告知救助人员地点和关键情况，不要等待应用回复",
        "Tell the responder your location and key facts; do not wait for the app",
    ),
    "notice": (
        "Определите документ, отправителя и указанный срок",
        "Құжатты, жіберушіні және көрсетілген мерзімді анықтаңыз",
        "确认文件类型、发送方和注明的期限",
        "Identify the document, sender and stated deadline",
    ),
    "document_questions": (
        "Уточните непонятные требования у выдавшей документ организации",
        "Түсініксіз талаптарды құжат берген ұйымнан нақтылаңыз",
        "向签发机构确认不清楚的要求",
        "Clarify unclear requirements with the issuing institution",
    ),
    "housing": (
        "Сверьте договор, условия оплаты и сведения о жилье",
        "Шартты, төлем талаптарын және тұрғын үй туралы мәліметті салыстырыңыз",
        "核对租约、付款条件和房屋信息",
        "Check the agreement, payment terms and accommodation details",
    ),
    "housing_records": (
        "Сохраните подтверждения и уточните местный порядок регистрации",
        "Растамаларды сақтап, жергілікті тіркеу тәртібін нақтылаңыз",
        "保存凭证并确认当地住宿登记流程",
        "Keep records and confirm the local accommodation registration process",
    ),
    "payment_official": (
        "Откройте официальный раздел настройки или поддержки платёжного приложения",
        "Төлем қолданбасының ресми баптау не қолдау бөлімін ашыңыз",
        "打开支付应用的官方设置或帮助页面",
        "Open the payment app's official setup or support section",
    ),
    "payment_backup": (
        "Подготовьте запасной способ оплаты; не передавайте коды другим людям",
        "Қосалқы төлем тәсілін дайындаңыз; кодтарды басқа адамдарға бермеңіз",
        "准备备用支付方式，不要向他人提供验证码",
        "Prepare a backup payment method; do not share verification codes",
    ),
    "transport_route": (
        "Подтвердите маршрут, станцию или аэропорт и время отправления",
        "Бағытты, вокзал не әуежайды және жөнелту уақытын растаңыз",
        "确认路线、车站或机场及出发时间",
        "Confirm the route, station or airport and departure time",
    ),
    "transport_documents": (
        "Уточните у перевозчика документы и условия изменения билета",
        "Тасымалдаушыдан құжаттар мен билетті өзгерту шарттарын нақтылаңыз",
        "向承运方确认所需证件和改签条件",
        "Check identification and ticket-change conditions with the carrier",
    ),
    "translation_review": (
        "Сверьте оригинал, даты, суммы и отрицания в распознанном тексте",
        "Түпнұсқаны, күндерді, сомаларды және танылған мәтіндегі терістеуді салыстырыңыз",
        "核对原文、日期、金额和识别文本中的否定词",
        "Check the original, dates, amounts and negations in the extracted text",
    ),
    "translation_reply": (
        "Проверьте смысл и отредактируйте ответ перед отправкой",
        "Мағынасын тексеріп, жіберер алдында жауапты өңдеңіз",
        "确认含义并在发送前编辑回复",
        "Confirm the meaning and edit the reply before sending",
    ),
    "community_context": (
        "Уточните город, дату и обстоятельства чужого опыта",
        "Басқа адамның тәжірибесіндегі қала, күн және жағдайды нақтылаңыз",
        "确认经验分享的城市、日期和具体情况",
        "Check the city, date and circumstances of the shared experience",
    ),
    "community_verify": (
        "Проверьте обязательные требования по официальным источникам",
        "Міндетті талаптарды ресми дереккөздерден тексеріңіз",
        "通过官方来源核实强制要求",
        "Verify mandatory requirements with official sources",
    ),
    "clarify": (
        "Уточните цель, город и срочность задачи",
        "Мақсатты, қаланы және мәселенің шұғылдығын нақтылаңыз",
        "补充目标、城市和紧急程度",
        "Clarify the goal, city and urgency",
    ),
}
PLANS = {
    "tourism": ("travel_plan", "arrival"),
    "kazakhstan_entry": (
        "kazakhstan_visa",
        "kazakhstan_purpose",
        "kazakhstan_evisa",
        "kazakhstan_arrival",
    ),
    "study": ("enrollment", "student_documents"),
    "work": ("employer", "work_status"),
    "business": ("meeting", "business_documents"),
    "medical": ("hospital", "medical_preparation"),
    "emergency": ("safe_help", "emergency_facts"),
    "documents": ("notice", "document_questions"),
    "housing": ("housing", "housing_records"),
    "payments": ("payment_official", "payment_backup"),
    "transport": ("transport_route", "transport_documents"),
    "translation": ("translation_review", "translation_reply"),
    "community_experience": ("community_context", "community_verify"),
    "unclear": ("clarify", "community_verify"),
}


def preparation_steps(scenario: UserScenario, language: LanguageCode) -> list[tuple[str, str]]:
    index = LANGUAGES.index(language) if language in LANGUAGES else 0
    return [(key, STEPS[key][index]) for key in PLANS[scenario.value]]
