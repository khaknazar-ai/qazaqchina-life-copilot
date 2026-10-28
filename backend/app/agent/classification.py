"""Shared offline routing rules; unknown requests never acquire invented context.

These conservative rules are a deterministic baseline, not a diagnosis. Keep the
emergency signal separate from the scenario so a hospital case stays medical.
"""

import re
from typing import Literal

from backend.app.domain.enums import RiskLevel, UserScenario

PaymentIntent = Literal["setup", "failure", "refund", "scam", "general"]

PASSPORT = ("passport", "паспорт", "төлқұжат", "护照")
LOSS = (
    "lost",
    "stolen",
    "missing",
    "can't find",
    "cannot find",
    "потер",
    "утер",
    "укра",
    "не могу найти",
    "жоғал",
    "ұрлан",
    "таба алмай",
    "丢",
    "遗失",
    "被偷",
    "找不到",
)
ACUTE_MEDICAL = (
    "chest pain",
    "cannot breathe",
    "can't breathe",
    "difficulty breathing",
    "trouble breathing",
    "shortness of breath",
    "unconscious",
    "severe bleeding",
    "not breathing",
    "unresponsive",
    "seizure",
    "overdose",
    "heart attack",
    "stroke symptoms",
    "can't stop bleeding",
    "боль в груди",
    "болит груд",
    "трудно дышать",
    "не могу дышать",
    "задыха",
    "без сознания",
    "сильное кровотечение",
    "не дышит",
    "судорог",
    "не приходит в сознание",
    "передозиров",
    "кеудем ауыра",
    "кеуде ауыру",
    "дем ала алмай",
    "тыныс алу қиын",
    "есінен тан",
    "қатты қан кет",
    "тыныс алмай",
    "құрысу",
    "胸痛",
    "胸口痛",
    "呼吸困难",
    "喘不过气",
    "无法呼吸",
    "昏迷",
    "大量出血",
    "没有呼吸",
    "抽搐",
    "无法唤醒",
    "药物过量",
)
DANGER = (
    "immediate danger",
    "being attacked",
    "emergency",
    "call an ambulance",
    "threatening me",
    "being threatened",
    "being assaulted",
    "want to kill myself",
    "want to end my life",
    "мне угрожают",
    "на меня напали",
    "вызвать скорую",
    "срочная помощь",
    "меня избили",
    "в опасности",
    "хочу покончить с собой",
    "хочу убить себя",
    "төтенше",
    "қауіп төніп",
    "жедел жәрдем",
    "шабуыл жасалды",
    "өзімді өлтір",
    "紧急",
    "有危险",
    "被袭击",
    "叫救护车",
    "威胁我",
    "想自杀",
    "想杀死自己",
)
MEDICAL = (
    "hospital",
    "medical",
    "doctor",
    "clinic",
    "symptom",
    "pain",
    "symptoms",
    "fever",
    "больниц",
    "врач",
    "клиник",
    "болит",
    "температур",
    "боль",
    "медицин",
    "аурухана",
    "дәрігер",
    "ауырып",
    "денсаулық",
    "医院",
    "病",
    "医生",
    "发烧",
    "疼",
)
WORK = (
    "work",
    "working",
    "job",
    "employment",
    "employer",
    "работ",
    "трудов",
    "жұмыс",
    "еңбек",
    "工作",
    "就业",
    "雇主",
    "劳动",
)
WORK_STATUS = (
    "tourist",
    "visa",
    "permit",
    "contract",
    "authorization",
    "documents later",
    "start first",
    "start now",
    "documents are unclear",
    "paid cash",
    "without papers",
    "турист",
    "виз",
    "разрешен",
    "договор",
    "контракт",
    "без документ",
    "потом оформ",
    "рұқсат",
    "шарт",
    "құжат",
    "签证",
    "许可",
    "合同",
    "无证",
    "先工作",
    "以后办",
)
REGISTRATION = (
    "housing registration",
    "residence registration",
    "accommodation registration",
    "police station registration",
    "регистрация проживания",
    "регистрации проживания",
    "регистрация по месту",
    "регистрации по месту",
    "регистрацию по месту",
    "регистрацией по месту",
    "миграционный учет",
    "тұрғылықты жер бойынша тіркеу",
    "тұрғылықты тіркеу",
    "住宿登记",
    "居住登记",
    "派出所登记",
)
LEGAL_DOCUMENTS = (
    "power of attorney",
    "notarial",
    "notarization",
    "notary",
    "доверенн",
    "нотариальн",
    "нотариус",
    "апостиль",
    "сенімхат",
    "нотариалды",
    "委托书",
    "授权书",
    "公证",
    "领事文件",
)
VISA = (
    "visa",
    "overstay",
    "immigration",
    "residence permit",
    "виз",
    "миграц",
    "виза",
    "тұруға рұқсат",
    "签证",
    "居留许可",
    "逾期停留",
)
KAZAKHSTAN_ENTRY_PHRASES = (
    "travel to kazakhstan",
    "travelling to kazakhstan",
    "traveling to kazakhstan",
    "trip to kazakhstan",
    "go to kazakhstan",
    "going to kazakhstan",
    "visit kazakhstan",
    "visiting kazakhstan",
    "enter kazakhstan",
    "entering kazakhstan",
    "entry to kazakhstan",
    "kazakhstan entry",
    "visa to kazakhstan",
    "visa for kazakhstan",
    "kazakhstan visa",
    "tourist visa kazakhstan",
    "tourist evisa",
    "tourist e-visa",
    "tourism in kazakhstan",
    "tourism kazakhstan",
    "travel to kz",
    "trip to kz",
    "visa for kz",
    "go to kz",
    "going to kz",
    "visit kz",
    "entry to kz",
    "виза казахстан",
    "визовый режим казахстан",
    "нужна ли виза в казахстан",
    "визу в казахстан",
    "для поездки в казахстан",
    "поехать в казахстан",
    "ехать в казахстан",
    "как въехать в казахстан",
    "лететь в казахстан",
    "лечу в казахстан",
    "летим в казахстан",
    "вылет в казахстан",
    "собираюсь поехать в казахстан",
    "планирую поехать в казахстан",
    "планирует поездку в казахстан",
    "планируют поездку в казахстан",
    "планируем поездку в казахстан",
    "хочу поехать в казахстан",
    "хочу ехать в казахстан",
    "иностранец едет в казахстан",
    "иностранцы едут в казахстан",
    "планирую поездку в кз",
    "собираюсь поехать в кз",
    "планирует поехать в кз",
    "въезд в кз",
    "поездка в казахстан",
    "поездку в казахстан",
    "поеду в казахстан",
    "еду в казахстан",
    "планирую поездку в казахстан",
    "собираюсь в казахстан",
    "въезд в казахстан",
    "въехать в казахстан",
    "въезд в рк",
    "виза в казахстан",
    "виза казахстана",
    "казахстанская виза",
    "туристическая виза казахстан",
    "туристическая виза в казахстан",
    "туризм в казахстане",
    "туризм в кз",
    "туристическая поездка в казахстан",
    "отдых в казахстане",
    "поездка в кз",
    "виза в кз",
    "қазақстанға сапар",
    "қазақстанға бару",
    "қазақстанға кіру",
    "қазақстанға",
    "қазақстан визасы",
    "қазақстанның визасы",
    "қазақстанға виза",
    "қазақстанға туристік виза",
    "қазақстандағы туризм",
    "哈萨克斯坦签证",
    "哈萨克斯坦旅游签证",
    "去哈萨克斯坦旅游",
    "哈萨克斯坦要签证",
    "去哈萨克斯坦需要签证",
    "到哈萨克斯坦需要签证",
    "去哈萨克斯坦",
    "赴哈萨克斯坦",
    "访问哈萨克斯坦",
    "入境哈萨克斯坦",
    "哈萨克斯坦入境",
    "work visa in kazakhstan",
    "work visa kazakhstan",
    "work in kazakhstan",
    "working in kazakhstan",
    "business visa kazakhstan",
    "business in kazakhstan",
    "business immigrant kazakhstan",
    "business trip to kazakhstan",
    "business visit to kazakhstan",
    "study in kazakhstan",
    "student visa kazakhstan",
    "permanent residence kazakhstan",
    "open bank account in kazakhstan",
    "bank account in kazakhstan",
    "iin in kazakhstan",
    "get an iin in kazakhstan",
    "e-residency kazakhstan",
    "eresidency kazakhstan",
    "kazakhstan consular services",
    "рабочая виза казахстан",
    "работа в казахстане",
    "работать в казахстане",
    "бизнес виза казахстан",
    "деловая виза в казахстан",
    "деловая поездка в казахстан",
    "командировка в казахстан",
    "по делам в казахстан",
    "бизнес-иммигрант",
    "бизнес в казахстане",
    "учебная виза казахстан",
    "учиться в казахстане",
    "постоянное проживание казахстан",
    "иин в казахстане",
    "иин иностранцу",
    "получить иин",
    "открыть счет в казахстане",
    "открыть счёт в казахстане",
    "банковский счет в казахстане",
    "банковский счёт в казахстане",
    "eresidency",
    "консульство казахстана в китае",
    "жсн шетелдікке",
    "қазақстанда жұмыс істеу",
    "қазақстанда жұмыс",
    "қазақстанда бизнес",
    "қазақстанға іссапар",
    "қазақстанда банк шотын ашу",
    "哈萨克斯坦工作签证",
    "去哈萨克斯坦工作",
    "哈萨克斯坦商务签证",
    "赴哈萨克斯坦商务",
    "哈萨克斯坦开银行账户",
    "哈萨克斯坦个人识别号码",
    "哈萨克斯坦学习签证",
    "哈萨克斯坦居留",
    "c3 visa",
    "c5 visa",
    "c9 visa",
    "b2 visa",
    "b8 visa",
    "b10 visa",
    "c10 visa",
    "виза c3",
    "виза с3",
    "виза c5",
    "виза с5",
    "виза c9",
    "виза с9",
    "виза b2",
    "виза b8",
    "виза b10",
    "виза c10",
    "виза с10",
    "c10",
    "с10",
    "c9",
    "с9",
    "c3",
    "с3",
    "c5",
    "с5",
    "b2",
    "в2",
    "b8",
    "в8",
    "b10",
    "в10",
    "виза c10",
    "виза с10",
    "иин для иностранца",
    "иин для иностранцев",
    "иин иностранным гражданам",
    "банк иностранцу в казахстане",
    "открытие счета иностранцу",
    "открытие счёта иностранцу",
    "бизнес в рк",
    "работа в рк",
    "учеба в рк",
    "учёба в рк",
    "консульские услуги иностранцам рк",
)
PAYMENTS = (
    "alipay",
    "wechat pay",
    "payment",
    "bank card",
    "sim card",
    "refund",
    "scam",
    "платеж",
    "платёж",
    "оплат",
    "банк",
    "возврат денег",
    "мошенни",
    "сим-карт",
    "төлем",
    "төле",
    "банк карт",
    "алаяқ",
    "支付宝",
    "微信支付",
    "支付",
    "银行卡",
    "退款",
    "诈骗",
)
TRANSLATION = (
    "translate",
    "translation",
    "explain this notice",
    "explain this chinese",
    "explain the notice",
    "explain this notification",
    "explain this photo",
    "переведи",
    "перевод текста",
    "перевод уведомления",
    "объясни уведомление",
    "объясни китайское",
    "аудар",
    "хабарламаны түсіндір",
    "қазақша түсіндір",
    "翻译",
    "解释这段",
    "解释通知",
)
COMMUNITY = (
    "community experience",
    "others experience",
    "other students' experience",
    "опыт сообщества",
    "чужой опыт",
    "своем опыте",
    "личным опытом",
    "қауымдастық",
    "тәжірибесімен бөліс",
    "经验分享",
    "分享经验",
    "别人的经验",
)
INJECTION = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignore all instructions",
    "show api key",
    "reveal secret",
    "jailbreak",
    "reveal the system prompt",
    "reveal your system prompt",
    "show the system prompt",
    "игнорируй инструкции",
    "игнорируй предыдущие инструкции",
    "покажи api ключ",
    "раскрой системный промпт",
    "нұсқауларды елеме",
    "忽略之前的指令",
    "泄露密钥",
)

