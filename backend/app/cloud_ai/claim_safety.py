"""Conservative, explicit cross-language checks before semantic approval can help.

This is not a general entailment engine. Unsupported number formats and changes
to explicit conditions, negation or modality fail closed, even if a model agrees.
"""

import re
from collections import Counter
from decimal import Decimal

from backend.app.cloud_ai.document_numbers import numeric_details_match, protected_detail_spans

_MARKERS = {
    "prohibition": r"must not|cannot|can't|not allowed|prohibited|forbidden|"
    r"不得|不能|禁止|不允许|不可|勿|不要|别|甭|莫|"
    r"нельзя|запрещ\w*|не (?:долж\w*|разрешено)|болмайды|тыйым",
    "no_obligation": r"not required|not necessary|do not need|don't need|need not|"
    r"无需|不需要|不必|не (?:требуется|нужно|обязан\w*)|қажет емес",
    "obligation": r"\bmust\b|\brequired\b|\bmandatory\b|need to|have to|"
    r"必须|应当|需要|须|долж\w*|обязан\w*|необходимо|обязательно|требуется|міндетті|тиіс",
    "request": r"\bplease\b|(?<!申)请|пожалуйста|просим|өтінем",
    "advice": r"\bshould\b|recommend\w*|建议|最好|следует|рекоменд\w*|жөн",
    "permission": r"\bmay\b|\bcan\b|allowed|permitted|可以|允许|можно|разрешено|"
    r"могут|может|можете|рұқсат",
    "if": r"\bif\b|如果|若|如(?=已|未|需|有)|если|егер",
    "unless": r"\bunless\b|除非|если не|болмаса",
    "exception": r"\bexcept\b|exception|除外|除了|例外|исключени\w*|кроме|басқа",
    "only": r"\bonly\b|仅|只有|только|лишь|тек\b",
    "within": r"\bwithin\b|小时内|天内|日内|в течение|ішінде",
    "before": r"\bbefore\b|前|\bдо\b|дейін",
    "after": r"\bafter\b|后|после|кейін",
    "during": r"\bduring\b|期间|во время|кезінде",
    "until": r"\buntil\b|直到|直至|пока|дейін",
    "cancelled": r"\bcancel(?:led|ed|lation)?\b|取消|отмен\w*|тоқтат\w*",
    "denial": r"\bnot\b|\bno\b|\bnever\b|\bwithout\b|未|没有|不|无|"
    r"\bне\b|\bнет\b|\bбез\b|емес|жоқ",
    # Ambiguous negative morphology is literal only, never approved from a
    # same-model boolean. This intentionally over-withholds unknown forms.
    "negative_morphology": r"\b\w+n['’]t\b|\bне[а-яё]\w*|"
    r"\b(?:unregistered|ineligible|unauthori[sz]ed|invalid|unavailable|unable)\b",
    "minimum": r"at least|minimum|\bover(?=\s|\d)|more than|older than|至少|超过|大于|"
    r"не менее|старше|более|кемінде",
    "maximum": r"at most|maximum|up to|\bunder(?=\s|\d)|less than|younger than|最多|不超过|"
    r"未满|少于|не более|младше|менее|дейін ғана",
    "and": r"\band\b|\bboth\b|以及|和|且|\bи\b|мен\b",
    "or": r"\bor\b|或者|或|\bили\b|немесе",
    "lost": r"\blost\b|\bloss\b|丢失|遗失|утер\w*|потер\w*|жоғал\w*",
    "found": r"\bfound\b|\brecovered\b|找回|找到|найден\w*|нашл\w*|табыл\w*",
}
_SCOPE = {
    "student": r"\bstudents?\b|学生|студент\w*|студенческ\w*",
    "tourist": r"\btourists?\b|旅游|турист\w*",
    "foreign": r"\bforeign\b|\bforeigners?\b|外国|иностран\w*|шетел",
    "passport": r"\bpassport\b|护照|паспорт\w*|төлқұжат",
    "visa": r"\bvisa\b|签证|\bвиз\w*|виза",
    "permit": r"\bpermits?\b|许可|разрешени\w*|рұқсат",
    "hotel": r"\bhotels?\b|旅馆|酒店|гостиниц\w*|отел\w*|қонақүй",
    "work": r"\bwork\b|\bworking\b|工作|就业|работ\w*|жұмыс",
    "registration": r"\bregister\w*|\bregistration\b|登记|регистрац\w*|зарегистр\w*|тірке",
    "already": r"\balready\b|已经|已(?=登记|办理|注册)|уже|әлдеқашан",
    "check_in": r"checking in|check(?:ed)?[ -]in|入住|заселени\w*",
    "arrival": r"\barrival\b|\barriv\w*|到达|прибыт\w*",
    "expiry": r"\bexpir\w*|到期|истечени\w*|истека\w*",
    "payment": r"\bpay\w*|支付|缴费|опла[тч]\w*|төлем",
    "beijing": r"\bbeijing\b|北京|пекин\w*",
    "shanghai": r"\bshanghai\b|上海|шанха\w*",
    "guangzhou": r"\bguangzhou\b|广州|гуанчжоу",
}
_UNITS = {
    "hour": r"hours?|小时|час\w*|сағат",
    "day": r"days?|天|日|дней|дня|день|күн",
    "week": r"weeks?|周|недел\w*|апта",
    "month": r"months?|个月|месяц\w*|ай",
    "year": r"years?|岁|年|лет|года?",
}
_QUANTITY = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>" + "|".join(_UNITS.values()) + ")", re.I,
)
_SPELLED_QUANTITY = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)"
    r"[\w\s-]{0,24}\b(?:hours?|days?|weeks?|months?)\b|"
    r"\b(?:один|одна|два|две|три|четыре|пять|десять|двадцать|тридцать|сорок|сто)"
    r"[\w\s-]{0,24}(?:час\w*|дней|дня|день|недел\w*|месяц\w*)\b|"
    r"[一二三四五六七八九十百千万零两]+(?:小时|天|日|周|个月|元)", re.I,
)
_EVENTS = {
    "check_in": r"checking in|check-in|入住|заселени\w*",
    "arrival": r"arrival|arriving|到达|прибыт\w*",
    "registration": r"registration|registering|登记|регистрац\w*",
    "appointment": r"appointment|预约|при[её]м\w*|запис\w*",
    "payment": r"payment|paying|支付|缴费|оплат\w*",
    "expiry": r"expiry|expiration|到期|истечени\w*",
}
_CONCEPTS = {
    "you": r"\byou\b|\bвы\b|您|你",
    "we": r"\bwe\b|\bмы\b|我们",
    "foreign": r"\bforeign nationals\b|\bforeigners?\b|外国人|иностран\w*",
    "student": _SCOPE["student"], "tourist": _SCOPE["tourist"],
    "applicant": r"\bapplicants?\b|申请人|заявител\w*",
    "passport": _SCOPE["passport"], "visa": _SCOPE["visa"],
    "registration": r"\bcomplete (?:accommodation )?registration\b|"
    r"оформить регистрацию|" + _SCOPE["registration"],
    "lodging": r"\baccommodation\b|住宿|проживани\w*",
    "bring": r"\bbring\w*|携带|带上|принести|принес\w*|предъяв\w*",
    "submit": r"\bsubmit\w*|提交|递交|подать|пода[йё]\w*",
    "contact": r"\bcontact\w*|联系|обратит\w*|свяж\w*",
    "book": r"\b(?:book|make|schedule) (?:an?|the|your) appointment\b|"
    r"записаться на при[её]м",
    "appointment": r"\bappointments?\b|预约|при[её]м\w*|запис\w*",
    "payment": _SCOPE["payment"],
    "cancellation": r"\bcancellations?\b|\bотмена\b|\bотмены\b",
    "cancel": r"\bcancel(?:s|led|ed|ling|ing)?\b|取消|отмен\w*",
    "documents": r"\bdocuments?\b|材料|文件|документ\w*",
    "original": r"\boriginals?\b|原件|оригинал\w*",
    "office": r"\boffice\b|办公室|офис\w*",
    "service": r"\bservices?\b|服务|служб\w*",
    "official": r"\bofficial\b|官方|официальн\w*",
    "hold": r"\bhold\w*|\bhave\b|持有|\bесть\b|имеет\w*",
    "already": _SCOPE["already"],
    "and": _MARKERS["and"], "or": _MARKERS["or"],
    **{key: _MARKERS[key] for key in ("obligation", "request", "advice", "permission")},
}
_GRAMMAR = re.compile(
    r"\b(?:a|an|the|your|for|to|of|in|at|is|are|it|this|be|has|been|"
    r"у|вас|ваш\w*|для|на|в|к|и)\b|'s\b|在|的|被|[\s.,:;!?。！？，；：-]+", re.I,
)
_ACTIONS = {"bring", "submit", "contact", "payment", "cancel", "hold", "book"}
_MODALS = {"obligation", "request", "advice", "permission"}
_CONTEXT = {"lodging"}  # Topic specificity remains part of the typed semantic review.
_KAZAKH_NEGATIVE = re.compile(
    r"\b[а-яёәғқңөұүһі]+(?:ма|ме|ба|бе|па|пе)(?:(?:ң|й|ды|ді|ған|ген|с)\w*)?\b", re.I,
)
_CONTRACTIONS = {
    "can't": "cannot", "won't": "will not", "shan't": "shall not",
    "needn't": "need not", "don't": "do not", "doesn't": "does not",
    "didn't": "did not", "isn't": "is not", "aren't": "are not",
    "wasn't": "was not", "weren't": "were not", "haven't": "have not",
    "hasn't": "has not", "hadn't": "had not", "mustn't": "must not",
    "shouldn't": "should not", "couldn't": "could not", "wouldn't": "would not",
}


