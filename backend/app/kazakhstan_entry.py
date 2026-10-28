"""Direct lookup answers for the official Kazakhstan MFA visa table."""

from __future__ import annotations

import re

from backend.app.answer_quality.composer import render_grounded_answer_markdown
from backend.app.answer_quality.models import (
    GroundedAnswerDraft,
    GroundedAnswerSection,
)
from backend.app.answer_quality.policies import build_source_note
from backend.app.domain.enums import LanguageCode, RiskLevel, UserScenario
from backend.app.domain.sources import Citation, SourceReference
from backend.app.source_registry.registry import SourceRegistry

_TABLE_PREFIX = "Kazakhstan MFA visa regime: "
_SNAPSHOT_DATE = "2026-10-25"

_COUNTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "China": ("chinese", "китай", "китая", "китайский", "кнр", "қытай", "中国", "中国籍"),
    "Russian Federation": (
        "russia",
        "russian",
        "россия",
        "россии",
        "российский",
        "российской федерации",
        "рф",
        "ресей",
        "ресейлік",
        "俄罗斯",
        "俄罗斯联邦",
    ),
    "India": ("indian", "индия", "индии", "индийский", "үндістан", "印度"),
    "Italy": ("italian", "италия", "италии", "итальянский", "итальянка", "意大利"),
    "Spain": ("spanish", "испания", "испанский", "西班牙"),
    "Netherlands": ("holland", "dutch", "нидерланды", "голландия", "荷兰"),
    "Switzerland": ("swiss", "швейцария", "швейцарии", "швейцарский", "瑞士"),
    "Brazil": ("brazilian", "бразилия", "бразилец", "巴西"),
    "Mexico": ("mexican", "мексика", "мексиканец", "墨西哥"),
    "Thailand": ("thai", "таиланд", "тайланд", "таец", "泰国"),
    "Vietnam": ("vietnamese", "вьетнам", "вьетнамский", "越南"),
    "Indonesia": ("indonesian", "индонезия", "индонезийский", "印度尼西亚"),
    "Philippines": ("filipino", "филиппины", "филиппинский", "菲律宾"),
    "Nepal": ("nepalese", "непал", "непалец", "尼泊尔"),
    "Sri Lanka": ("sri lankan", "шри ланка", "шри-ланка", "斯里兰卡"),
    "Egypt": ("egyptian", "египет", "египтянин", "埃及"),
    "Saudi Arabia": (
        "saudi",
        "саудовская аравия",
        "саудовской аравии",
        "саудовский",
        "沙特阿拉伯",
    ),
    "Malaysia": ("malaysian", "малайзия", "малайзиец", "马来西亚"),
    "Singapore": ("singaporean", "сингапур", "сингапурец", "新加坡"),
    "Poland": ("polish", "польша", "поляк", "波兰"),
    "Sweden": ("swedish", "швеция", "швед", "瑞典"),
    "Norway": ("norwegian", "норвегия", "норвежец", "挪威"),
    "Ireland": ("irish", "ирландия", "ирландец", "爱尔兰"),
    "Georgia": ("georgian", "грузия", "грузин", "格鲁吉亚"),
    "Moldova": ("moldovan", "молдова", "молдавия", "摩尔多瓦"),
    "United States": ("usa", "u.s.a.", "американец", "американка", "сша", "美国"),
    "United Kingdom": ("britain", "british", "uk", "англия", "британия", "英国", "英國"),
    "Germany": ("german", "германия", "германии", "немецкий", "德国"),
    "France": ("french", "франция", "франции", "французский", "法国"),
    "Japan": ("japanese", "япония", "японии", "японский", "日本"),
    "Republic of Korea": ("south korea", "корея южная", "южная корея", "대한민국", "韩国"),
    "Turkey": ("turkey", "turkish", "турция", "турции", "түркия", "土耳其"),
    "Uzbekistan": ("узбекистан", "узбекистана", "өзбекстан", "乌兹别克斯坦"),
    "Kyrgyzstan": ("кыргызстан", "киргизия", "қырғызстан", "吉尔吉斯斯坦"),
    "Tajikistan": ("таджикистан", "тоҷикистон", "塔吉克斯坦"),
    "Azerbaijan": ("азербайджан", "әзербайжан", "阿塞拜疆"),
    "Armenia": ("армения", "армянский", "հայաստան", "亚美尼亚"),
    "Belarus": ("беларусь", "белоруссия", "белорусский", "беларусь", "白俄罗斯"),
    "Ukraine": ("украина", "украины", "украинский", "乌克兰"),
    "Mongolia": ("монголия", "монголии", "монғолия", "蒙古"),
    "Iran": ("иран", "иранский", "ایران", "伊朗"),
    "Pakistan": ("пакистан", "пакистанский", "پاکستان", "巴基斯坦"),
    "Bangladesh": ("бангладеш", "বাংলাদেশ", "孟加拉国"),
    "United Arab Emirates": ("uae", "оаэ", "эмираты", "біріккен араб әмірліктері", "阿联酋"),
    "Canada": ("canadian", "канада", "канадский", "加拿大"),
    "Australia": ("australian", "австралия", "австралии", "австралийский", "澳大利亚"),
    "New Zealand": ("new zealand", "новая зеландия", "新西兰"),
    "Hong Kong (PRC)": ("hong kong", "гонконг", "香港"),
}

