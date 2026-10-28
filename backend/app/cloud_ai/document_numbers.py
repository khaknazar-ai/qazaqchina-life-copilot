"""Compare explicit document numbers without changing the original document.

Only calendar dates and explicitly labeled yuan amounts have alternate formats.
Other numbers remain literal tokens. This checks values, not which fee or event
they describe; the semantic reviewer still checks that relationship.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

_DateValue = tuple[int | None, int, int]
_Value = _DateValue | Decimal | str
_NUMBER = re.compile(r"[+\-−]?\d+(?:[.,]\d+)*")
_DECIMAL = re.compile(r"[+\-−]?[0-9]{1,12}(?:[.,][0-9]{1,2})?")
_CHINESE_DATE = re.compile(
    r"(?:(?P<year>[0-9]{4})年)?(?P<month>[0-9]{1,2})月(?P<day>[0-9]{1,2})[日号]"
)
_ISO_DATE = re.compile(r"(?P<year>[0-9]{4})-(?P<month>[0-9]{1,2})-(?P<day>[0-9]{1,2})")
_DOTTED_DATE = re.compile(
    r"(?P<day>[0-9]{1,2})\.(?P<month>[0-9]{1,2})\.(?P<year>[0-9]{4})"
)
_RUSSIAN_MONTHS = {
    "январь": 1, "января": 1, "февраль": 2, "февраля": 2,
    "март": 3, "марта": 3, "апрель": 4, "апреля": 4,
    "май": 5, "мая": 5, "июнь": 6, "июня": 6,
    "июль": 7, "июля": 7, "август": 8, "августа": 8,
    "сентябрь": 9, "сентября": 9, "октябрь": 10, "октября": 10,
    "ноябрь": 11, "ноября": 11, "декабрь": 12, "декабря": 12,
}
_RUSSIAN_DATE = re.compile(
    r"(?P<day>[0-9]{1,2})\s+(?P<month>" + "|".join(_RUSSIAN_MONTHS) + r")"
    r"(?:\s+(?P<year>[0-9]{4})(?:\s*(?:года|г\.?))?)?",
    re.I,
)
_CNY_UNITS = {
    "cny", "rmb", "人民币", "元", "yuan", "yuans", "юань", "юаня", "юаней",
    "юанях", "юанями", "юаням",
}
_FOREIGN_UNITS = {
    "usd", "dollar", "dollars", "доллар", "доллара", "долларов", "美元",
    "eur", "euro", "euros", "евро", "欧元",
    "kzt", "теңге", "тенге", "gbp", "pound", "pounds", "фунт", "фунтов",
    "jpy", "yen", "йен", "иен", "日元",
    "hkd", "mop", "twd", "sgd", "aud", "cad", "chf", "nzd", "krw", "rub", "inr",
}
_CURRENCY_SYMBOLS = {"$", "€", "£", "¥", "￥", "₸"}
_UNIT_PATTERN = "|".join(
    re.escape(unit) for unit in sorted(
        _CNY_UNITS | _FOREIGN_UNITS | _CURRENCY_SYMBOLS, key=len, reverse=True,
    )
) + r"|(?-i:[A-Z]{3})"
_AMOUNT = re.compile(
    rf"(?:(?P<prefix>{_UNIT_PATTERN})\s*)?"
    r"(?P<number>[+\-−]?[0-9]+(?:[.,][0-9]+)*)"
    rf"(?:\s*(?P<suffix>{_UNIT_PATTERN}))?",
    re.I,
)


@dataclass(frozen=True)
class _Detail:
    kind: str
    value: _Value
    start: int
    end: int

    @property
    def key(self) -> tuple[str, _Value]:
        return self.kind, self.value


@dataclass(frozen=True)
class _Parsed:
    details: tuple[_Detail, ...]
    malformed: bool = False


def _is_embedded(character: str) -> bool:
    # Chinese prose normally has no spaces around dates or amounts. Letters in
    # other scripts, digits and identifier/email separators are token boundaries.
    return character in "_@.+-−" or character.isdigit() or (
        character.isalpha() and not "\u4e00" <= character <= "\u9fff"
    )


def _bounded(text: str, start: int, end: int) -> bool:
    if start > 0 and _is_embedded(text[start - 1]):
        return False
    if end == len(text):
        return True
    if text[end] == ".":
        # Permit a sentence full stop, but not another identifier/date component.
        return end + 1 == len(text) or not _is_embedded(text[end + 1])
    return not _is_embedded(text[end])


def _parse_details(text: str, *, language: str) -> _Parsed:
    details: list[_Detail] = []
    malformed = False
    patterns = [_CHINESE_DATE, _ISO_DATE, _DOTTED_DATE]
    if language == "ru":
        patterns.append(_RUSSIAN_DATE)
    for pattern in patterns:
        for match in pattern.finditer(text):
            start, end = match.span()
            if not _bounded(text, start, end) or any(
                start < existing.end and end > existing.start for existing in details
            ):
                continue
            year = int(match["year"]) if match["year"] is not None else None
            month_text = match["month"].casefold()
            month = _RUSSIAN_MONTHS[month_text] if pattern is _RUSSIAN_DATE else int(month_text)
            day = int(match["day"])
            try:
                # A leap year validates a yearless date without choosing its year.
                date(year if year is not None else 2000, month, day)
            except ValueError:
                malformed = True
                continue
            details.append(_Detail("date", (year, month, day), start, end))
    for match in _AMOUNT.finditer(text):
        units = [unit.casefold() for unit in (match["prefix"], match["suffix"]) if unit]
        start, end = match.span()
        if not units or any(
            start < existing.end and end > existing.start for existing in details
        ):
            continue
        if not _bounded(text, start, end):
            # An embedded currency/identifier token cannot fall back to a bare
            # digit match and thereby smuggle in a different currency.
            malformed = True
            continue
        if any(unit in _CNY_UNITS for unit in units) and all(
            unit in _CNY_UNITS | {"¥", "￥"} for unit in units
        ):
            if not _DECIMAL.fullmatch(match["number"]):
                # Grouping commas, mixed separators and more than two decimal
                # places are deliberately unsupported, even when repeated.
                malformed = True
                continue
            try:
                value = Decimal(match["number"].replace(",", ".").replace("−", "-"))
            except InvalidOperation:
                malformed = True
                continue
            details.append(_Detail("amount", value, start, end))
        elif any(unit in _CNY_UNITS for unit in units):
            malformed = True
        else:
            # Foreign amounts are literal only; never mask them or normalize a
            # currency conversion. A new foreign unit cannot replace source yuan.
            details.append(_Detail("foreign_amount", match.group().casefold(), start, end))
    return _Parsed(tuple(sorted(details, key=lambda detail: detail.start)), malformed)


def _outside_numbers(text: str, details: list[_Detail]) -> set[str]:
    parts: list[str] = []
    start = 0
    for detail in sorted(details, key=lambda item: item.start):
        parts.append(text[start:detail.start])
        start = detail.end
    parts.append(text[start:])
    # Separate removed spans, so adjacent identifiers cannot form a new token.
    return set(_NUMBER.findall(" ".join(parts)))


def _legacy_date_literal(source: _Parsed, text: str, detail: _Detail) -> bool:
    """Allow the old year/month/day parentheses without inventing a date year."""
    if detail.kind != "date" or not isinstance(detail.value, tuple) or detail.value[0] is not None:
        return False
    for original in source.details:
        if original.kind != "date" or not isinstance(original.value, tuple):
            continue
        year, month, day = original.value
        if year is None or (month, day) != detail.value[1:]:
            continue
        if re.match(
            rf"\s*\(\s*{year}\s*,\s+{month}\s*,\s+{day}\s*\)", text[detail.end:],
        ):
            return True
    return False


def _literal_annotations(
    original: str, text: str, source: list[_Detail], candidate: list[_Detail],
) -> list[_Detail]:
    """Keep only exact original digit annotations attached to an equal detail."""
    annotations: list[_Detail] = []
    for translated in candidate:
        for supplied in source:
            if supplied.key != translated.key:
                continue
            tokens = _NUMBER.findall(original[supplied.start:supplied.end])
            literal = r"\s*,\s+".join(re.escape(token) for token in tokens)
            match = re.match(r"\s*\(\s*" + literal + r"\s*\)", text[translated.end:])
            if match:
                annotations.append(_Detail(
                    "literal_annotation", supplied.value,
                    translated.end + match.start(), translated.end + match.end(),
                ))
                break
    return annotations


def numeric_details_match(
    original: str, text: str, *, language: str = "en", allow_omission: bool = False,
) -> bool:
    """Check source-equal date/money values and literal remaining numeric tokens.

    Actions may omit details. Complete translations must keep every amount and
    all remaining numbers, including dates rendered with the legacy digit words.
    Dates without a year stay yearless; no year or number is inferred.
    """
    source = _parse_details(original, language=language)
    candidate = _parse_details(text, language=language)
    if source.malformed or candidate.malformed:
        return False
    source_keys = {detail.key for detail in source.details}
    candidate_details = [
        detail for detail in candidate.details
        if detail.key in source_keys or not _legacy_date_literal(source, text, detail)
    ]
    candidate_keys = {detail.key for detail in candidate_details}
    if not candidate_keys <= source_keys:
        return False
    if not allow_omission and any(
        detail.kind in {"amount", "foreign_amount"} and detail.key not in candidate_keys
        for detail in source.details
    ):
        return False
    matched_source = [detail for detail in source.details if detail.key in candidate_keys]
    required = _outside_numbers(original, matched_source)
    annotations = _literal_annotations(original, text, matched_source, candidate_details)
    remaining = _outside_numbers(text, candidate_details + annotations)
    if allow_omission:
        return remaining <= required
    return required == remaining


def protected_detail_spans(
    original: str, text: str, *, language: str = "en",
) -> list[tuple[int, int]]:
    """Return only bounded date/yuan spans equal to explicit source details.

    The caller must check explicit private labels before exempting these spans
    from a generic number detector. This function does not certify text as safe.
    """
    source = _parse_details(original, language=language)
    candidate = _parse_details(text, language=language)
    if source.malformed or candidate.malformed:
        return []
    source_keys = {detail.key for detail in source.details if detail.kind in {"date", "amount"}}
    return [(detail.start, detail.end) for detail in candidate.details if detail.key in source_keys]
