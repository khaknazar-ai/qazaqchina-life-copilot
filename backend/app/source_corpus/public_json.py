"""Bounded extraction of the verified public GOV.KZ and Adilet response schemas."""

import json
import re
from urllib.parse import parse_qs, urlsplit

from backend.app.source_corpus.extraction import MAX_RAW_BYTES, MAX_TEXT_CHARS, extract_html

_KAZAKH_LETTERS = frozenset("әғқңөұүіһ")
_SERVICE_KEYS = frozenset(
    {
        "result_description",
        "projects",
        "documents",
        "is_webel",
        "type",
        "project_id",
        "faq",
        "id",
        "similar",
        "acc_ls",
        "service_price",
        "old_cms_id",
        "zaglushki_datetime",
        "directions",
        "additional_info",
        "service_channel_availability",
        "automationtype",
        "status",
        "category_mob_ul",
        "code",
        "description",
        "video",
        "title",
        "short_title",
        "categories",
        "prosmotry_uslug",
        "service_time",
        "service_places",
        "subject_type",
        "user_types",
        "full_title",
        "instruction",
        "activities",
        "organization",
        "category",
        "view_count",
    }
)
_INSTRUCTION_KEYS = frozenset(
    {
        "projects",
        "clients",
        "additional",
        "project_id",
        "gettingmethod",
        "instruction",
        "service_method",
        "id",
        "order",
    }
)
_FAQ_KEYS = frozenset({"projects", "question", "answer", "project_id", "id"})