_PASSPORT_ALIASES = {
    "D": ("diplomatic", "дипломат", "дипломатиялық", "外交护照", "外交護照"),
    "S": ("service passport", "official passport", "служеб", "қызметтік", "公务护照"),
    "N": ("ordinary passport", "обычный паспорт", "қарапайым паспорт", "普通护照"),
}
_CITIZENSHIP_MARKERS = (
    "citizenship",
    "nationality",
    "citizen of",
    "гражданство",
    "гражданин",
    "гражданка",
    "азаматтығым",
    "азаматтығы",
    "азаматым",
    "国籍",
    "公民",
)

_COPY = {
    "ru": {
        "passport": {
            "D": "дипломатический паспорт",
            "S": "служебный паспорт",
            "N": "обычный паспорт",
        },
        "unknown": 'Не нашёл страну гражданства в таблице МИД. Напиши её ' \
                   'официальное название; номер паспорта не нужен.',
        "missing": 'Напиши страну гражданства. Если паспорт служебный или ' \
                   'дипломатический, укажи его тип; иначе предполагаю обычный ' \
                   'паспорт.',
        "ambiguous": 'В сообщении указано несколько стран. Напиши страну именно ' \
                     'своего гражданства, чтобы я выбрал правильную строку МИД.',
        "visa": 'В таблице МИД для граждан {country} с паспортом ' \
                '«{passport}» указана виза. Снимок таблицы сделан {date}.',
        "free": 'По таблице МИД, для граждан {country} с паспортом ' \
                '«{passport}» указан безвизовый въезд до {days} дн.{scope} ' \
                'Снимок таблицы сделан {date}.',
        "arrival": 'Официальная памятка по уведомлению о прибытии (обновлена ' \
                   '05.08.2024) указывает срок 3 рабочих дня. Уведомить может ' \
                   'физическое или юридическое лицо, в том числе представитель ' \
                   'гостиницы или владелец жилья.',
        "stay_ok": 'Указанный срок поездки укладывается в лимит таблицы; это не ' \
                   'подтверждает другие условия въезда.',
        "stay_over": 'Указанный срок поездки превышает лимит из строки таблицы. ' \
                     'Нужна подходящая виза или другое основание пребывания.',
        "purpose": 'Таблица описывает визовый режим, но сама по себе не ' \
                   'разрешает работу, учёбу или проживание. Для такой цели ' \
                   'требуется соответствующая категория.',
        "evisa": 'Право на e-Visa зависит от гражданства и цели поездки; ' \
                 'требуется приглашение, одобренное уполномоченным органом. ' \
                 'По e-Visa въехать и выехать можно только через ' \
                 'международные аэропорты Казахстана, а срок пребывания и ' \
                 'цель определяет выданная виза.',
        "on_arrival": 'Таблица указывает визу по прибытии для этого типа паспорта. ' \
                      'Она не подтверждает доступность процедуры в каждом пункте ' \
                      'въезда — проверь условия поездки.',
        "conflict": 'В таблице МИД найдены разные строки для {country}. Не буду ' \
                    'выбирать одну наугад; уточни правило в официальном визовом ' \
                    'портале.',
        "facts": "Строка официальной таблицы",
        "steps": "Что учесть",
        "uncertainty": 'Это снимок опубликованной таблицы, а не гарантия допуска на ' \
                       'границе. Проверь изменения до поездки.',
        "needs_invitation": 'e-Visa выдаётся на основании приглашения, одобренного ' \
                            'уполномоченным органом.',
        "arrival_step": 'Уточни у принимающей стороны, гостиницы или хозяина жилья, ' \
                        'кто подаст уведомление о прибытии.',
    },
    "kk": {
        "passport": {
            "D": "дипломатиялық паспорт",
            "S": "қызметтік паспорт",
            "N": "қарапайым паспорт",
        },
        "unknown": 'Азаматтық еліңді СІМ кестесінен таппадым. Елдің ресми ' \
                   'атауын жаз; паспорт нөмірі қажет емес.',
        "missing": 'Азаматтық еліңді жаз. Паспорт қызметтік не дипломатиялық ' \
                   'болса, түрін көрсет; әйтпесе қарапайым паспорт деп аламын.',
        "ambiguous": 'Хабарламада бірнеше ел бар. Дұрыс кесте жолын табу үшін ' \
                     'азаматтық еліңді нақты жаз.',
        "visa": 'СІМ кестесінде {country} азаматына «{passport}» паспортымен ' \
                'виза қажет деп көрсетілген. Кесте көшірмесі {date} күні ' \
                'алынды.',
        "free": 'СІМ кестесінде {country} азаматына «{passport}» паспортымен ' \
                '{days} күнге дейін визасыз кіру көрсетілген{scope}. Кесте ' \
                'көшірмесі {date} күні алынды.',
        "arrival": 'Келгені туралы хабарлау жөніндегі ресми нұсқаулық ' \
                   '(05.08.2024 жаңартылған) 3 жұмыс күні мерзімін көрсетеді. ' \
                   'Хабарламаны жеке немесе заңды тұлға, соның ішінде қонақүй ' \
                   'өкілі не баспана иесі бере алады.',
        "stay_ok": 'Көрсетілген сапар ұзақтығы кестедегі шекке сай, бірақ бұл ' \
                   'басқа кіру шарттарын растамайды.',
        "stay_over": 'Сапар ұзақтығы кестедегі шектен асады. Сәйкес виза немесе ' \
                     'өзге болу негізі қажет.',
        "purpose": 'Кесте визалық режимді көрсетеді, бірақ жұмысқа, оқуға ' \
                   'немесе тұруға рұқсат бермейді. Мұндай мақсатқа тиісті санат ' \
                   'қажет.',
        "evisa": 'Электрондық визаның қолжетімділігі азаматтық пен сапар ' \
                 'мақсатына байланысты; уәкілетті орган мақұлдаған шақыру ' \
                 'қажет. Электрондық визамен кіру және шығу тек Қазақстанның ' \
                 'халықаралық әуежайлары арқылы рұқсат етіледі, ал болу ' \
                 'мерзімі мен сапар мақсатын берілген виза анықтайды.',
        "on_arrival": 'Кестеде осы паспорт түріне келген кезде виза алу ' \
                      'көрсетілген. Бұл барлық кіру пунктінде қолжетімді екеніне ' \
                      'кепіл емес.',
        "conflict": 'СІМ кестесінде {country} үшін әртүрлі жолдар табылды. ' \
                    'Біреуін болжап таңдамаймын; ресми визалық порталдан нақтыла.',
        "facts": "Ресми кестедегі жол",
        "steps": "Ескеретін жайттар",
        "uncertainty": 'Бұл — жарияланған кестенің көшірмесі, шекарадан өткізу ' \
                       'кепілі емес. Жол алдында өзгерістерді тексер.',
        "needs_invitation": "Электрондық визаға уәкілетті орган мақұлдаған шақыру негіз болады.",
        "arrival_step": 'Қабылдаушы тараптан, қонақүйден немесе үй иесінен келгені ' \
                        'туралы хабарламаны кім беретінін сұра.',
    },
    "zh": {
        "passport": {"D": "外交护照", "S": "公务护照", "N": "普通护照"},
        "unknown": '没有在哈萨克斯坦外交部表格中找到该国籍。请写出国籍国家的正式名称；无需提供' \
                   '护照号码。',
        "missing": "请提供国籍。若持公务或外交护照，请说明类型；否则暂按普通护照查询。",
        "ambiguous": "消息中出现多个国家。请明确护照签发国，以便匹配正确的外交部表格行。",
        "visa": '哈萨克斯坦外交部表格显示，{country}公民持{passport}需要签证。表格快照日期：{d' \
                'ate}。',
        "free": '外交部表格显示，{country}公民持{passport}可免签停留至多{days}天{scope}。表格' \
                '快照日期：{' \
                'date}。',
        "arrival": '入境通知官方说明（更新于2024年8月5日）写明期限为抵达后3个工作日。自然人或' \
                   '法人均可提交，包括酒店代表或房屋所有人。',
        "stay_ok": "计划停留时间在表格上限内，但这不代表满足其他入境条件。",
        "stay_over": "计划停留时间超过表格所列上限，需要相应签证或其他停留依据。",
        "purpose": "表格说明的是签证制度，本身不授予工作、学习或居留许可；这些目的需要对应类别。",
        "evisa": '电子签证资格取决于国籍和旅行目的，并需要主管机关批准的邀请。持电子签证入境和' \
                 '离境只能经哈萨克斯坦国际机场；停留期限和旅行' \
                 '目的以签发的签证为准。',
        "on_arrival": "表格列出此护照类型可办理落地签，但不保证每个入境口岸都能办理。",
        "conflict": '外交部表格中{country}有互相不同的记录。我不会猜选其中一条；请在官方签证门' \
                    '户确认。',
        "facts": "官方表格记录",
        "steps": "需要留意",
        "uncertainty": "这是已发布表格的快照，不是边境准入保证。出行前请查看是否有更新。",
        "needs_invitation": "电子签证以主管机关批准的邀请为基础签发。",
        "arrival_step": "向接待方、酒店或房东确认由谁提交抵达通知。",
    },
    "en": {
        "passport": {
            "D": "diplomatic passport",
            "S": "service/official passport",
            "N": "ordinary passport",
        },
        "unknown": "I couldn't match that citizenship to a country in the MFA " \
                   "table. Send the country's official name; do not send a " \
                   'passport number.',
        "missing": 'Tell me the citizenship country. If the passport is ' \
                   'diplomatic or service/official, include its type; otherwise ' \
                   'I will use an ordinary passport.',
        "ambiguous": 'Your message mentions more than one country. Tell me the ' \
                     "passport's country of citizenship so I can use the right " \
                     'MFA row.',
        "visa": 'The Kazakhstan MFA table lists a visa for a citizen of ' \
                '{country} holding a {passport}. Snapshot date: {date}.',
        "free": 'The Kazakhstan MFA table lists visa-free entry for a ' \
                'citizen of {country} holding a {passport}, for up to {days} ' \
                'days{scope}. Snapshot date: {date}.',
        "arrival": 'The official arrival-notification page (updated 2024-08-05) ' \
                   'states a three-working-day deadline. An individual or legal ' \
                   'entity may submit it, including a hotel representative or ' \
                   'housing owner.',
        "stay_ok": "Your stated trip length fits the table's limit; this does " \
                   'not confirm other entry conditions.',
        "stay_over": 'Your stated trip length exceeds the table entry. You will ' \
                     'need a suitable visa or another basis of stay.',
        "purpose": 'The table describes visa regime only. It does not itself ' \
                   'authorize work, study, or residence; those purposes need ' \
                   'the matching category.',
        "evisa": 'e-Visa eligibility depends on citizenship and travel ' \
                 'purpose, and an invitation approved by the authorized body ' \
                 'is required. Entry and exit using an e-Visa are allowed ' \
                 "only through Kazakhstan's international airports; the " \
                 'issued visa sets the permitted stay and purpose.',
        "on_arrival": 'The table lists visa on arrival for this passport type. It ' \
                      'does not confirm availability at every entry point.',
        "conflict": 'The MFA table contains different rows for {country}. I ' \
                    "won't choose one; confirm the entry in the official visa " \
                    'portal.',
        "facts": "Official table row",
        "steps": "What to consider",
        "uncertainty": 'This is a snapshot of the published table, not a guarantee ' \
                       'of border admission. Check for updates before travel.',
        "needs_invitation": 'An e-Visa is issued on the basis of an invitation approved ' \
                            'by the authorized government body.',
        "arrival_step": 'Ask the host, hotel, or housing owner who will submit the ' \
                        'arrival notification.',
    },
}


