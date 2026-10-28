"""Extract narrowly scoped service rules from literal, normative passages.

These recognizers reflect recurring document and service confusion. They do not
encode which assertion is true. Missing jurisdictions, contractual conditions or
ambiguous exceptions are left for a human rather than filled from general knowledge.
"""

import re
from datetime import date

from backend.app.domain.enums import RiskLevel, UserScenario
from backend.app.domain.sources import SourceReference
from backend.app.source_conflicts.claims import RuleClaim
from backend.app.source_conflicts.rule_text import matches, normalized, rule_sentences

_MAX_CLAIMS = 8
_FOREIGN = r"\bforeign(?:ers?| nationals?| guests?| travellers?)\b|иностран\w*|外国人|外籍|境外人员"
_HOTEL = r"\bhotels?\b|гостиниц\w*|отел\w*|酒店|旅馆"
_QUALIFICATION = (
    r"\bforeign[- ]related (?:qualifications?|licen[cs]es?|certificates?)\b|"
    r"\blicen[cs]e to (?:host|accommodate|accept) foreign\w*\b|"
    r"специальн\w* лиценз\w* для иностран\w*|涉外资质|涉外资格"
)
_UNCERTAIN = (
    r"\b(?:alleged|purported|incorrect|misleading|outdated|rumou?r|formerly|previously|"
    r"used to|according to a recruiter|it is false|not true|false claim|claim that|"
    r"not prohibited|not forbidden)\b|"
    r"ранее|устарев\w*|неверн\w*|слух\w*|ошибочн\w*|раньше|не запрещено|"
    r"此前|以前|错误|谣言"
)
_COMPLEX = (
    r"\b(?:unless|except|otherwise|however|notwithstanding|but|although|instead)\b|"
    r"кроме|за исключением|однако|если не|除非|除外|但是|不过|但"
)
_TECHNICAL = (
    r"\b(?:error|failed|fails?|pending|unavailable|outage|busy|broken|timed out)\b|"
    r"ошибк\w*|не удалось|сбой|ожидани\w*|не работает|失败|错误|故障|审核中"
)
_ISO_START = re.compile(
    r"\b(?:effective from|starting from|from|since)\s+(\d{4}-\d{2}-\d{2})\b|"
    r"(?:начиная с|с)\s+(\d{4}-\d{2}-\d{2})\b|"
    r"自\s*(\d{4}-\d{2}-\d{2})(?:起)?",
    re.I,
)
_ISO_END = re.compile(
    r"\b(?:through|until|valid until)\s+(\d{4}-\d{2}-\d{2})\b|"
    r"(?:по|до)\s+(\d{4}-\d{2}-\d{2})\b|"
    r"截至\s*(\d{4}-\d{2}-\d{2})",
    re.I,
)
_ZH_START = re.compile(r"(?:自)?(\d{4})年(\d{1,2})月(\d{1,2})日起")
_ZH_END = re.compile(r"截至(\d{4})年(\d{1,2})月(\d{1,2})日")
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("january", "января"),
            ("february", "февраля"),
            ("march", "марта"),
            ("april", "апреля"),
            ("may", "мая"),
            ("june", "июня"),
            ("july", "июля"),
            ("august", "августа"),
            ("september", "сентября"),
            ("october", "октября"),
            ("november", "ноября"),
            ("december", "декабря"),
        ),
        start=1,
    )
    for name in names
}
_NAMED_EN_DATE = r"([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"
_NAMED_RU_DATE = r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})(?:\s+года)?\b"
_NAMED_START = re.compile(
    r"\b(?:effective from|starting from|from|since)\s+"
    + _NAMED_EN_DATE
    + r"|(?:начиная с|с)\s+"
    + _NAMED_RU_DATE,
    re.I,
)
_NAMED_END = re.compile(
    r"\b(?:through|until|valid until)\s+" + _NAMED_EN_DATE + r"|(?:по|до)\s+" + _NAMED_RU_DATE,
    re.I,
)


def extract_service_claims(source: SourceReference) -> list[RuleClaim]:
    """Return exact source passages with sufficient explicit applicability."""
    claims: list[RuleClaim] = []
    for quote in rule_sentences(source):
        if len(quote) > 900 or matches(_UNCERTAIN, quote) or matches(_COMPLEX, quote):
            continue
        validity = _validity(quote)
        if validity is None:
            continue
        for extractor in (
            _apostille,
            _hotel_qualification,
            _passport_verification,
            _direct_billing,
        ):
            claim = extractor(source, quote, *validity)
            if claim is not None:
                claims.append(claim)
                if len(claims) == _MAX_CLAIMS:
                    return claims
    return claims


