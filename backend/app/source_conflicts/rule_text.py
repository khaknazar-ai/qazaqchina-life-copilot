"""Bounded exact passages shared by topic-specific claim extractors."""

import re
from collections.abc import Iterator

from backend.app.domain.sources import SourceReference

MAX_RULE_SOURCE_CHARS = 40_000
MAX_RULE_QUOTE_CHARS = 900
_SENTENCE = re.compile(r".*?(?:[!?。！？]|\.(?=\s|$)|[\r\n]+|$)", re.S)
_EXPERIENCE = re.compile(
    r"\b(?:I|my|our|we)\b|\b(?:friend|recruiter|agent)\s+(?:said|told)\b|"
    r"\b(?:was|were)\s+(?:refused|rejected|unable)\b|"
    r"\b(?:rumou?rs?|allegedly|might|maybe|possibly|apparently)\b|"
    r"(?<!\w)(?:я|мне|нам|нас|мой|наши|возможно|говорят)(?!\w)|"
    r"(?:我的|我们|我被|据说|听说|可能|менің|бізге|мүмкін)",
    re.I,
)
_CONTEXT_LIMIT = re.compile(
    r"\b(?:if|unless|except|exceptions?|provided that|subject to|incorrect|false|"
    r"misleading|formerly|previously|used to|only|lower limit|non-residents)\b|"
    r"если|только|кроме|исключени\w*|при\s+услови\w*|ошибоч\w*|неверн\w*|ранее|"
    r"如果|仅限|除非|除外|例外|错误|此前|以前|条件是",
    re.I,
)


def rule_sentences(source: SourceReference) -> Iterator[str]:
    content = source.content or ""
    if len(content) > MAX_RULE_SOURCE_CHARS:
        return
    bounded = content
    sentences = list(_SENTENCE.finditer(bounded))
    for index, match in enumerate(sentences):
        quote = match.group().strip()
        if not quote or len(quote) > MAX_RULE_QUOTE_CHARS:
            continue
        if len(content) > len(bounded) and match.end() == len(bounded):
            continue
        if "?" in quote or "？" in quote or _EXPERIENCE.search(quote):
            continue
        limited = False
        for neighbor_index in (index - 1, index + 1):
            if not 0 <= neighbor_index < len(sentences):
                continue
            neighbor = sentences[neighbor_index]
            gap_start = min(match.end(), neighbor.end())
            gap_end = max(match.start(), neighbor.start())
            if re.search(r"\r?\n\s*\r?\n", content[gap_start:gap_end]):
                continue
            if _CONTEXT_LIMIT.search(neighbor.group()):
                limited = True
                break
        if limited:
            continue
        yield quote


def normalized(quote: str) -> str:
    return " ".join(quote.casefold().split())


def matches(pattern: str, quote: str) -> bool:
    return re.search(pattern, quote, re.I) is not None