def extract_public_json(data: bytes, candidate: dict) -> tuple[str, str]:
    if len(data) > MAX_RAW_BYTES:
        raise ValueError("Public JSON exceeds the byte limit")
    try:
        value = json.loads(
            data.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
    except (UnicodeError, RecursionError, ValueError) as exc:
        raise ValueError("Public JSON is not a bounded valid document") from exc
    if not isinstance(value, dict):
        raise ValueError("Public JSON must be an object")
    address = candidate.get("url")
    if not isinstance(address, str) or not address.isascii() or any(c.isspace() for c in address):
        raise ValueError("Public API origin is invalid")
    url = urlsplit(address)
    schema = candidate.get("api_schema")
    identifier = str(candidate.get("expected_document_id", ""))
    language = candidate.get("expected_language")
    if (
        url.scheme != "https"
        or url.port not in {None, 443}
        or url.username
        or url.password
        or url.fragment
    ):
        raise ValueError("Public API origin is invalid")
    if schema == "adilet_document":
        if (
            not re.fullmatch(r"[A-Z][0-9]{10}", identifier)
            or url.hostname != "adilet.zan.kz"
            or url.path != f"/api/documents/by-ngr/{identifier}"
            or parse_qs(url.query, keep_blank_values=True) != {"language": [language]}
            or language not in {"rus", "kaz"}
        ):
            raise ValueError("Adilet API attribution does not match the candidate")
        document = value.get("document")
        if not isinstance(document, dict) or (
            document.get("group_number") != identifier
            or document.get("language") != language
            or document.get("has_content") is not True
            or document.get("is_stub") is not False
            or document.get("is_actual") is not True
        ):
            raise ValueError("Adilet document identity, language or active body does not match")
        title = _text(document, "title_ru")
        body = _text(document, "text_content")
        parts = [title, body]
        body_language = "ru" if language == "rus" else "kk"
        language_parts = [body]
    else:
        routes = {
            "gov_article": "/api/v1/public/content-manager/article/",
            "gov_project": "/api/v1/public/content-manager/projectdetails/",
            "gov_service": "/api/v1/public/content-manager/services/",
        }
        route = routes.get(schema)
        if (
            not re.fullmatch(r"[1-9][0-9]{0,11}", identifier)
            or url.hostname != "www.gov.kz"
            or route is None
            or url.path != route + identifier
            or url.query
            or language not in {"en", "ru", "kk"}
            or type(value.get("id")) is not int
            or str(value["id"]) != identifier
        ):
            raise ValueError("GOV.KZ API attribution does not match the candidate")
        # The verified GOV responses have no locale key. A newly declared one
        # must agree; a requested language is never proof of the returned body.
        for key in ("language", "locale", "lang"):
            if key in value and value[key] != language:
                raise ValueError("GOV.KZ declared language does not match")
        if schema == "gov_article":
            if value.get("projects") != "mfa":
                raise ValueError("GOV.KZ ministry identity does not match")
            parts = [_text(value, "title"), _text(value, "content")]
            language_parts = [parts[1]]
        elif schema == "gov_project":
            if value.get("slug") != "mfa-beijing" or value.get("projects") != "mfa-beijing":
                raise ValueError("GOV.KZ embassy identity does not match")
            parts = [
                _text(value, field)
                for field in (
                    "project_name",
                    "about_title",
                    "activities_description",
                    "contacts",
                )
            ]
            language_parts = [_text(value, "activities_description")]
        else:
            parts, language_parts = _service_parts(value)
        body_language = language
    texts = [_plain(part) for part in parts]
    text = "\n".join(part for part in texts if part.strip())
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("Public JSON text exceeds the review limit")
    _language_sanity("\n".join(_plain(part) for part in language_parts), body_language)
    return text, f"public_json:{schema}"


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Public JSON contains duplicate object fields")
        value[key] = item
    return value


def _invalid_constant(_value: str):
    raise ValueError("Public JSON contains a non-JSON number")


def _text(value: dict, key: str, *, allow_empty: bool = False) -> str:
    field = value.get(key)
    if not isinstance(field, str) or (not allow_empty and not field.strip()):
        raise ValueError("A public document text field is missing or has an unsupported shape")
    return field


def _list(value: dict, key: str, *, nonempty: bool = False) -> list:
    field = value.get(key)
    if not isinstance(field, list) or len(field) > 1000 or (nonempty and not field):
        raise ValueError("A public document collection is missing or has an unsupported shape")
    return field


def _known_object(value: object, allowed: frozenset[str]) -> dict:
    if not isinstance(value, dict) or len(value) > 100 or set(value) - allowed:
        raise ValueError("A public document object has an unreviewed shape")
    return value


def _group(value: dict, key: str, *, name: str = "name", nonempty: bool = False) -> list[str]:
    group = _known_object(value.get(key), frozenset({"items", "content_type_slug"}))
    _text(group, "content_type_slug")
    items = _list(group, "items", nonempty=nonempty)
    texts = []
    allowed = frozenset({name, "id", "source_id"})
    for item in items:
        texts.append(_text(_known_object(item, allowed), name))
    return texts


def _service_parts(value: dict) -> tuple[list[str], list[str]]:
    _known_object(value, _SERVICE_KEYS | frozenset({"language", "locale", "lang"}))
    parts = [_text(value, "full_title"), _text(value, "description", allow_empty=True)]
    language_parts = []
    instructions = _list(value, "instruction", nonempty=True)
    orders = []
    for instruction in instructions:
        instruction = _known_object(instruction, _INSTRUCTION_KEYS)
        order = instruction.get("order")
        if type(order) is not int or order < 0:
            raise ValueError("Public service instructions need an explicit order")
        orders.append(order)
    if len(orders) != len(set(orders)):
        raise ValueError("Public service instruction order is ambiguous")
    for instruction in sorted(instructions, key=lambda item: item["order"]):
        parts.append(_text(instruction, "service_method"))
        parts.extend(_group(instruction, "gettingmethod", nonempty=True))
        parts.extend(_group(instruction, "clients", nonempty=True))
        body = _text(instruction, "instruction")
        parts.extend((body, _text(instruction, "additional", allow_empty=True)))
        language_parts.append(body)
    parts.append(_text(value, "result_description"))
    for faq in _list(value, "faq"):
        faq = _known_object(faq, _FAQ_KEYS)
        parts.extend((_text(faq, "question"), _text(faq, "answer")))
    parts.extend(
        _text(value, field)
        for field in (
            "service_price",
            "service_time",
            "additional_info",
        )
    )
    parts.extend(_group(value, "service_places", nonempty=True))
    parts.extend(_group(value, "user_types", nonempty=True))
    parts.extend(_group(value, "automationtype", name="title", nonempty=True))
    # These groups are empty in the captured schema. New attachments or scope
    # data need a reviewed extractor rather than silent omission of conditions.
    for field in (
        "subject_type",
        "service_channel_availability",
        "documents",
        "acc_ls",
        "directions",
        "activities",
    ):
        if field not in value and field not in {"subject_type", "service_channel_availability"}:
            continue
        group = _known_object(value.get(field), frozenset({"items", "content_type_slug"}))
        _text(group, "content_type_slug")
        if _list(group, "items"):
            raise ValueError("Public service attachments or eligibility fields need schema review")
    organization = _known_object(
        value.get("organization"), frozenset({"items", "content_type_slug"})
    )
    _text(organization, "content_type_slug")
    organizations = _list(organization, "items", nonempty=True)
    if not any(isinstance(item, dict) and item.get("slug") == "mfa" for item in organizations):
        raise ValueError("Public service ministry identity does not match")
    for item in organizations:
        item = _known_object(item, frozenset({"id", "project_name", "shortname", "slug"}))
        parts.append(_text(item, "project_name"))
    return parts, language_parts


def _plain(value: str) -> str:
    return extract_html(value.encode("utf-8"), "text/html; charset=utf-8")[0]


def _language_sanity(text: str, expected: str) -> None:
    # A conservative script check catches default-language fallbacks. It does
    # not certify translation or replace the human language/applicability review.
    letters = [character for character in text.casefold() if character.isalpha()]
    latin = sum(character.isascii() for character in letters)
    cyrillic = sum("\u0400" <= character <= "\u04ff" for character in letters)
    kazakh = sum(character in _KAZAKH_LETTERS for character in letters)
    total = len(letters)
    if expected == "en":
        matches = latin >= 20 and latin >= total * 0.85
    elif expected == "kk":
        matches = cyrillic >= 20 and cyrillic >= total * 0.70 and kazakh >= 5
    else:
        matches = cyrillic >= 20 and cyrillic >= total * 0.70 and kazakh < cyrillic * 0.03
    if not matches:
        raise ValueError("Public document body language is ambiguous or mismatched")