def build_kazakhstan_entry_answer(
    user_message: str,
    language: LanguageCode,
    registry: SourceRegistry,
    *,
    context_text: str = "",
) -> tuple[GroundedAnswerDraft, list[Citation], dict[str, str | None]]:
    """Answer from an exact MFA row and attach the official source passages."""
    lang = language.value if language.value in _COPY else "en"
    copy = _COPY[lang]
    combined = f"{context_text}\n{user_message}".strip()
    visa_rows = [
        source
        for source in registry.official_sources()
        if source.source_id.startswith("KZ-MFA-VISA-")
    ]
    country = _detect_country(combined, visa_rows)
    passport_code = _passport_code(combined)
    metadata: dict[str, str | None] = {
        "country": country,
        "passport_code": passport_code,
        "snapshot_date": _SNAPSHOT_DATE,
        "purpose": _purpose(combined),
    }

    selected: list[SourceReference] = []
    claims: list[tuple[str, str, str]] = []
    country_rows = (
        [source for source in visa_rows if _country_from_source(source) == country]
        if country
        else []
    )
    if not country:
        direct = (
            copy["ambiguous"] if _has_multiple_countries(combined, visa_rows) else copy["missing"]
        )
    elif not country_rows:
        direct = copy["unknown"].format(country=country)
    else:
        regimes = [_passport_regime(source, passport_code) for source in country_rows]
        unique_regimes = list(dict.fromkeys(regimes))
        if len(unique_regimes) > 1:
            direct = copy["conflict"].format(country=_display_country(country, lang))
            selected.extend(country_rows)
            claims.extend((source.source_id, direct, _row_quote(source)) for source in country_rows)
        else:
            source = country_rows[0]
            selected.append(source)
            regime = unique_regimes[0]
            passport_label = copy["passport"][passport_code]
            country_label = _display_country(country, lang)
            max_days = _max_days(regime)
            scope = _localized_scope(regime, lang)
            if _is_visa_required(regime):
                direct = copy["visa"].format(
                    country=country_label,
                    passport=passport_label,
                    date=_localized_date(lang),
                )
                claims.append(
                    (
                        source.source_id,
                        direct,
                        _row_quote(source),
                    )
                )
            elif _is_visa_free(regime) and max_days is not None:
                direct = copy["free"].format(
                    country=country_label,
                    passport=passport_label,
                    days=max_days,
                    scope=scope,
                    date=_localized_date(lang),
                )
                planned_days = _planned_stay_days(combined)
                if planned_days is not None:
                    stay_copy = copy["stay_ok"] if planned_days <= max_days else copy["stay_over"]
                    direct += " " + stay_copy
                claims.append((source.source_id, direct, _row_quote(source)))
            elif _is_visa_on_arrival(regime):
                direct = copy["on_arrival"].format(
                    country=country_label,
                    passport=passport_label,
                )
                claims.append((source.source_id, direct, _row_quote(source)))
            else:
                direct = f"{country_label}: {regime} ({passport_label})."
                claims.append((source.source_id, direct, _row_quote(source)))

            purpose = _purpose(combined)
            if purpose in {"work", "study", "residence"}:
                direct += " " + copy["purpose"]
            guide = registry.get_source_by_id("KZ-EVISA-GUIDE-001")
            if guide and (_is_visa_required(regime) or _mentions_evisa(combined)):
                selected.append(guide)
                direct += " " + copy["evisa"]
                if guide.content:
                    claims.append((guide.source_id, copy["evisa"], _evisa_quote(guide)))

            arrival = registry.get_source_by_id("KZ-ARRIVAL-NOTICE-001")
            if arrival and _mentions_arrival_notice(combined):
                selected.append(arrival)
                direct += " " + copy["arrival"]
                if arrival.content:
                    claims.append((arrival.source_id, copy["arrival"], _arrival_quote(arrival)))
            if purpose in {"work", "study", "residence"} and max_days is not None:
                direct += " " + copy["purpose"]

    arrival = registry.get_source_by_id("KZ-ARRIVAL-NOTICE-001")
    if arrival and _mentions_arrival_notice(combined) and arrival not in selected:
        selected.append(arrival)
        claims.append((arrival.source_id, copy["arrival"], _arrival_quote(arrival)))

    source_notes = [build_source_note(source) for source in selected]
    fact_sections = [
        GroundedAnswerSection(
            heading=copy["facts"],
            body=claim,
            source_ids=[source_id],
        )
        for source_id, claim, _quote in claims
    ]
    steps: list[GroundedAnswerSection] = []
    if (
        any(source.source_id == "KZ-EVISA-GUIDE-001" for source in selected)
        and country_rows
        and _is_visa_required(_passport_regime(country_rows[0], passport_code))
    ):
        steps.append(
            GroundedAnswerSection(
                heading=copy["steps"],
                body=copy["needs_invitation"],
                source_ids=["KZ-EVISA-GUIDE-001"],
            )
        )
    if any(source.source_id == "KZ-ARRIVAL-NOTICE-001" for source in selected):
        steps.append(
            GroundedAnswerSection(
                heading=copy["steps"],
                body=copy["arrival_step"],
                source_ids=["KZ-ARRIVAL-NOTICE-001"],
            )
        )
    draft = GroundedAnswerDraft(
        scenario=UserScenario.kazakhstan_entry.value,
        risk_level=RiskLevel.legal_sensitive.value,
        language=lang,
        direct_answer=direct,
        grounded_facts=fact_sections,
        recommended_steps=steps,
        uncertainty=[copy["uncertainty"]],
        source_notes=source_notes,
    )
    citations = [
        Citation(
            citation_id=f"KZ-MFA-{index}",
            source_id=source_id,
            claim=claim,
            supporting_quote=quote,
            confidence=1.0,
        )
        for index, (source_id, claim, quote) in enumerate(claims, start=1)
    ]
    metadata["source_ids"] = ",".join(source.source_id for source in selected)
    return draft, citations, metadata