def _polarity_text(text: str) -> str:
    text = text.casefold().translate(str.maketrans({"’": "'", "‘": "'", "ʼ": "'"}))
    return re.sub(r"\b[a-z]+n't\b", lambda match: _CONTRACTIONS.get(
        match.group(), match.group(),
    ), text)


def _kazakh_negatives(text: str, language: str | None) -> int:
    if language != "kk" and not re.search(r"[әғқңөұүһі]", text, re.I):
        return 0
    return len(_KAZAKH_NEGATIVE.findall(text))


def _safety_sentences(text: str, *, language: str | None = None) -> list[str]:
    return [sentence.strip().rstrip(".!?。！？").casefold()
            for sentence in re.split(r"(?<=[.!?。！？])\s+|(?<=[。！？])|\n+", _polarity_text(text))
            if sentence.strip() and (any(
                re.search(pattern, sentence, re.I)
                for name, pattern in _MARKERS.items() if name not in {"and", "or"}
            ) or _kazakh_negatives(sentence, language))]


def _concept_tokens(text: str) -> list[str] | None:
    text = re.sub(r"办理(?=住宿|登记)", "", text)
    pattern = re.compile("|".join(f"(?P<{key}>{value})" for key, value in _CONCEPTS.items()), re.I)
    tokens = []
    end = 0
    for match in pattern.finditer(text):
        if _GRAMMAR.sub("", text[end:match.start()]):
            return None
        tokens.append(match.lastgroup)
        if match.lastgroup == "book":
            tokens.append("appointment")
        # 'complete accommodation registration' retains the lodging object too.
        if match.lastgroup == "registration" and "accommodation" in match.group():
            tokens.append("lodging")
        end = match.end()
    return None if _GRAMMAR.sub("", text[end:]) else tokens


