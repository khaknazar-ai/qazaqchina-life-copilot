"""Bounded full-document extraction; originals and derived text have separate hashes."""

import hashlib
import re
from html.parser import HTMLParser

from backend.app.memory.redaction import redact_sensitive_text
from backend.app.moderation.checks import detect_prompt_injection
from backend.app.privacy.patterns import LABELED_ID_PATTERN, SECRET_PATTERNS
from backend.app.url_fetcher.extractor import decode_response_bytes

MAX_RAW_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 500_000
_BLOCK_TAGS = {"p", "div", "section", "article", "main", "li", "h1", "h2", "h3", "br", "tr"}
_SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form"}
_ARTICLE_MARKERS = re.compile(r"(?:TRS_Editor|article[-_]?body|article[-_]?content|正文)", re.I)
_INJECTION = ("忽略之前的指令", "泄露系统提示", "игнорируй предыдущие инструкции")


def bytes_hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def text_hash(value: str) -> str:
    return bytes_hash(value.encode("utf-8"))


class FullTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool]] = []
        self.parts: list[str] = []
        self.article_parts: list[str] = []
        self.article_seen = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        marker = " ".join(str(attributes.get(key, "")) for key in ("id", "class"))
        skip = tag in _SKIP_TAGS or bool(self.stack and self.stack[-1][1])
        article = tag in {"article", "main"} or bool(_ARTICLE_MARKERS.search(marker))
        article = article or bool(self.stack and self.stack[-1][2])
        if not skip and article:
            self.article_seen = True
        if tag in _BLOCK_TAGS:
            self._append("\n", skip, article)
        if tag not in {"br", "img", "meta", "link", "input", "hr", "source", "wbr"}:
            self.stack.append((tag, skip, article))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                _, skip, article = self.stack[index]
                if tag in _BLOCK_TAGS:
                    self._append("\n", skip, article)
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        skip = bool(self.stack and self.stack[-1][1])
        article = bool(self.stack and self.stack[-1][2])
        self._append(data, skip, article)

    def _append(self, value: str, skip: bool, article: bool) -> None:
        if skip:
            return
        self.parts.append(value)
        if article:
            self.article_parts.append(value)

    def text(self) -> str:
        parts = self.article_parts if self.article_seen else self.parts
        return "\n".join(
            line for raw in "".join(parts).splitlines() if (line := " ".join(raw.split()))
        )


def extract_html(data: bytes, content_type: str | None = None) -> tuple[str, str]:
    decoded = decode_response_bytes(data, content_type)
    # Some official HTML declares GB2312 only in a meta element.
    if "\ufffd" in decoded:
        meta = re.search(rb"charset\s*=\s*[\"']?([\w-]+)", data[:8192], re.I)
        if meta:
            try:
                decoded = data.decode(meta.group(1).decode("ascii"), errors="strict")
            except (UnicodeError, LookupError):
                pass
    parser = FullTextParser()
    parser.feed(decoded)
    return parser.text(), "html_article" if parser.article_seen else "html_full_visible_text"


def assess_text(text: str) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not text.strip() or len(text.strip()) < 200:
        blockers.append("body_missing_or_application_shell")
    if len(text) > MAX_TEXT_CHARS:
        blockers.append("text_exceeds_review_limit")
    if "\ufffd" in text or "\x00" in text:
        blockers.append("encoding_or_binary_text")
    normalized = " ".join(text.casefold().split())
    if detect_prompt_injection(text) or any(term in normalized for term in _INJECTION):
        blockers.append("prompt_injection")
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        blockers.append("secret_like_value")
    if LABELED_ID_PATTERN.search(text):
        blockers.append("private_identity_value")
    derived, redactions = redact_sensitive_text(text)
    if redactions:
        warnings.append("contacts_or_identifier_like_values_redacted_in_derived_text")
    # Broad PII heuristics can mistake legal references for IDs. Reviewers see the
    # original and must verify each redaction; redacted values never enter retrieval.
    return derived, blockers, warnings
