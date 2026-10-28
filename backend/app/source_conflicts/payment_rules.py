"""Extract explicit payment terms with separate funding and fee scopes.

Values come from the compared passages, not a catalog of presumed current rules.
Account failures, bank charges and different promotion programs need manual review.
"""

import re
from datetime import date
from decimal import Decimal

from backend.app.domain.enums import RiskLevel, UserScenario
from backend.app.domain.sources import SourceReference
from backend.app.source_conflicts.claims import RuleClaim
from backend.app.source_conflicts.rule_text import matches, rule_sentences

_FOREIGN_CARD = (
    r"(?:foreign|international|overseas)[- ](?:issued[- ])?(?:(?:bank|credit|debit) )?cards?"
    r"|иностранн\w*\s+(?:банковск\w*\s+)?карт\w*|международн\w*\s+карт\w*"
    r"|境外(?:银行|信用|借记)?卡|国际(?:银行|信用|借记)?卡"
    r"|шетелдік\s+(?:банк\w*\s+)?карт\w*|халықаралық\s+(?:банк\w*\s+)?карт\w*"
)
_NEGATIVE = (
    r"\b(?:cannot|can't|can not|may not|must not|can never|not permitted|"
    r"does not allow|do not allow|not supported|unsupported|does not support|do not support|"
    r"not allowed|prohibited|unavailable)\b|не\s+(?:поддержива\w*|доступ\w*|разреш\w*|"
    r"могут|можно)|нельзя|不支持|不能|不允许|不可|"
    r"рұқсат етілмейді|болмайды|қолдау көрсетілмейді|мүмкін емес"
)
_POSITIVE = (
    r"\b(?:can|may|supports?|supported|allowed|available|permitted)\b|"
    r"поддержива\w*|доступ\w*|разреш\w*|можно|могут|支持|可以|允许"
    r"|рұқсат етіледі|болады|қолдау көрсетіледі"
)
_AMBIGUOUS = (
    r"\b(?:used to|formerly|previously|rumou?rs?|incorrect|misleading|allegedly|"
    r"depending|if|unless|except|only|some cards|certain cards|selected cards|"
    r"claim that|claiming|websites say|not true|false)\b|"
    r"раньше|ранее|устарев\w*|ошибоч\w*|если|только|кроме|за\s+исключением|зависит|"
    r"以前|此前|谣言|错误|如果|仅限|除外|除非|部分卡|某些卡"
    r"|егер|бұрын|тек\b|қоспағанда|жалған"
)
_CNY = (
    r"(?:RMB|CNY|￥|¥)\s*([\d,.]+)|"
    r"(?<![\d.,-])([\d,.]+)\s*(?:RMB|CNY|yuan|юан\w*|元)"
)
_USD = (
    r"(?:USD|US\$)\s*([\d,.]+)|"
    r"(?<![\d.,-])([\d,.]+)\s*(?:USD|US dollars|доллар\w*\s+США|美元)"
)


def extract_payment_claims(source: SourceReference) -> list[RuleClaim]:
    claims: list[RuleClaim] = []
    for quote in rule_sentences(source):
        if matches(_AMBIGUOUS, quote) or not matches(_FOREIGN_CARD, quote):
            continue
        if _validity(quote) is None:
            continue
        platform = _platform(quote)
        if platform is None:
            continue
        dimensions = {"platform": platform, "funding": "international_card"}
        claims.extend(_features(source, quote, dimensions))
        claims.extend(_fees(source, quote, dimensions))
        claims.extend(_limits(source, quote, dimensions))
        claims.extend(_promotion(source, quote, dimensions))
        if len(claims) >= 24:
            break
    return claims[:24]


def _platform(quote: str) -> str | None:
    found = [
        name
        for name, pattern in (
            ("weixin_pay", r"WeChat(?:\s+Pay)?|Weixin(?:\s+Pay)?|微信(?:支付)?"),
            ("alipay", r"Alipay|Алип[еэ]й|支付宝"),
        )
        if matches(pattern, quote)
    ]
    if len(found) != 1 or matches(r"WeChat\s+Pay\s+HK|Weixin\s+Pay\s+HK|微信香港钱包", quote):
        return None
    return found[0]


def _claim(
    source: SourceReference,
    quote: str,
    rule_id: str,
    value: str,
    dimensions: dict[str, str],
) -> RuleClaim:
    valid_from, valid_until = _validity(quote)
    return RuleClaim(
        rule_id=rule_id,
        source=source,
        quote=quote,
        value=str(value),
        dimensions=dimensions,
        scenario=UserScenario.payments,
        risk_level=RiskLevel.medium,
        valid_from=valid_from,
        valid_until=valid_until,
    )