def _noun_groups(tokens: list[str]) -> tuple:
    groups = [[]]
    joins = []
    for token in tokens:
        if token in {"and", "or"}:
            joins.append(token)
            groups.append([])
        elif token not in _CONTEXT:
            groups[-1].append(token)
    return tuple(sorted(tuple(sorted(group)) for group in groups if group)), tuple(sorted(joins))


def _predicate_binding(tokens: list[str], *, condition: bool = False) -> tuple | None:
    actions = [token for token in tokens if token in _ACTIONS]
    modals = [token for token in tokens if token in _MODALS]
    if len(actions) > 1 or len(modals) > 1 or "cancellation" in tokens:
        return None
    if condition and (modals or actions != ["hold"]):
        return None
    action = actions[0] if actions else next(
        (token for token in tokens if token in {"registration", "appointment"}), None,
    )
    if action is None:
        return None
    action_at = tokens.index(action)
    modal_at = next((i for i, token in enumerate(tokens) if token in _MODALS), action_at)
    # A required action differs from requiring its completed result as an object.
    if modals and action_at < modal_at:
        return None
    predicate_at = min(action_at, modal_at)
    subjects = [token for token in tokens[:predicate_at] if token != "already"]
    objects = [
        token for token in tokens[predicate_at:] if token not in _MODALS | {action, "already"}
    ]
    # An appointment in the sole predicate slot means making an appointment.
    # The same concept following a different verb remains that verb's object.
    if not actions and action == "appointment":
        action = "book"
        objects.append("appointment")
    return (
        _noun_groups(subjects or ["you"]), action, tuple(modals), _noun_groups(objects),
        tokens.count("already"),
    )


