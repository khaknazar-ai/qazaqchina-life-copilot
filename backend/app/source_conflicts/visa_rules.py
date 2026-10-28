"""Extract explicit immigration claims with matching documents and policy scopes.

These recognizers suggest passages for review. They neither encode current legal
rules nor decide whether an activity or an individual is legally eligible.
"""

import re
from datetime import date

from backend.app.domain.enums import RiskLevel, UserScenario
from backend.app.domain.sources import SourceReference
from backend.app.source_conflicts.claims import RuleClaim
from backend.app.source_conflicts.rule_text import matches, rule_sentences

_CHINA = r"\b(?:china|chinese)\b|кита[йяею]|中国|қытай"
_VISA = r"\bvisas?\b|виз\w*|签证|виза"
_FREE = r"\bvisa[- ]free\b|\bvisa (?:waiver|exemption)\b|безвиз\w*|免签|визасыз"
_FOREIGN = r"\bforeign(?:ers?| nationals?| students?)\b|иностран\w*|外国人|外国留学生|шетелдік"
_STUDENT = r"\bstudents?\b|студент\w*|留学生|学生|студент"
_RP = r"\b(?:student[- ]type|study[- ]type|student|study) residence permits?\b|"
_RP += r"\bresidence permits? (?:for|of) (?:study|students?)\b|"
_RP += r"студенческ\w*\s+(?:вид\w*\s+на\s+жительств\w*|внж)|学习(?:类)?居留(?:许可|证件)"
_RP += r"|студенттік тұру рұқсат\w*"
_OFF_CAMPUS = r"\boff[- ]campus\b|\boutside (?:the )?(?:school|university)\b|"
_OFF_CAMPUS += r"вне\s+(?:кампуса|университета|вуза)|校外"
_OFF_CAMPUS += r"|кампус сыртындағы|университеттен тыс"
_INTERNSHIP = r"\binternships?\b|\bwork[- ]study\b|стажиров\w*|实习|勤工助学|тағылымдама\w*"
_AMBIGUOUS = (
    r"\b(?:if|unless|except|exceptions?|otherwise|rumou?rs?|outdated|previously|"
    r"formerly|incorrect|misleading|allegedly|some|certain|may sometimes)\b|"
    r"\b(?:used to|subject to|provided that|no longer)\b|"
    r"если|кроме|исключени\w*|ранее|устарев\w*|слух\w*|неверн\w*|при\s+условии|"
    r"如果|除非|除外|豁免|此前|以前|谣言|据说|错误|例外|егер|бұрын"
)
_NEGATIVE_REQUIRED = (
    r"\b(?:not required|not necessary|not needed|no .*?required|need not|"
    r"do not need|does not need|do(?:es)? not require|"
    r"without (?:any )?(?:need|requirement))\b|"
    r"не\s+(?:требуется|нужно|нужна|нужны|обязан\w*|долж\w*)|"
    r"без\s+(?:одобрения|согласования|отметки)|无需|无须|不需要|不必|қажет емес"
)
_REQUIRED = (
    r"\b(?:must|shall|required|requires?|need(?:s)? to|have to|necessary)\b|"
    r"обязан\w*|долж\w*|необходимо|требуется|нужно|应当|必须|需要|需|须|қажет"
)
_ALLOWED = (
    r"\b(?:can|may|allowed|permitted|accepted|valid|equivalent)\b|"
    r"разреш\w*|мож\w*|可以|允许|有效|рұқсат"
)
_NOT_ALLOWED = (
    r"\b(?:cannot|can't|not (?:allowed|permitted|accepted|valid)|prohibited|"
    r"may not|must not|shall not|does not (?:allow|permit|apply)|do not (?:allow|permit))\b|"
    r"не\s+(?:разреш\w*|допуска\w*|мож\w*)|запрещ\w*|нельзя|不能|不得|不允许|禁止|"
    r"рұқсат етілмейді|тыйым салынған"
)
_NATIONALITIES = {
    "kazakhstan": r"\b(?:kazakhstani?|kazakhstan) (?:citizens?|nationals?|passport holders?)\b|"
    r"граждан\w*\s+казахстан\w*|(?:哈萨克斯坦|哈萨克)公民|қазақстан\w*\s+азамат\w*",
    "united_kingdom": r"\b(?:british|uk|united kingdom) "
    r"(?:citizens?|nationals?|passport holders?)\b|"
    r"граждан\w*\s+великобритани\w*|英国公民",
    "australia": r"\baustralian (?:citizens?|nationals?|passport holders?)\b|"
    r"граждан\w*\s+австрали\w*|澳大利亚公民",
    "china": r"\bchinese (?:citizens?|nationals?|passport holders?)\b|граждан\w*\s+китая|中国公民",
}
_DATES_FROM = re.compile(
    r"(?:effective\s+(?:from|on)|действует\s+с|自)\s*(\d{4}-\d{2}-\d{2})", re.I
)
_DATES_UNTIL = re.compile(
    r"(?:effective\s+until|until|действует\s+до|至)\s*(\d{4}-\d{2}-\d{2})", re.I
)