def _validity(quote: str) -> tuple[date | None, date | None] | None:
    starts = (
        list(_ISO_START.finditer(quote))
        + list(_ZH_START.finditer(quote))
        + list(_NAMED_START.finditer(quote))
    )
    ends = (
        list(_ISO_END.finditer(quote))
        + list(_ZH_END.finditer(quote))
        + list(_NAMED_END.finditer(quote))
    )
    if len(starts) > 1 or len(ends) > 1:
        return None
    covered = {
        position for match in starts + ends for position in range(match.start(), match.end())
    }
    if any(match.start() not in covered for match in _YEAR.finditer(quote)):
        return None  # Document issuance and publication dates are not effective dates.
    try:
        start = _matched_date(starts[0]) if starts else None
        end = _matched_date(ends[0]) if ends else None
    except ValueError:
        return None
    return None if start and end and start > end else (start, end)


def _matched_date(match: re.Match[str]) -> date:
    parts = [part for part in match.groups() if part is not None]
    if len(parts) == 1:
        return date.fromisoformat(parts[0])
    if parts[0].casefold() in _MONTHS:
        return date(int(parts[2]), _MONTHS[parts[0].casefold()], int(parts[1]))
    if parts[1].casefold() in _MONTHS:
        return date(int(parts[2]), _MONTHS[parts[1].casefold()], int(parts[0]))
    return date(*map(int, parts))


def _claim(
    source: SourceReference,
    quote: str,
    rule_id: str,
    value: str,
    dimensions: dict[str, str],
    scenario: UserScenario,
    risk: RiskLevel,
    start: date | None,
    end: date | None,
) -> RuleClaim:
    return RuleClaim(
        rule_id=rule_id,
        source=source,
        quote=quote,
        value=value,
        dimensions=dimensions,
        scenario=scenario,
        risk_level=risk,
        valid_from=start,
        valid_until=end,
    )


def _apostille(
    source: SourceReference, quote: str, start: date | None, end: date | None
) -> RuleClaim | None:
    text = normalized(quote)
    if matches(r"\bnot issued\b|\bissued outside\b|выдан\w* не в|не выдан\w* в|非哈萨克斯坦", text):
        return None
    if not matches(
        r"\bwith an? apostille\b|\balready apostilled\b|\bafter (?:an? )?apostille\b|"
        r"с апостил\w*|после апостил\w*|已办理附加证明书",
        text,
    ) or matches(
        r"\bwithout an? apostille\b|\bdo not require an? apostille\b|"
        r"без апостил\w*|не требуется апостил\w*|未办理附加证明书",
        text,
    ):
        return None
    if not all(
        matches(pattern, text)
        for pattern in (
            r"\bpublic documents?\b|официальн\w* документ\w*|публичн\w* документ\w*|公文书",
            r"\b(?:issued in|issued by|issued from|kazakhstan[- ]issued)\s*kazakhstan\b|"
            r"\bkazakhstan[- ]issued\b|выдан\w* в казахстан\w*|"
            r"казахстан\w* (?:выда\w*|официальн\w* документ\w*)|哈萨克斯坦签发",
            r"\bmainland china\b|материков\w* кита\w*|中国内地",
            r"\b(?:convention[- ]covered|covered by the convention|within the convention)\b|"
            r"(?:подпада\w*|охватыва\w*)[^.。]{0,45}конвенци\w*|《公约》范围内",
            r"\bapostille\b|апостил\w*|附加证明书",
            r"\bconsular (?:legali[sz]ation|authentication)\b|консульск\w* легализац\w*|领事认证",
        )
    ):
        return None
    negative = matches(
        r"\b(?:do not|does not|no longer) require (?:additional )?consular "
        r"(?:legali[sz]ation|authentication)\b|"
        r"\bconsular (?:legali[sz]ation|authentication) is not required\b|"
        r"\bwithout (?:additional )?consular\b|"
        r"не (?:требуется|нужна) (?:дополнительная )?консульская легализация|"
        r"консульская легализация не требуется|"
        r"(?:无需|无须|不需要)(?:办理)?领事认证",
        text,
    )
    positive = matches(
        r"(?<!not )\brequire[sd]? (?:additional )?consular (?:legali[sz]ation|authentication)\b|"
        r"\b(?:must|shall) undergo (?:additional )?consular (?:legali[sz]ation|authentication)\b|"
        r"(?<!не )(?:требуется|нужна) (?:дополнительная )?консульская легализация|"
        r"консульская легализация обязательна|"
        r"(?<!无)(?<!不)需(?:办理)?领事认证|必须(?:办理)?领事认证",
        text,
    )
    if negative == positive:
        return None
    # A notarized translation or academic validation has a different purpose.
    if matches(
        r"\b(?:translations?|notari[sz]ation|degree verification|certified cop(?:y|ies))\b|"
        r"перевод\w*|нотариальн\w*|学历认证|翻译|公证",
        text,
    ):
        return None
    return _claim(
        source,
        quote,
        "apostille_consular_legalization",
        "not_required" if negative else "required",
        {
            "document_origin": "kazakhstan",
            "destination": "mainland_china",
            "document_scope": "convention_public_document",
            "apostille": "present",
            "action": "additional_consular_legalization",
        },
        UserScenario.documents,
        RiskLevel.legal_sensitive,
        start,
        end,
    )