# Remove only explicit, local negations. "Cannot breathe" remains an emergency
# signal in every supported language.
NEGATED_SIGNALS = (
    r"\bnot (?:an? )?emergency\b",
    r"\bnon-emergency\b",
    r"\b(?:not|never) (?:lost|stolen|missing)\b",
    r"\b(?:did not|didn't|haven't|have not) (?:lose|lost)\b",
    r"\bno (?:chest pain|difficulty breathing|trouble breathing|severe bleeding)\b",
    r"не (?:потерял\w*|утерян\w*|украден\w*)",
    r"нет боли в груди",
    r"не экстренн\w*",
    r"не (?:задыхаюсь|в опасности)",
    r"жоғалған жоқ",
    r"жоғалма\w*",
    r"кеудем ауырмайды",
    r"төтенше жағдай емес",
    r"тыныс алу қиын емес",
    r"(?:没|没有|并未)(?:丢失|丢|遗失|被偷)",
    r"(?:没有|无)(?:胸痛|呼吸困难|大量出血)",
    r"不是紧急(?:情况)?",
)


def _normalized(message: str) -> str:
    return " ".join(message.casefold().replace("ё", "е").split())


def is_kazakhstan_entry_request(message: str) -> bool:
    """Match travel whose destination is Kazakhstan, not a Kazakh citizen abroad."""
    text = _normalized(message)
    return any(phrase in text for phrase in KAZAKHSTAN_ENTRY_PHRASES)