def extract_visa_claims(source: SourceReference) -> list[RuleClaim]:
    """Normalize assertions only when the relevant policy and action are explicit."""
    claims: list[RuleClaim] = []
    for quote in rule_sentences(source):
        if len(quote) > 900 or not _mainland_scope(source, quote):
            continue
        if _ambiguous_context(source, quote):
            continue
        period = _period(quote)
        if period is None:
            continue
        claims.extend(_visa_fields(source, quote, period))
        claims.extend(_visa_free(source, quote, period))
        claims.extend(_student_internships(source, quote, period))
        claims.extend(_permit_deadlines(source, quote, period))
        claims.extend(_registration(source, quote, period))
        if len(claims) >= 32:
            return claims[:32]
    return claims


def _mainland_scope(source: SourceReference, quote: str) -> bool:
    text = f"{source.title} {quote}"
    if not matches(_CHINA, text):
        return False
    if matches(
        r"\b(?:agreement|treaty)\s+with\s+(?!china\b)|"
        r"соглашени\w*\s+с\s+(?!кита)|与(?!中国).*?免签协定",
        quote,
    ):
        return False
    return not matches(
        r"hong kong|maca[ou]|香港|澳门|гонконг|макао|"
        r"\bin (?:kazakhstan|australia|the uk|united kingdom)\b|"
        r"в\s+казахстане|в\s+австралии|в\s+великобритании|在哈萨克斯坦",
        quote,
    )


def _ambiguous_context(source: SourceReference, quote: str) -> bool:
    # rule_sentences already keeps adjacent exception/condition statements attached.
    return quote not in (source.content or "") or matches(_AMBIGUOUS, quote)


def _period(quote: str) -> tuple[date | None, date | None] | None:
    start_match, end_match = _DATES_FROM.search(quote), _DATES_UNTIL.search(quote)
    try:
        start = date.fromisoformat(start_match[1]) if start_match else None
        end = date.fromisoformat(end_match[1]) if end_match else None
    except ValueError:
        return None
    if start and end and start > end:
        return None
    return start, end


def _claim(
    source: SourceReference,
    quote: str,
    rule_id: str,
    value: str,
    dimensions: dict[str, str],
    period: tuple[date | None, date | None],
    *,
    scenario: UserScenario = UserScenario.documents,
    risk: RiskLevel = RiskLevel.legal_sensitive,
) -> RuleClaim:
    return RuleClaim(
        source=source,
        quote=quote,
        rule_id=rule_id,
        value=value,
        dimensions={"jurisdiction": "china_mainland", **dimensions},
        scenario=scenario,
        risk_level=risk,
        valid_from=period[0],
        valid_until=period[1],
    )


def _required(quote: str) -> str | None:
    if matches(r"\b(?:must|shall) not\b|不得", quote):
        return None
    negative = matches(_NEGATIVE_REQUIRED, quote)
    remainder = re.sub(_NEGATIVE_REQUIRED, "", quote, flags=re.I)
    if negative and matches(_REQUIRED, remainder):
        return None  # Mixed obligations need separate, correctly attached clauses.
    if negative:
        return "not_required"
    if matches(_REQUIRED, quote):
        return "required"
    return None