def render_kazakhstan_entry_answer(draft: GroundedAnswerDraft) -> str:
    return render_grounded_answer_markdown(draft)


def _detect_country(text: str, sources: list[SourceReference]) -> str | None:
    normalized = _normalize(text)
    matches: list[tuple[int, int, str]] = []
    all_names = {_country_from_source(source) for source in sources}
    all_names.discard(None)
    for country in all_names:
        aliases = (country, *_COUNTRY_ALIASES.get(country, ()))
        for alias in aliases:
            needle = _normalize(alias)
            if not needle or not _contains(normalized, needle):
                continue
            positions = [m.start() for m in re.finditer(re.escape(needle), normalized)]
            for position in positions:
                distance = _citizenship_distance(normalized, position)
                matches.append((distance, -len(needle), country))
    if not matches:
        return None
    matches.sort()
    best_distance, best_length, best_country = matches[0]
    if len({item[2] for item in matches if (item[0], item[1]) == (best_distance, best_length)}) > 1:
        return None
    return best_country


def _has_multiple_countries(text: str, sources: list[SourceReference]) -> bool:
    normalized = _normalize(text)
    matches = set()
    for source in sources:
        country = _country_from_source(source)
        if not country:
            continue
        for alias in (country, *_COUNTRY_ALIASES.get(country, ())):
            needle = _normalize(alias)
            if needle and _contains(normalized, needle):
                matches.add(country)
                break
    return len(matches) > 1