def _active_signals(message: str) -> str:
    text = _normalized(message)
    for pattern in NEGATED_SIGNALS:
        text = re.sub(pattern, " ", text)
    return text


def _has(message: str, terms: tuple[str, ...]) -> bool:
    # English words should not turn "homework" or "network" into employment.
    return any(
        bool(re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", message))
        if term.isascii()
        else term in message
        for term in terms
    )


def is_acute_medical(message: str) -> bool:
    return _has(_active_signals(message), ACUTE_MEDICAL)


def is_document_loss(message: str) -> bool:
    text = _active_signals(message)
    clauses = re.split(r"[.;!?。；！？]|\b(?:but|но|бірақ)\b|但是", text)
    return any(_has(clause, PASSPORT) and _has(clause, LOSS) for clause in clauses)


def quoted_translation_content(message: str) -> bool:
    """Whether an explicit explanation request supplies a delimited text payload.

    The payload remains untrusted; it never becomes instructions or evidence.
    Prefix instructions are still checked independently for an active override.
    """
    return _translation_instruction_surface(message) is not None


def _translation_instruction_surface(message: str) -> str | None:
    delimiter = re.search(r'[:\n："“«「]', message)
    if delimiter is None:
        return None
    prefix = message[: delimiter.start()]
    if len(prefix) > 180 or not _has(_normalized(prefix), TRANSLATION):
        return None
    remainder = message[delimiter.start() :]
    if remainder[0] in ":\n：":
        remainder = remainder[1:].lstrip()
    closing_quotes = {'"': '"', "“": "”", "«": "»", "「": "」"}
    if remainder and remainder[0] in closing_quotes:
        closing = remainder.find(closing_quotes[remainder[0]], 1)
        if closing != -1:
            # Instructions outside the quotation must still pass the guard.
            return prefix + " " + remainder[closing + 1 :]
    return prefix


def has_active_prompt_injection(message: str) -> bool:
    surface = _translation_instruction_surface(message)
    text = message if surface is None else surface
    return _has(_normalized(text), INJECTION)


def _has_employment(text: str) -> bool:
    if not _has(text, WORK):
        return False
    if _has(text, PAYMENTS) and _has(
        text,
        (
            "not working",
            "не работает",
            "жұмыс істемейді",
            "无法工作",
        ),
    ):
        remaining = text
        for phrase in ("not working", "не работает", "жұмыс істемейді", "无法工作"):
            remaining = remaining.replace(phrase, "")
        return _has(remaining, WORK)
    return True


def payment_intent(message: str) -> PaymentIntent:
    text = _normalized(message)
    if _has(text, ("verification code", "код подтверждения", "растау код", "验证码")) and _has(
        text, ("stranger", "share", "незнаком", "сообщить", "жібер", "陌生人", "发给别人")
    ):
        return "scam"
    groups: tuple[tuple[PaymentIntent, tuple[str, ...]], ...] = (
        (
            "scam",
            (
                "scam",
                "fraud",
                "stolen money",
                "мошенни",
                "обман",
                "украли деньги",
                "алаяқ",
                "алдан",
                "诈骗",
                "被骗",
            ),
        ),
        ("refund", ("refund", "chargeback", "возврат", "вернуть деньги", "қайтар", "退款", "退钱")),
        (
            "failure",
            (
                "declined",
                "failed",
                "not working",
                "can't pay",
                "cannot pay",
                "не работает",
                "не проходит",
                "отклон",
                "төлем өтп",
                "істемейді",
                "支付失败",
                "无法支付",
            ),
        ),
        (
            "setup",
            (
                "set up",
                "setup",
                "register",
                "link",
                "activate",
                "add card",
                "настро",
                "подключ",
                "привяз",
                "қосу",
                "баптау",
                "тіркел",
                "开通",
                "绑定",
                "注册",
                "设置",
            ),
        ),
    )
    return next((intent for intent, terms in groups if _has(text, terms)), "general")


def classify_scenario(message: str) -> UserScenario:
    text = _normalized(message)
    if is_acute_medical(message):
        return UserScenario.medical
    if is_document_loss(message) or _has(_active_signals(message), DANGER):
        return UserScenario.emergency
    if _has(text, TRANSLATION):
        return UserScenario.translation
    if is_kazakhstan_entry_request(message):
        return UserScenario.kazakhstan_entry
    if _has(text, COMMUNITY):
        return UserScenario.community_experience
    if _has_employment(text):
        return UserScenario.work
    if _has(text, REGISTRATION):
        return UserScenario.housing
    if _has(text, VISA):
        return UserScenario.documents
    if _has(text, LEGAL_DOCUMENTS):
        return UserScenario.documents
    if _has(text, MEDICAL):
        return UserScenario.medical
    if _has(text, PAYMENTS):
        return UserScenario.payments
    groups = (
        (UserScenario.medical, MEDICAL),
        (
            UserScenario.study,
            (
                "study",
                "student",
                "university",
                "enrollment",
                "учеб",
                "учеба",
                "университет",
                "студент",
                "оқу",
                "大学",
                "留学",
                "入学",
            ),
        ),
        (UserScenario.payments, PAYMENTS),
        (
            UserScenario.housing,
            (
                "housing",
                "apartment",
                "landlord",
                "rent",
                "жиль",
                "квартир",
                "аренд",
                "пәтер",
                "жалға",
                "房东",
                "租房",
                "住宿",
            ),
        ),
        (
            UserScenario.transport,
            (
                "train",
                "railway",
                "flight",
                "airport",
                "metro",
                "bus",
                "поезд",
                "билет",
                "аэропорт",
                "көлік",
                "пойыз",
                "ұшақ",
                "火车",
                "高铁",
                "机票",
                "地铁",
                "公交",
            ),
        ),
        (
            UserScenario.business,
            (
                "business",
                "company",
                "entrepreneur",
                "supplier",
                "бизнес",
                "компани",
                "поставщик",
                "кәсіп",
                "жеткізуші",
                "商务",
                "公司",
                "供应商",
            ),
        ),
        (
            UserScenario.community_experience,
            (*COMMUNITY,),
        ),
        (
            UserScenario.tourism,
            (
                "tourism",
                "tourist",
                "sightseeing",
                "travel",
                "туризм",
                "турист",
                "путешеств",
                "саяхат",
                "旅游",
                "旅行",
            ),
        ),
    )
    matched = next((scenario for scenario, terms in groups if _has(text, terms)), None)
    return matched or (UserScenario.documents if _has(text, PASSPORT) else UserScenario.unclear)


def requests_document_forgery(message: str) -> bool:
    """Separate requests to fabricate credentials from reporting or translating them."""
    surface = _translation_instruction_surface(message)
    text = _normalized(message if surface is None else surface)
    # A benign report or negation applies only to its own clause. Otherwise
    # "report identity theft and how to forge a visa" exempts the active request.
    request_start = (
        r"how (?:to|can i|do i)|help me|can you|i (?:want|need)|teach me|where can i buy|"
        r"как|помоги|сделай|хочу|қалай|көмектес|жаса|怎么|如何|帮我|教我|我要|请|想"
    )
    clauses = []
    for sentence in re.split(
        r"[.;!?。；！？]|\b(?:but|also|then|но|также|затем|бірақ)\b|但是", text,
    ):
        starts = request_start
        # A fresh explicit request ends a negation's scope; a coordinated verb
        # alone does not: "do not forge a passport and fake a visa" stays benign.
        if not _has(sentence, (
            "avoid fake", "do not want to fake", "don't want to fake", "do not forge",
            "не хочу подделывать",
        )):
            starts += r"|forge\b|falsify\b|fake\s+(?:a|an|the|my|your)\b"
        clauses.extend(re.split(
            rf"(?:[,，]|\b(?:and|и|және)\b|并且|而且|同时|并)\s*"
            rf"(?=[^,，.;!?。；！？]*(?:{starts}))",
            sentence,
        ))
    for clause in clauses:
        if _has(
            clause,
            (
                "how to report",
                "report fake documents",
                "report document forgery",
                "verify authenticity",
                "check whether",
                "detect forged",
                "avoid fake",
                "do not want to fake",
                "don't want to fake",
                "do not forge",
                "проверить подлинность",
                "распознать подделку",
                "сообщить о подделке",
                "не хочу подделывать",
                "қалай анықта",
                "举报伪造",
                "识别伪造",
                "检查真伪",
            ),
        ):
            continue
        document = _has(
            clause,
            (
                *PASSPORT,
                *VISA,
                "documents",
                "document",
                "credentials",
                "документ",
                "справк",
                "құжат",
                "证件",
                "材料",
                "假证",
            ),
        )
        request = _has(
            clause,
            (
                "how can i",
                "how do i",
                "how to",
                "help me",
                "can you",
                "i want",
                "i need",
                "teach me",
                "where can i buy",
                "как",
                "помоги",
                "сделай",
                "хочу",
                "қалай",
                "көмектес",
                "жаса",
                "怎么",
                "如何",
                "帮我",
                "教我",
                "我要",
                "请",
                "想",
            ),
        ) or bool(re.match(r"(?:fake|forge|falsify)\b", clause.strip()))
        action = _has(
            clause,
            (
                "fake",
                "forge",
                "falsify",
                "подделать",
                "поддельн",
                "қолдан жаса",
                "жалған",
                "伪造",
                "制作假",
                "办假证",
            ),
        )
        if document and request and action:
            return True
    return False


def classify_risk(message: str, scenario: UserScenario | None = None) -> RiskLevel:
    text = _normalized(message)
    active_scenario = scenario or classify_scenario(message)
    if has_active_prompt_injection(message):
        return RiskLevel.prompt_injection
    if (
        is_acute_medical(message)
        or is_document_loss(message)
        or _has(_active_signals(message), DANGER)
    ):
        return RiskLevel.emergency
    if requests_document_forgery(message):
        return RiskLevel.unsafe
    if active_scenario == UserScenario.kazakhstan_entry:
        if _has(text, WORK) and _has(text, WORK_STATUS):
            return RiskLevel.work_status_sensitive
        return RiskLevel.legal_sensitive
    if active_scenario == UserScenario.work and _has(text, WORK_STATUS):
        return RiskLevel.work_status_sensitive
    if _has(text, LEGAL_DOCUMENTS):
        return RiskLevel.legal_sensitive
    if _has(text, VISA) or _has(text, REGISTRATION) or _has(text, PASSPORT):
        return RiskLevel.legal_sensitive
    if _has(text, MEDICAL):
        return RiskLevel.medical_sensitive
    if active_scenario == UserScenario.payments and payment_intent(message) == "scam":
        return RiskLevel.medium
    return RiskLevel.normal