def _allowed(quote: str) -> str | None:
    negative = matches(_NOT_ALLOWED, quote)
    remainder = re.sub(_NOT_ALLOWED, "", quote, flags=re.I)
    if negative and matches(_ALLOWED, remainder):
        return None
    if negative:
        return "not_allowed"
    if matches(_ALLOWED, quote):
        return "allowed"
    return None


def _visa_fields(
    source: SourceReference, quote: str, period: tuple[date | None, date | None]
) -> list[RuleClaim]:
    if not (matches(_VISA, quote) or matches(_VISA, source.title)) or matches(_FREE, quote):
        return []
    if matches(r"residence permit|вид\w*\s+на\s+жительств\w*|居留(?:许可|证件)", quote):
        return []
    if matches(r"\bnot\b|не\s+означает|并非|不是", quote):
        return []
    claims = []
    dims = {"document": "entry_visa", "population": "visa_holder"}
    if matches(r"enter before|въехать до|入境有效期|入境截止日期", quote):
        entry = matches(
            r"(?:last|latest) (?:permitted )?(?:entry date|date .*?enter)|"
            r"used for entering|valid for enter|date.*?(?:may|can).*?enter|"
            r"(?:последн\w*|крайн\w*).*?дат\w*.*?въезд|"
            r"(?:入境有效期|入境截止日期).*?(?:入境日期|可以入境|可入境|最后入境)",
            quote,
        )
        departure = matches(
            r"(?:last|latest) (?:permitted )?(?:departure date|date .*?leave)|"
            r"must (?:leave|depart)|долж\w*.*?(?:выехать|покинуть)|"
            r"(?:последн\w*|крайн\w*).*?дат\w*.*?выезд|必须离境|离境截止日期",
            quote,
        )
        if entry != departure:
            claims.append(
                _claim(
                    source,
                    quote,
                    "visa.enter_before_meaning",
                    "last_entry_date" if entry else "last_departure_date",
                    dims,
                    period,
                )
            )
    if matches(
        r"duration (?:of|for|of each) stay|stay (?:duration|period)|"
        r"срок\w*\s+пребывания|停留(?:期限|期|时间)",
        quote,
    ):
        next_day = matches(
            r"(?:from|on|starting).*?(?:next day|day after).*?entry|"
            r"со следующего дня.*?въезд|入境(?:的)?次日|入境后第二天",
            quote,
        )
        entry_day = matches(
            r"(?:from|on|starting).*?(?:the )?(?:day|date) of entry|"
            r"со дня въезда|с даты въезда|自入境(?:当日|之日)|入境当天",
            quote,
        )
        if next_day != entry_day:
            claims.append(
                _claim(
                    source,
                    quote,
                    "visa.stay_count_anchor",
                    "next_day_after_entry" if next_day else "entry_day",
                    dims,
                    period,
                )
            )
    return claims


def _visa_free_scope(quote: str) -> dict[str, str] | None:
    nationalities = [name for name, pattern in _NATIONALITIES.items() if matches(pattern, quote)]
    if len(nationalities) != 1:
        return None
    bilateral = matches(
        r"\bbilateral\b|mutual visa (?:exemption|waiver) agreement|"
        r"двусторон\w*|соглашени\w*.*?взаимн\w*|双边|互免签证协定",
        quote,
    )
    unilateral = matches(r"\bunilateral\b|односторон\w*|单方面|单边", quote)
    if bilateral == unilateral:
        return None
    if matches(r"diplomatic|service passport|дипломатическ\w*|служебн\w*|外交护照|公务护照", quote):
        return None
    document = (
        "ordinary_passport"
        if matches(
            r"ordinary passports?|обычн\w*\s+паспорт\w*|общегражданск\w*\s+паспорт\w*|普通护照",
            quote,
        )
        else "unspecified_passport"
    )
    return {
        "nationality": nationalities[0],
        "entry_policy": "bilateral" if bilateral else "unilateral",
        "document": document,
    }


def _number(pattern: str, quote: str) -> str | None:
    found = list(re.finditer(pattern, quote, re.I))
    values = {next(item for item in match.groups() if item is not None) for match in found}
    return next(iter(values)) if len(values) == 1 else None