def _hotel_qualification(
    source: SourceReference, quote: str, start: date | None, end: date | None
) -> RuleClaim | None:
    text = normalized(quote)
    if matches(r"\b(?:if|when|only|provided)\b|если|когда|только|при условии|如果|仅限|只有", text):
        return None
    if not all(matches(pattern, text) for pattern in (_HOTEL, _FOREIGN, _QUALIFICATION)):
        return None
    hotel = re.search(_HOTEL, text, re.I)
    # Require the lodging operator to be the actor, not a guest refusing a hotel.
    modality = re.search(
        r"\b(?:must|shall|should|may|can|cannot|are)\b|"
        r"вправе|могут|должны|можно|запрещено|不得|可以|必须",
        text,
        re.I,
    )
    guest = re.search(_FOREIGN, text, re.I)
    if (
        hotel is None
        or modality is None
        or guest is None
        or not (hotel.start() < modality.start() < guest.start())
    ):
        return None
    if not matches(
        r"\bbecause (?:they |hotels? )?(?:lack|have no|do not have)\b|"
        r"\bon (?:the )?grounds? (?:of|that)\b|из-за отсутств\w*|"
        r"по причине отсутств\w*|以[^.。]{0,25}(?:涉外资质|涉外资格)[^.。]{0,8}为由",
        text,
    ):
        return None
    if not matches(r"\b(?:lack|lacking|without|no|not have)\b|отсутств\w*|без\b|没有|无涉外", text):
        return None
    if matches(
        r"\b(?:full|closed|no rooms|capacity|security|identity documents?)\b|"
        r"\bwithout (?:a |a valid |valid )?passport\b|нет мест|закрыт\w*|"
        r"безопасност\w*|без паспорт\w*|身份证|没有护照|无有效证件|客满|停业",
        text,
    ):
        return None
    prohibited = matches(
        r"\b(?:must|shall|should|may) not (?:refuse|reject|turn away)\b|"
        r"\b(?:cannot|can not|mustn't) (?:refuse|reject|turn away)\b|"
        r"не (?:должны|вправе|могут) отказ\w*|запрещено отказ\w*|不得[^.。]{0,80}拒绝",
        text,
    )
    allowed = matches(
        r"\b(?:may|can|must|shall|are legally permitted to|are required to) "
        r"(?:refuse|reject|turn away)\b|"
        r"(?<!не )(?:вправе|могут|должны) отказ\w*|(?<!не )можно отказ\w*|"
        r"(?<!不)可以[^.。]{0,80}拒绝|必须[^.。]{0,80}拒绝",
        text,
    )
    if prohibited == allowed:
        return None
    return _claim(
        source,
        quote,
        "hotel_foreign_guest_qualification",
        "refusal_prohibited" if prohibited else "refusal_allowed",
        {
            "accommodation": "hotel",
            "guest": "foreign_national",
            "refusal_ground": "lack_of_foreign_related_qualification",
        },
        UserScenario.housing,
        RiskLevel.legal_sensitive,
        start,
        end,
    )