def _validity(quote: str) -> tuple[date | None, date | None] | None:
    values = []
    for pattern in (
        r"(?:effective\s+(?:from|on)|starting\s+from|действует\s+с|自)\s*(\d{4}-\d{2}-\d{2})",
        r"(?:effective\s+until|until|действует\s+до|截至)\s*(\d{4}-\d{2}-\d{2})",
    ):
        found = re.findall(pattern, quote, re.I)
        if len(found) > 1:
            return None
        try:
            values.append(date.fromisoformat(found[0]) if found else None)
        except ValueError:
            return None
    if values[0] and values[1] and values[0] > values[1]:
        return None
    return values[0], values[1]


def _features(
    source: SourceReference,
    quote: str,
    dimensions: dict[str, str],
) -> list[RuleClaim]:
    features = [
        name
        for name, pattern in (
            (
                "p2p_allowed",
                r"person[- ]to[- ]person|peer[- ]to[- ]peer|P2P|перевод\w*\s+"
                r"(?:друг\w*|между\s+людьми)|个人转账|向朋友转账|"
                r"жеке тұлғалар арасындағы аударым\w*",
            ),
            (
                "red_packet_allowed",
                r"red[- ]packets?|hongbao|красн\w*\s+конверт\w*|红包|қызыл конверт\w*",
            ),
            (
                "balance_top_up_allowed",
                r"(?:wallet|balance)\s+(?:top[- ]up|recharg\w*)|"
                r"top[- ]up\s+(?:the\s+)?(?:wallet|balance)|пополн\w*\s+(?:баланс\w*|"
                r"кошель\w*)|零钱充值|钱包充值|(?:әмиян|баланс)\w* толтыр\w*",
            ),
            (
                "linking_allowed",
                r"(?:link|add|bind)\w*\s+(?:(?:a|an|the|supported)\s+)*"
                + "(?:"
                + _FOREIGN_CARD
                + r")|привяз\w*|绑定|байланыстыр\w*",
            ),
        )
        if matches(pattern, quote)
    ]
    # Mixed features may have different polarity. Never distribute one negation to all.
    if len(features) != 1 or matches(
        r"\b(?:but|and|or|however)\b|но\s|但是|不过|remittance|汇款|және|немесе|бірақ", quote
    ):
        return []
    value = (
        "not_allowed"
        if matches(_NEGATIVE, quote)
        else ("allowed" if matches(_POSITIVE, quote) else None)
    )
    if value is None:
        return []
    if features[0] == "red_packet_allowed":
        incoming = matches(r"receiv\w*|получ\w*|收红包|接收红包|алуға|алу\b", quote)
        outgoing = matches(r"send\w*|отправ\w*|发红包|发送红包|жібер\w*", quote)
        if incoming and outgoing:
            return []
        dimensions = {
            **dimensions,
            "direction": "receive" if incoming else ("send" if outgoing else "unspecified"),
        }
    return [_claim(source, quote, "payments.foreign_card." + features[0], value, dimensions)]


def _number(pattern: str, quote: str) -> str | None:
    values = set()
    for match in re.finditer(pattern, quote, re.I):
        raw = next(value for value in match.groups() if value is not None)
        if raw.endswith("."):
            raw = raw[:-1]  # Sentence punctuation is not a fractional separator.
        if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?", raw):
            return None
        values.add(Decimal(raw.replace(",", "")))
    if len(values) != 1:
        return None
    value = values.pop()
    return format(value.normalize(), "f") if 0 <= value <= 1_000_000 else None


