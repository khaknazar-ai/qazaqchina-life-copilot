"""Conservative city continuity from a user's message, never source evidence."""

import re

_CITIES = {
    "Shanghai": r"shanghai|шанха(?:й|е|я)|上海",
    "Beijing": r"beijing|пекин(?:е|а)?|北京",
    "Hangzhou": r"hangzhou|ханчжоу|杭州",
    "Guangzhou": r"guangzhou|гуанчжоу|广州",
}


def message_city(text: str) -> str | None:
    """Accept one named location with an explicit in/в/在 marker; otherwise abstain."""
    normalized = text.casefold()
    if re.search(r"\b(?:если|или|либо|if|or)\b|或者|可能|不在|\b(?:не|not)\s+(?:в|in)\b",
                 normalized):
        return None
    mentioned = [
        city for city, names in _CITIES.items()
        if re.search(r"(?<![a-zа-яё])(?:" + names + r")(?![a-zа-яё])", normalized)
    ]
    if len(mentioned) != 1:
        return None
    city = mentioned[0]
    names = _CITIES[city]
    located = re.search(r"\b(?:в|во|in)\s+(?:" + names + r")(?![a-zа-яё])", normalized)
    chinese = re.search(r"在\s*(?:" + names + r")", normalized)
    return city if located or chinese else None