def _passport_verification(
    source: SourceReference, quote: str, start: date | None, end: date | None
) -> RuleClaim | None:
    text = normalized(quote)
    if not all(
        matches(pattern, text)
        for pattern in (
            r"(?<![a-z0-9])12306(?![a-z0-9])",
            r"\bforeign passports?\b|иностранн\w* паспорт\w*|外国护照|外籍护照",
            r"\b(?:identity|passport) verification\b|"
            r"\bverify (?:their |a |the )?(?:foreign )?passport\b|"
            r"провер\w* (?:личност\w*|паспорт\w*)|верификац\w* паспорт\w*|身份核验|护照核验",
        )
    ) or matches(_TECHNICAL, text):
        return None
    if matches(
        r"\b(?:email|e-mail|phone|qr code|boarding|gate|refund|payment)\b|"
        r"почт\w*|телефон\w*|посадк\w*|оплат\w*|邮箱|二维码|检票|付款",
        text,
    ):
        return None
    if matches(r"\bif\b|\bprovided\b|если|若|如果", text):
        return None
    if matches(
        r"\b(?:online|station)\s+(?:for|when|during|with)\b|"
        r"онлайн\s+(?:для|при)|(?:вокзал\w*|станци\w*)\s+для",
        text,
    ):
        return None
    station_only = matches(
        r"\bonly (?:be )?(?:completed|done|performed|available|possible)?\s*"
        r"(?:in person )?at (?:a |the )?(?:railway |train )?station\b|"
        r"\b(?:cannot|can not|must not) (?:be )?(?:completed|done|performed) online\b|"
        r"\bonline[^.。]{0,35}(?:impossible|not possible)\b|"
        r"только[^.。]{0,40}(?:вокзал\w*|станци\w*)|невозможн\w* онлайн|"
        r"не (?:доступна|может быть)[^.。]{0,40}онлайн|"
        r"只能[^.。]{0,40}(?:车站|火车站)|不(?:能|可以)[^.。]{0,40}(?:在线|线上|网上)",
        text,
    )
    online = matches(
        r"\b(?:can|may) (?:be )?(?:completed|done|performed|verified) online\b|"
        r"\bonline (?:identity |passport )?verification (?:is )?(?:available|permitted|possible)\b|"
        r"(?<!не )(?:можно|возможно|доступна|может быть)[^.。]{0,40}онлайн|"
        r"(?<!不)(?:可以|可)[^.。]{0,40}(?:在线|线上|网上)[^.。]{0,40}(?:核验|验证|完成)",
        text,
    )
    if station_only == online:
        return None
    return _claim(
        source,
        quote,
        "railway_foreign_passport_verification",
        "station_only" if station_only else "online_available",
        {"operator": "12306", "document": "foreign_passport", "action": "identity_verification"},
        UserScenario.transport,
        RiskLevel.medium,
        start,
        end,
    )