def _citizenship_distance(text: str, position: int) -> int:
    markers = [text.rfind(marker, 0, position + 1) for marker in _CITIZENSHIP_MARKERS]
    nearest = max((index for index in markers if index >= 0), default=-1)
    return position - nearest if nearest >= 0 else 100_000 + position


def _country_from_source(source: SourceReference) -> str | None:
    return (
        source.title[len(_TABLE_PREFIX) :].strip()
        if source.title.startswith(_TABLE_PREFIX)
        else None
    )


def _passport_code(text: str) -> str:
    normalized = _normalize(text)
    for code in ("D", "S"):
        if any(_contains(normalized, _normalize(term)) for term in _PASSPORT_ALIASES[code]):
            return code
    return "N"


def _passport_regime(source: SourceReference, code: str) -> str:
    match = re.search(r"Official table row:\s*(.+)", source.content or "")
    if not match:
        return ""
    cells = [cell.strip() for cell in match.group(1).split("|")]
    return cells[{"D": 2, "S": 3, "N": 4}[code]] if len(cells) > 4 else ""


def _row_quote(source: SourceReference) -> str:
    match = re.search(r"Official table row:\s*(.+)", source.content or "")
    return match.group(1).strip() if match else (source.content or "")


def _is_visa_required(value: str) -> bool:
    return value.strip().casefold() == "visa"