def _visa_free(
    source: SourceReference, quote: str, period: tuple[date | None, date | None]
) -> list[RuleClaim]:
    if not matches(_FREE, quote):
        return []
    scope = _visa_free_scope(quote)
    if scope is None:
        return []
    claims = []
    numeric_denial = matches(
        r"\bnot\s+(?:(?:a|the|one)\s+)?(?:single stay|cumulative stay|total stay|\d)|"
        r"\b(?:not|never)\s+(?:have|has|receive|receives)\b|"
        r"не\s+составляет|не\s+равен|不是|并非",
        quote,
    )
    days = _number(
        r"(?:single stay|per entry|each (?:entry|stay|visit))[^.;。]{0,45}?(\d{1,3})\s*days?\b|"
        r"(\d{1,3})\s*days?\s+(?:per|for each)\s+(?:entry|stay|visit)\b|"
        r"(?:одн\w*\s+пребывани\w*|кажд\w*\s+въезд\w*)[^.;。]{0,45}?(\d{1,3})\s*дн\w*|"
        r"单次停留(?:不超过|最多|为)?\s*(\d{1,3})\s*(?:日|天)",
        quote,
    )
    window = _number(
        r"(?:every|within|in|per)\s+(?:a\s+)?(?:rolling\s+)?(\d{1,3})\s*days?\b|"
        r"(?:в\s+течение|за)\s*(\d{1,3})\s*дн\w*|每\s*(\d{1,3})\s*(?:日|天)",
        quote,
    )
    cumulative = _number(
        r"(?:cumulative|total|aggregate)[^.;。]{0,45}?(\d{1,3})\s*days?\b|"
        r"(?:суммарн\w*|совокупн\w*)[^.;。]{0,45}?(\d{1,3})\s*дн\w*|"
        r"累计停留(?:不超过|最多|为)?\s*(\d{1,3})\s*(?:日|天)",
        quote,
    )
    unlimited = matches(
        r"no (?:restriction|limit).*?(?:cumulative|total|aggregate).*?(?:stay|days)|"
        r"(?:суммарн\w*|совокупн\w*).*?не ограничен\w*|累计停留.*?不限",
        quote,
    )
    if days is not None and not numeric_denial:
        claims.append(
            _claim(
                source,
                quote,
                "visa_free.single_stay_days",
                days,
                {**scope, "measure": "single_entry_stay"},
                period,
                scenario=UserScenario.tourism,
            )
        )
    if window is not None and (cumulative is not None or unlimited) and not numeric_denial:
        claims.append(
            _claim(
                source,
                quote,
                "visa_free.cumulative_stay_days",
                "unlimited" if unlimited else cumulative,
                {**scope, "measure": "cumulative_stay", "window_days": window},
                period,
                scenario=UserScenario.tourism,
            )
        )
        claims.append(
            _claim(
                source,
                quote,
                "visa_free.rolling_window_days",
                window,
                {**scope, "measure": "rolling_window"},
                period,
                scenario=UserScenario.tourism,
            )
        )
    if matches(
        r"\b(?:employment|employed|paid local work|local employment)\b|"
        r"трудоустройств\w*|оплачиваем\w*\s+работ\w*|就业|受雇|有偿工作",
        quote,
    ):
        permission = _allowed(quote)
        if permission:
            claims.append(
                _claim(
                    source,
                    quote,
                    "visa_free.employment_allowed",
                    permission,
                    {**scope, "activity": "local_employment"},
                    period,
                    scenario=UserScenario.work,
                    risk=RiskLevel.work_status_sensitive,
                )
            )
    return claims