def _direct_billing(
    source: SourceReference, quote: str, start: date | None, end: date | None
) -> RuleClaim | None:
    text = normalized(quote)
    facility = _facility_scope(quote)
    department = _department_scope(quote)
    if facility is None or department is None:
        return None
    if not all(
        matches(pattern, text)
        for pattern in (
            r"\b(?:participating|contracted|partner|signed) (?:commercial |health )*"
            r"(?:insurers?|insurance plans?)\b|"
            r"(?:страховщик\w*|страхов\w* компани\w*)[^.。]{0,40}(?:договор\w*|партнер\w*)|"
            r"(?:签约|合作)[^.。]{0,20}(?:商保|商业保险|保险公司|保险机构)",
            r"\bdirect (?:billing|settlement)\b|прям\w* расчет\w*|прям\w* оплат\w*|直付|直接结算",
        )
    ):
        return None
    if matches(
        r"\b(?:reimbursement|deductible|copay|co-pay|preauthorization|prior authorization|"
        r"inpatient deposit)\b|"
        r"возмещени\w*|франшиз\w*|доплат\w*|предварительн\w* согласован\w*|报销|自付|押金|预授权",
        text,
    ):
        return None
    if matches(r"\b(?:if|unless|only after)\b|если|только после|如果|除非", text):
        return None
    negative = matches(
        r"\b(?:does not|do not|cannot|can not|never) (?:offer|provide|support|accept|arrange) "
        r"direct (?:billing|settlement)\b|"
        r"\bdirect (?:billing|settlement) (?:is )?(?:not available|unavailable)\b|"
        r"не (?:предоставляет|поддерживает) прям\w* (?:расчет\w*|оплат\w*)|"
        r"прям\w* (?:расчет\w*|оплат\w*) не доступ\w*|"
        r"不(?:提供|支持|接受)[^，,。;；]{0,30}(?:直付|直接结算)|无法[^.。]{0,15}直付",
        text,
    )
    positive = matches(
        r"(?<!not )\b(?:offers?|provides?|supports?|accepts?|arranges?) "
        r"direct (?:billing|settlement)\b|"
        r"\bdirect (?:billing|settlement) (?:is )?available\b|"
        r"(?<!не )(?:предоставля\w*|поддержива\w*) прям\w* (?:расчет\w*|оплат\w*)|"
        r"прям\w* (?:расчет\w*|оплат\w*) доступ\w*|"
        r"(?<!不)(?:提供|支持|可享受|可以享受)[^，,。;；]{0,30}(?:直付|直接结算)",
        text,
    )
    if negative == positive:
        return None
    if matches(
        r"\b(?:outpatient|inpatient|emergency|ward)\b|амбулатор\w*|стационар\w*|"
        r"экстренн\w*|门诊|住院|急诊",
        text,
    ):
        return None  # A service-specific contract needs additional structured conditions.
    plan = re.search(r"\bplan\s+([a-z][a-z0-9_-]{0,40})\s*[.!。]?$", text)
    if matches(r"\bplans?\s+(?!for\b)|полис\w*|тариф\w*|计划|保险产品", text) and plan is None:
        return None  # Free-form or translated plan names are not silently collapsed.
    # Do not merge an explicitly named plan with an unnamed participating plan.
    named_contract = re.search(
        r'\b(?:insurer|insurance company)\s+["“]([^"”]{2,80})["”]|'
        r'(?:страховщик|страховая компания|сақтандыру компаниясы)\s+[«"]([^»"]{2,80})[»"]|'
        r'保险公司[“"]([^”"]{2,80})[”"]',
        text,
    )
    insurer_names = re.findall(r"\b(cigna|bupa|aetna|allianz|msh|ping an)\b", text)
    if named_contract:
        name = next(value for value in named_contract.groups() if value)
        insurer_names.append(normalized(name))
    if len(set(insurer_names)) > 1:
        return None
    if matches(r"\b(?:including|named|called|issued by|provided by)\b|например|名为|包括", text):
        # Unknown insurer names require a verified contract identifier, not a wildcard.
        if not insurer_names:
            return None
    if (
        matches(
            r"\b(?:participating|contracted|partner|signed) (?:commercial |health )*"
            r"insurers?\s+(?!including\b|under\b)[a-z]",
            text,
        )
        and named_contract is None
    ):
        return None
    insurer_name = insurer_names[0] if insurer_names else "participating"
    contract = f"{insurer_name}:{plan.group(1) if plan else 'commercial'}"
    return _claim(
        source,
        quote,
        "hospital_commercial_insurance_direct_billing",
        "unavailable" if negative else "available",
        {
            "facility": facility,
            "department": department,
            "contract": contract,
            "action": "direct_billing",
        },
        UserScenario.medical,
        RiskLevel.medical_sensitive,
        start,
        end,
    )


def _facility_scope(quote: str) -> str | None:
    if matches(
        r"\bpumch\b|\bpeking union medical college hospital\b|北京协和医院|"
        r"пекинск\w* объединенн\w* медицинск\w*",
        quote,
    ):
        return "pumch"
    english = re.findall(
        r"\b[A-Z][A-Za-z'-]*(?: [A-Z][A-Za-z'-]*){0,7} (?:Hospital|Medical Center)\b",
        quote,
    )
    labelled = re.findall(
        r'(?:hospital|facility|госпиталь|больница|аурухана)\s+[«"“]([^»"”]{2,100})[»"”]',
        quote,
        re.I,
    )
    chinese = re.findall(r"[\u4e00-\u9fff]{2,16}(?:医院|医疗中心)(?=国际|的国际|[，,])", quote)
    names = {normalized(value) for value in english + labelled + chinese}
    return next(iter(names)) if len(names) == 1 else None


def _department_scope(quote: str) -> str | None:
    if matches(
        r"\binternational medical department\b|\bimd\b|"
        r"международн\w* медицинск\w* отделени\w*|国际医疗部|协和国际部|"
        r"халықаралық медициналық бөлім\w*",
        quote,
    ):
        return "international_medical_department"
    departments = re.findall(
        r"(?:Hospital|Medical Center)[, ]+"
        r"([A-Z][A-Za-z'-]*(?: [A-Z][A-Za-z'-]*){0,2} Department)\b",
        quote,
    )
    named = re.findall(r'(?:department|отделение|бөлім)\s+[«"“]([^»"”]{2,80})[»"”]', quote, re.I)
    values = {normalized(value) for value in departments + named}
    return next(iter(values)) if len(values) == 1 else None
