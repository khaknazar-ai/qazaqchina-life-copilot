import hashlib
import re
from html import unescape
from html.parser import HTMLParser


class _PreviewHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized = tag.casefold()
        if normalized in {"script", "style", "noscript", "svg", "nav"}:
            self._skip_depth += 1
        if normalized == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in {"script", "style", "noscript", "svg", "nav"} and self._skip_depth:
            self._skip_depth -= 1
        if normalized == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = _normalize_whitespace(data)
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
            return
        if self._skip_depth == 0:
            self.text_parts.append(text)


def extract_title_from_html(html: str) -> str | None:
    parser = _PreviewHTMLParser()
    parser.feed(html)
    title = _normalize_whitespace(" ".join(parser.title_parts))
    return title or None


def extract_text_preview_from_html(html: str, max_chars: int = 1200) -> str:
    parser = _PreviewHTMLParser()
    parser.feed(html)
    text = _normalize_whitespace(" ".join(parser.text_parts))
    if not text:
        text = _normalize_whitespace(_strip_tags(html))
    return text[:max_chars]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def decode_response_bytes(data: bytes, content_type: str | None = None) -> str:
    encoding = _charset_from_content_type(content_type) or "utf-8"
    try:
        return data.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        return data.decode("utf-8", errors="replace")


def _charset_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    for part in content_type.split(";"):
        key, _, value = part.strip().partition("=")
        if key.casefold() == "charset" and value:
            return value.strip("\"'")
    return None


def _strip_tags(html: str) -> str:
    return unescape(re.sub(r"<[^>]+>", " ", html))


def _normalize_whitespace(value: str) -> str:
    return " ".join(unescape(value).split())