def _student_internships(
    source: SourceReference, quote: str, period: tuple[date | None, date | None]
) -> list[RuleClaim]:
    if not all(matches(pattern, quote) for pattern in (_STUDENT, _RP, _OFF_CAMPUS, _INTERNSHIP)):
        return []
    if matches(r"\bX2\b|\bon[- ]campus\b|в\s+кампусе|校内", quote):
        return []
    obligation = _required(quote)
    if obligation is None:
        return []
    unpaid = matches(r"\bunpaid\b|неоплачиваем\w*|без оплаты|无薪|无偿", quote)
    paid = matches(r"\bpaid\b|(?<!не)оплачиваем\w*|有薪|有偿", quote)
    if unpaid and paid:
        return []
    internship = matches(r"\binternships?\b|стажиров\w*|实习|тағылымдама\w*", quote)
    work_study = matches(r"\bwork[- ]study\b|勤工助学", quote)
    activity = "off_campus_internship" if internship else "off_campus_work_study"
    if internship and work_study:
        activity = "off_campus_internship_and_work_study"
    scope = {
        "document": "student_residence_permit",
        "population": "foreign_student",
        "activity": activity,
        "compensation": "unpaid" if unpaid else ("paid" if paid else "unspecified"),
    }
    claims = []
    university = matches(
        r"(?:university|school) (?:approval|permission|consent)|"
        r"(?:approval|permission|consent) (?:of|from|by) (?:the )?(?:school|university)|"
        r"(?:одобрени\w*|согласи\w*|разрешени\w*)\s+(?:университет\w*|вуза|школ\w*)|"
        r"学校(?:批准|同意)|大学(?:批准|同意)|университеттің келісімі|университет келісімі",
        quote,
    )
    endorsement = matches(r"\b(?:endorsement|remarks?|annotation)\b|отметк\w*|加注|注明", quote)
    if university:
        claims.append(
            _claim(
                source,
                quote,
                "student.off_campus.university_approval",
                obligation,
                scope,
                period,
                scenario=UserScenario.study,
                risk=RiskLevel.work_status_sensitive,
            )
        )
    if endorsement:
        claims.append(
            _claim(
                source,
                quote,
                "student.off_campus.residence_endorsement",
                obligation,
                scope,
                period,
                scenario=UserScenario.study,
                risk=RiskLevel.work_status_sensitive,
            )
        )
    return claims


def _permit_deadlines(
    source: SourceReference, quote: str, period: tuple[date | None, date | None]
) -> list[RuleClaim]:
    if _required(quote) != "required":
        return []
    residence = matches(
        r"\bresidence permits?\b|вид\w*\s+на\s+жительств\w*|\bвнж\b|居留(?:许可|证件)", quote
    )
    application = matches(r"\b(?:apply|application|submit|file)\b|подать|заявлени\w*|申请", quote)
    if not application:
        return []
    claims = []
    after = _number(
        r"\bwithin\s+(\d{1,3})\s*days?\s+(?:after|from)\s+(?:the date of )?(?:entry|arrival)|"
        r"в\s+течение\s+(\d{1,3})\s*дн\w*\s+(?:после|со дня)\s+въезд\w*|"
        r"(?:自)?入境(?:之日)?起?\s*(\d{1,3})\s*(?:日|天)内",
        quote,
    )
    visa_types = re.findall(r"(?<![A-Za-z0-9])(?:D|J1|Q1|S1|X1|X2|Z)(?![A-Za-z0-9])", quote)
    if residence and after and len(set(visa_types)) == 1:
        claims.append(
            _claim(
                source,
                quote,
                "residence_application.after_entry_days",
                after,
                {
                    "document": visa_types[0].upper(),
                    "action": "residence_application",
                    "clock": "after_entry",
                },
                period,
            )
        )
    before = _number(
        r"(\d{1,3})\s*days?\s+(?:before|prior to).*?(?:expiry|expiration)|"
        r"за\s*(\d{1,3})\s*дн\w*\s+до\s+(?:истечени\w*|окончани\w*)|"
        r"(?:有效期)?(?:届满|到期|期满)前\s*(\d{1,3})\s*(?:日|天)",
        quote,
    )
    if before and matches(
        r"\b(?:extension|extend|renewal|renew)\b|продлен\w*|延长|延期|续期", quote
    ):
        visa = matches(_VISA, quote)
        if residence == visa:
            return claims
        if visa and not matches(
            r"permitted stay|duration of (?:each )?stay|stay expiry|stay expiration|"
            r"срок\w*\s+пребыван\w*|停留期",
            quote,
        ):
            return claims  # Entry validity and permitted-stay expiry are different clocks.
        document = "residence_permit" if residence else "entry_visa"
        rule = (
            "residence_extension.before_expiry_days"
            if residence
            else "visa_extension.before_expiry_days"
        )
        clock = "before_residence_expiry" if residence else "before_permitted_stay_expiry"
        claims.append(
            _claim(
                source,
                quote,
                rule,
                before,
                {"document": document, "action": "extension_application", "clock": clock},
                period,
            )
        )
    return claims