def _structural_form(sentence: str, *, language: str | None = None) -> tuple | None:
    # Negative/ambiguous morphology stays literal. Explicit positive clauses use
    # reusable subjects/actions/objects and condition slots, not a whole-answer
    # exception. Unknown words, nested clauses and multiple predicates fail closed.
    if any(re.search(_MARKERS[key], sentence, re.I) for key in (
        "prohibition", "no_obligation", "denial", "negative_morphology",
    )) or _kazakh_negatives(sentence, language):
        return None
    conditions = []
    conditional = re.match(r"^(?:if|если|如果|若)\s*(.+?)[,，:]\s*(.+)$", sentence, re.I)
    if conditional:
        condition = _concept_tokens(conditional[1])
        binding = _predicate_binding(condition, condition=True) if condition else None
        if binding is None:
            return None
        conditions.append(("if", binding))
        sentence = conditional[2]
    for event, terms in _EVENTS.items():
        purpose = re.compile(
            rf"\bfor\s+(?:(?:the|your)\s+)?(?:{terms})|"
            rf"\bдля\s+(?:{terms})|^办理(?:{terms})(?=必须|应当|请|可以)", re.I,
        )
        conditions.extend(("purpose", event) for _ in purpose.finditer(sentence))
        sentence = purpose.sub(" ", sentence)
        tail = re.search(rf"办理(?:{terms})$", sentence)
        if tail and any(re.search(_CONCEPTS[action], sentence[:tail.start()], re.I)
                        for action in _ACTIONS - {"hold"}):
            conditions.append(("purpose", event))
            sentence = sentence[:tail.start()]
    for event, terms in _EVENTS.items():
        for relation, en, ru, zh in (
            ("after", "after", "после", "之后|以后|后"),
            ("before", "before", "до", "之前|以前|前"),
        ):
            pattern = re.compile(
                rf"\b{en}\s+(?:(?:the|your)\s+)?(?:{terms})|"
                rf"\b{ru}\s+(?:{terms})|(?:{terms})(?:{zh})", re.I,
            )
            conditions.extend((relation, event) for _ in pattern.finditer(sentence))
            sentence = pattern.sub(" ", sentence)
    units = "|".join(_UNITS.values())
    duration = re.compile(
        rf"(?:within|в течение)\s+(?P<prefix_value>\d+)\s*(?P<prefix_unit>{units})|"
        rf"(?P<suffix_value>\d+)\s*(?P<suffix_unit>{units})内", re.I,
    )
    durations = list(duration.finditer(sentence))
    if len(durations) > 1 or (durations and sum(
        condition[0] in {"before", "after"} for condition in conditions
    ) > 1):
        # Several deadline/event branches need a real relation parser. A sorted
        # list of numbers and events would silently lose each deadline's anchor.
        return None
    for match in durations:
        value = match["prefix_value"] or match["suffix_value"]
        unit = match["prefix_unit"] or match["suffix_unit"]
        name = next(key for key, pattern in _UNITS.items() if re.fullmatch(pattern, unit, re.I))
        conditions.append(("within", value, name))
    sentence = duration.sub(" ", sentence)
    tokens = _concept_tokens(sentence)
    binding = _predicate_binding(tokens) if tokens else None
    return (binding, tuple(sorted(conditions))) if binding is not None else None