def _fees(
    source: SourceReference,
    quote: str,
    dimensions: dict[str, str],
) -> list[RuleClaim]:
    if not matches(r"fee|commission|сбор\w*|комисси\w*|手续费", quote):
        return []
    if matches(
        r"(?:do|does|must|may|will)\s+not\s+charg|not\s+(?:charg|appl)|"
        r"не\s+(?:взима\w*|бер[её]\w*|применя\w*)|不收取|不适用",
        quote,
    ):
        return []
    if matches(
        r"bank(?:'s)?\s+(?:fee|charge)|issuing\s+bank|exchange|FX|"
        r"комисси\w*\s+банк\w*|курс\w*|发卡行|汇率|首次|first[- ]time|promot",
        quote,
    ):
        return []
    amount = _number(_CNY, quote)
    if amount is None or not matches(
        r"single|per\s+(?:payment|transaction)|payments?\s+of|"
        r"транзакц\w*|одн\w*\s+плат[её]ж\w*|单笔",
        quote,
    ):
        return []
    scope = {
        **dimensions,
        "currency": "CNY",
        "basis": "single_transaction",
        "program": "standard",
        "customer": "all_users",
    }
    claims = []
    if matches(
        r"fee[- ]free|fees?\s+(?:are\s+)?waived|no\s+(?:service\s+)?fee|"
        r"без\s+комисси\w*|комисси\w*\s+не\s+взима\w*|免手续费|免收手续费",
        quote,
    ):
        if matches(
            r"(?:or\s+less|up\s+to|not\s+exceed|at\s+most|<=|≤)|"
            r"не\s+более|до\s+\d|不超过|以下|及以下",
            quote,
        ):
            claims.append(_claim(source, quote, "payments.fee_free_threshold_cny", amount, scope))
    percentages = re.findall(r"(?<!\d)(\d{1,2}(?:\.\d{1,2})?)\s*%", quote)
    if (
        len(percentages) == 1
        and not matches(r"\b(?:no|not)\b|не\s|不是|不收取", quote)
        and matches(r"above|over|exceed|more\s+than|свыше|более|超过", quote)
    ):
        fee_base = "unspecified"
        if matches(
            r"full\s+(?:amount|transaction)|entire\s+(?:amount|transaction)|"
            r"всю\s+сумму|полную\s+сумму|全额",
            quote,
        ):
            fee_base = "full_amount"
        elif matches(r"excess|portion\s+above|превышени\w*|超过部分", quote):
            fee_base = "excess_amount"
        rate = str(float(percentages[0])).removesuffix(".0")
        scope = {**scope, "threshold_cny": amount, "charge_base": fee_base}
        claims.append(
            _claim(
                source,
                quote,
                "payments.service_fee_percent",
                rate,
                scope,
            )
        )
        if fee_base != "unspecified":
            base_scope = {key: value for key, value in scope.items() if key != "charge_base"}
            claims.append(
                _claim(
                    source,
                    quote,
                    "payments.service_fee_base",
                    fee_base,
                    {**base_scope, "rate_percent": rate},
                )
            )
    return claims


def _limits(
    source: SourceReference,
    quote: str,
    dimensions: dict[str, str],
) -> list[RuleClaim]:
    if not matches(r"limit|cap|maximum|лимит\w*|максим\w*|限额|上限", quote):
        return []
    if matches(r"raised|increased|previous|from\s+USD|повыш\w*|раньше|提高|此前", quote):
        return []
    value = _number(_USD, quote)
    if value is None:
        return []
    bases = [
        name
        for name, pattern in (
            ("single", r"single|per\s+transaction|одн\w*\s+(?:операц\w*|плат[её]ж\w*)|单笔"),
            ("annual", r"annual|per\s+year|годов\w*|в\s+год|每年|年度"),
        )
        if matches(pattern, quote)
    ]
    if len(bases) != 1:
        return []
    verified = matches(r"identity[- ]verified|verified\s+users|верифицирован\w*|实名认证", quote)
    unverified = matches(r"unverified|not\s+verified|неверифицирован\w*|未实名", quote)
    if verified == unverified:
        return []
    scope = {
        **dimensions,
        "currency": "USD",
        "basis": bases[0],
        "identity": "verified" if verified else "unverified",
    }
    return [_claim(source, quote, "payments." + bases[0] + "_limit_usd", value, scope)]


def _promotion(
    source: SourceReference,
    quote: str,
    dimensions: dict[str, str],
) -> list[RuleClaim]:
    if not matches(r"APEC\s*(?:China\s*)?2026", quote):
        return []
    if matches(
        r"not\s+eligible|not\s+waived|no\s+waiver|не\s+(?:доступ\w*|освобожд\w*)|"
        r"不享受|不适用|不免",
        quote,
    ):
        return []
    if not matches(r"first[- ]time|首次", quote) or not matches(
        r"waiv|fee[- ]free|免手续费", quote
    ):
        return []
    if not matches(r"first|after\s+link|首次|绑定后", quote):
        return []
    scope = {
        **dimensions,
        "program": "APEC_2026_first_time",
        "customer": "first_time_users",
        "anchor": "first_eligibility",
    }
    claims = []
    days = _number(r"(\d{1,3})\s*(?:consecutive\s+)?days?|连续(\d{1,3})天", quote)
    amount = _number(_CNY, quote)
    if days is not None:
        claims.append(
            _claim(
                source,
                quote,
                "payments.promotion.duration_days",
                days,
                {**scope, "daily_cap_cny": amount or "unspecified"},
            )
        )
    if amount is not None and matches(r"per\s+day|daily|每天|每日", quote):
        claims.append(
            _claim(
                source,
                quote,
                "payments.promotion.daily_cap_cny",
                amount,
                {**scope, "duration_days": days or "unspecified"},
            )
        )
    return claims