def _registration(
    source: SourceReference, quote: str, period: tuple[date | None, date | None]
) -> list[RuleClaim]:
    if not matches(
        r"\b(?:accommodation|residence) registration\b|регистрац\w*\s+прожив\w*|住宿登记", quote
    ):
        return []
    if not matches(_FOREIGN, quote):
        return []
    private = matches(
        r"\b(?:non[- ]hotel|private (?:homes?|residences?)|domiciles other than hotels)\b|"
        r"(?:вне|не в)\s+(?:гостиниц\w*|отел\w*)|частн\w*\s+жиль\w*|旅馆以外|酒店以外|私人住宅",
        quote,
    )
    if not private:
        return []
    scope = {
        "population": "foreign_student" if matches(_STUDENT, quote) else "foreigner",
        "accommodation": "non_hotel",
    }
    claims = []
    obligation = _required(quote)
    repeat = matches(
        r"re[- ]registration|register again|repeat (?:accommodation )?registration|"
        r"повторн\w*\s+регистрац\w*|重新登记|再次登记",
        quote,
    )
    online = matches(r"\bonline\b|онлайн|在线|网上", quote)
    if repeat:
        same_home = matches(
            r"\bsame habitual (?:home|residence)\b|"
            r"той же.*?постоянн\w*.*?(?:квартир\w*|жиль\w*)|同一经常居住地",
            quote,
        )
        valid_same_permit = matches(
            r"\b(?:valid same|same valid) residence permit\b|"
            r"тем же действующим.*?(?:внж|видом на жительство)|同一有效居留(?:许可|证件)",
            quote,
        )
        returning = matches(r"\breturn(?:ing)?\b|возвращ\w*|返回", quote)
        domestic = matches(r"\bdomestic travel\b|поездк\w*\s+по\s+китаю|国内旅行|境内旅行", quote)
        abroad = matches(
            r"\b(?:abroad|international travel|outside china)\b|"
            r"из-за границы|из за границы|境外旅行|国外旅行",
            quote,
        )
        travel = "domestic" if domestic else ("international" if abroad else "unspecified")
        if domestic and abroad:
            return claims
        if same_home and valid_same_permit and returning and obligation:
            claims.append(
                _claim(
                    source,
                    quote,
                    "accommodation.repeat_registration_required",
                    obligation,
                    {
                        **scope,
                        "home": "same_habitual_home",
                        "document": "same_valid_residence_permit",
                        "event": "return_after_travel",
                        "travel": travel,
                    },
                    period,
                    scenario=UserScenario.housing,
                )
            )
    elif online:
        accepted = _allowed(quote)
        if accepted and matches(
            r"legal (?:effect|validity)|legally (?:valid|accepted)|"
            r"юридическ\w*\s+сил\w*|法律效力",
            quote,
        ):
            claims.append(
                _claim(
                    source,
                    quote,
                    "accommodation.online_registration_accepted",
                    accepted,
                    {**scope, "channel": "online", "measure": "legal_effect"},
                    period,
                    scenario=UserScenario.housing,
                )
            )
    elif obligation and not matches(
        r"residence permit|вид\w*\s+на\s+жительств\w*|\bвнж\b|居留(?:许可|证件)",
        quote,
    ):
        if matches(
            r"change of address|changed address|different (?:home|address)|"
            r"short daytime|daytime visits?|short visits?|return(?:ing)?|"
            r"\b(?:personally|themselves|by themselves|in person)\b|"
            r"смен\w*\s+адрес\w*|возвращ\w*|дневн\w*\s+визит\w*|"
            r"лично|самостоятельно|地址变更|变更住址|白天访问|返回|亲自|自行",
            quote,
        ):
            return claims
        arrival = matches(r"\barrival\b|прибыт\w*|抵达|到达", quote)
        claims.append(
            _claim(
                source,
                quote,
                "accommodation.registration_required",
                obligation,
                {**scope, "event": "arrival" if arrival else "unspecified"},
                period,
                scenario=UserScenario.housing,
            )
        )
    return claims