def _safety_form(sentence: str, *, language: str | None = None) -> tuple:
    form = _structural_form(sentence, language=language)
    return ("structural", form) if form is not None else ("literal", sentence)


def _preserves_safety_forms(original: str, claim: str, *, language: str) -> bool:
    return Counter(_safety_form(s, language=language) for s in _safety_sentences(
        original, language=language,
    )) == Counter(
        _safety_form(s, language=language) for s in _safety_sentences(claim, language=language)
    )


def _markers(text: str, *, language: str | None = None) -> Counter[str]:
    text = _polarity_text(text)
    result = Counter()
    result["kazakh_negative_morphology"] = _kazakh_negatives(text, language)
    # Do not misread 'not required' as an obligation or 'must not' as permission.
    for name in ("prohibition", "no_obligation"):
        pattern = _MARKERS[name]
        if re.search(pattern, text):
            result[name] = len(re.findall(pattern, text))
            text = re.sub(pattern, " ", text)
    for name in ("minimum", "maximum"):
        pattern = _MARKERS[name]
        result[name] = len(re.findall(pattern, text))
        text = re.sub(pattern, " ", text)
    for name, pattern in _MARKERS.items():
        if name not in {"prohibition", "no_obligation", "minimum", "maximum"}:
            result[name] = len(re.findall(pattern, text))
    for name, pattern in _SCOPE.items():
        result["scope:" + name] = len(re.findall(pattern, text))
    return result


def _quantities(original: str, text: str, *, language: str) -> set[tuple[Decimal, str]]:
    # A calendar date's 年/日 are not duration units. The existing exact-value
    # date parser identifies only source-equal dates; it cannot exempt a new value.
    for start, end in sorted(
        protected_detail_spans(original, text, language=language), reverse=True,
    ):
        text = text[:start] + " " + text[end:]
    result = set()
    for match in _QUANTITY.finditer(text):
        unit = next(
            name for name, pattern in _UNITS.items()
            if re.fullmatch(pattern, match["unit"], re.I)
        )
        result.add((Decimal(match["value"].replace(",", ".")), unit))
    return result


def claim_preserves_details(original: str, claim: str, *, language: str) -> bool:
    if not numeric_details_match(original, claim, language=language):
        return False
    if _quantities(original, claim, language=language) != _quantities(
        original, original, language=language,
    ):
        return False
    # Word-number translation is outside this narrow gate. Do not let a missing
    # digit token conceal '24 hours' -> 'forty-eight hours'.
    if any(match.group().casefold() not in original.casefold()
           for match in _SPELLED_QUANTITY.finditer(claim)):
        return False
    return True


def claim_preserves_explicit_safety(original: str, claim: str, *, language: str) -> bool:
    return claim_preserves_details(original, claim, language=language) and (
        _markers(original, language=language) == _markers(claim, language=language)
        and _preserves_safety_forms(original, claim, language=language)
    )