def _is_visa_free(value: str) -> bool:
    return "visa-free" in value.casefold()


def _is_visa_on_arrival(value: str) -> bool:
    return "visa on the arrival" in value.casefold() or "visa on arrival" in value.casefold()


def _max_days(value: str) -> int | None:
    match = re.search(r"up to\s+(\d+)\s+days?", value, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _localized_scope(value: str, language: str) -> str:
    within = re.search(r"within\s+(\d+)\s+days?", value, re.IGNORECASE)
    effective = re.search(
        r"from\s+(\d{1,2})(?:st|nd|rd|th)\s+of\s+([A-Za-z]+),\s*(\d{4})", value, re.IGNORECASE
    )
    if within:
        days = within.group(1)
        return {
            "ru": f" в пределах {days} дней",
            "kk": f" {days} күн ішінде",
            "zh": f"，{days}天内",
            "en": f" within {days} days",
        }[language]
    if effective:
        return {
            "ru": f" (с {effective.group(1)} мая {effective.group(3)} года)",
            "kk": f" ({effective.group(3)} жылғы {effective.group(1)} мамырдан бастап)",
            "zh": f"（自{effective.group(3)}年{effective.group(1)}月起）",
            "en": f" (from {effective.group(1)} {effective.group(2)} {effective.group(3)})",
        }[language]
    return ""


def _planned_stay_days(text: str) -> int | None:
    normalized = _normalize(text)
    match = re.search(
        r"\b(\d{1,3})\s*(days?|день|дня|дней|күн|天)\b|(?<!\d)(\d{1,3})\s*天", normalized
    )
    if match:
        return int(match.group(1) or match.group(3))
    weeks = re.search(r"\b(\d{1,2})\s*(?:weeks?|недел\w*|апта|аптаға)\b", normalized)
    return int(weeks.group(1)) * 7 if weeks else None


def _purpose(text: str) -> str:
    normalized = _normalize(text)
    if any(term in normalized for term in ("work", "работ", "жұмыс", "工作")):
        return "work"
    if any(term in normalized for term in ("study", "учеб", "оқу", "学习")):
        return "study"
    if any(
        term in normalized
        for term in ("residence", "residency", "переезд", "постоянно жить", "тұруға")
    ):
        return "residence"
    return "tourism"


def _mentions_evisa(text: str) -> bool:
    normalized = _normalize(text)
    return any(
        term in normalized
        for term in (
            "e visa",
            "evisa",
            "electronic visa",
            "электронная виза",
            "电子签证",
        )
    )


def _mentions_arrival_notice(text: str) -> bool:
    normalized = _normalize(text)
    return any(
        term in normalized
        for term in (
            "arrival notification",
            "arrival notice",
            "notify arrival",
            "registration",
            "регистрация",
            "уведомлен",
            "прибыти",
            "келгені туралы хабарлау",
            "тіркеу",
            "到达通知",
            "住宿登记",
        )
    )


def _display_country(country: str, language: str) -> str:
    localized = {
        "ru": {
            "China": "Китай",
            "Russian Federation": "Россия",
            "India": "Индия",
            "United States": "США",
            "United Kingdom": "Великобритания",
            "Germany": "Германия",
            "France": "Франция",
            "Japan": "Япония",
            "Republic of Korea": "Республика Корея",
            "Turkey": "Турция",
            "Uzbekistan": "Узбекистан",
            "Kyrgyzstan": "Кыргызстан",
            "Tajikistan": "Таджикистан",
            "Azerbaijan": "Азербайджан",
            "Armenia": "Армения",
            "Belarus": "Беларусь",
            "Ukraine": "Украина",
            "Mongolia": "Монголия",
            "Iran": "Иран",
            "Pakistan": "Пакистан",
            "Canada": "Канада",
            "Australia": "Австралия",
        },
        "kk": {
            "China": "Қытай",
            "Russian Federation": "Ресей",
            "India": "Үндістан",
            "United States": "АҚШ",
            "Japan": "Жапония",
            "Turkey": "Түркия",
            "Uzbekistan": "Өзбекстан",
            "Kyrgyzstan": "Қырғызстан",
            "Tajikistan": "Тәжікстан",
            "Azerbaijan": "Әзербайжан",
            "Armenia": "Армения",
            "Belarus": "Беларусь",
            "Ukraine": "Украина",
            "Mongolia": "Моңғолия",
            "Iran": "Иран",
        },
        "zh": {
            "China": "中国",
            "Russian Federation": "俄罗斯",
            "India": "印度",
            "United States": "美国",
            "United Kingdom": "英国",
            "Germany": "德国",
            "France": "法国",
            "Japan": "日本",
            "Republic of Korea": "韩国",
            "Turkey": "土耳其",
            "Uzbekistan": "乌兹别克斯坦",
            "Kyrgyzstan": "吉尔吉斯斯坦",
            "Tajikistan": "塔吉克斯坦",
            "Azerbaijan": "阿塞拜疆",
            "Armenia": "亚美尼亚",
            "Belarus": "白俄罗斯",
            "Ukraine": "乌克兰",
            "Mongolia": "蒙古",
        },
    }
    return localized.get(language, {}).get(country, country)


def _local_date(language: str) -> str:
    return {"ru": "25.10.2026", "kk": "25.10.2026", "zh": "2026年10月25日", "en": "2026-10-25"}[
        language
    ]


def _localized_date(language: str) -> str:
    return _local_date(language)


def _evisa_quote(source: SourceReference) -> str:
    statements = (
        'Before submitting an application, a foreign citizen must ' \
        'check whether an electronic visa of the Republic of ' \
        'Kazakhstan is available for their country of citizenship ' \
        'and purpose of travel.',
        'An electronic visa is issued on the basis of an invitation ' \
        'from the inviting party approved by the authorized ' \
        'government body.',
        'Entry into and exit from the Republic of Kazakhstan using ' \
        'an e-Visa are permitted only through border crossing points ' \
        'at international airports of the Republic of Kazakhstan.',
        'The permitted duration of stay and purpose of travel are ' \
        'determined by the conditions of the issued e-Visa.',
    )
    content = source.content or ""
    return " ".join(statement for statement in statements if statement in content)


def _arrival_quote(source: SourceReference) -> str:
    statements = (
        'The Kazakhstan government information page, updated ' \
        "05.08.2024, states that notification of a foreign citizen's " \
        'arrival is carried out within 3 working days from arrival.',
        'It says an individual or legal entity, including a hotel ' \
        'representative or housing owner, can notify through the ' \
        'Visa and Migration Portal or gov.kz, or use the E-Qonaq app.',
    )
    content = source.content or ""
    return " ".join(statement for statement in statements if statement in content)


def _normalize(text: str) -> str:
    text = text.casefold().replace("ё", "е")
    return " ".join(re.sub(r"[^\w\u4e00-\u9fff]+", " ", text, flags=re.UNICODE).split())


def _contains(text: str, term: str) -> bool:
    if re.search(r"[\u4e00-\u9fff]", term):
        return term in text
    return f" {term} " in f" {text} "
