"""Offline checks for source-bounded Kazakhstan visa document answers."""

import pytest

from backend.app.domain.enums import LanguageCode
from backend.app.domain.sources import SourceReference
from backend.app.kazakhstan_consular_documents import (
    build_kazakhstan_consular_document_answer,
)
from backend.app.kazakhstan_entry import _detect_country
from backend.app.memory.service import SessionMemoryService
from backend.app.schemas.chat import ChatRequest
from backend.app.services.chat_service import ChatService
from backend.app.source_conflicts import ConflictResolutionService
from backend.app.source_registry.registry import SourceRegistry


@pytest.fixture(scope="module")
def registry() -> SourceRegistry:
    return SourceRegistry.from_data_dir()


@pytest.mark.parametrize(
    ("category", "language"),
    [
        ("B10", "ru"),
        ("C9", "kk"),
        ("B8", "zh"),
        ("B2", "en"),
        ("C3", "ru"),
        ("C5", "kk"),
        ("C10", "zh"),
    ],
)
def test_consular_category_returns_official_document_answer(
    registry: SourceRegistry,
    category: str,
    language: str,
) -> None:
    result = build_kazakhstan_consular_document_answer(
        f"What documents are needed for visa {category}?",
        LanguageCode(language),
        registry,
    )

    assert result is not None
    draft, citations, lookup = result
    assert lookup["category"] == category
    assert draft.risk_level == "legal_sensitive"
    assert citations
    assert all(registry.get_source_by_id(item.source_id) is not None for item in citations)
    assert lookup["snapshot_date"] == "2026-10-26"


@pytest.mark.parametrize("language", ["ru", "kk", "zh", "en"])
def test_b10_answer_explains_its_limited_scope_in_every_language(
    registry: SourceRegistry,
    language: str,
) -> None:
    result = build_kazakhstan_consular_document_answer(
        "What documents for B10?", LanguageCode(language), registry,
    )

    assert result is not None
    draft, citations, _lookup = result
    assert any(item.source_id == "KZ-FOREIGNER-BEIJING-B10-SCOPE-001" for item in citations)
    assert any(
        item.source_id == "KZ-FOREIGNER-BEIJING-CONSULAR-DOCUMENTS-001"
        for item in citations
    )
    assert len(draft.grounded_facts) == 2


def test_tourist_evisa_question_uses_national_guide(registry: SourceRegistry) -> None:
    result = build_kazakhstan_consular_document_answer(
        "What documents do I need for a tourist e-Visa?", LanguageCode.en, registry,
    )

    assert result is not None
    draft, citations, lookup = result
    assert lookup["intent"] == "consular_documents_tourist_evisa"
    assert {item.source_id for item in citations} == {"KZ-FOREIGNER-EVISA-CATEGORIES-001"}
    assert "invitation" in draft.direct_answer.lower()
    assert "international airports" in draft.direct_answer.lower()


def test_business_documents_without_category_asks_b2_or_c5(registry: SourceRegistry) -> None:
    result = build_kazakhstan_consular_document_answer(
        "What documents do I need for business?", LanguageCode.en, registry,
    )

    assert result is not None
    draft, _citations, lookup = result
    assert lookup["intent"] == "consular_documents_business_clarify"
    assert "B2" in draft.direct_answer
    assert "C5" in draft.direct_answer


def test_document_followup_reuses_category_from_user_context(registry: SourceRegistry) -> None:
    result = build_kazakhstan_consular_document_answer(
        "And what documents?",
        LanguageCode.en,
        registry,
        context_text="user: I am applying for a C3 work visa",
    )

    assert result is not None
    _draft, _citations, lookup = result
    assert lookup["category"] == "C3"


def test_tourist_evisa_documents_merge_country_specific_mfa_row(registry: SourceRegistry) -> None:
    response = ChatService(
        source_registry=registry,
        memory_service=SessionMemoryService(),
    ).create_response(ChatRequest(
        user_message="What documents for tourist e-Visa as a citizen of Australia?",
        preferred_language="en",
    ))

    source_ids = {citation.source_id for citation in response.citations}
    assert response.scenario.value == "kazakhstan_entry"
    assert response.risk_level.value == "legal_sensitive"
    assert any(source_id.startswith("KZ-MFA-VISA-") for source_id in source_ids)
    assert "KZ-FOREIGNER-EVISA-CATEGORIES-001" in source_ids
    assert "citizen of Australia" in response.answer
    assert "invitation" in response.answer.lower()
    assert response.metadata["kazakhstan_entry_lookup"]["intent"] == (
        "consular_documents_tourist_evisa_with_visa_regime"
    )


def test_chinese_tourist_visa_answer_is_not_blocked_by_other_countries_rows(
    registry: SourceRegistry,
) -> None:
    conflicts = ConflictResolutionService()
    try:
        response = ChatService(
            source_registry=registry,
            source_conflict_service=conflicts,
            memory_service=SessionMemoryService(),
        ).create_response(ChatRequest(
            user_message=(
                "Я гражданин Китая с обычным паспортом. Еду в Казахстан на 10 дней "
                "как турист. Нужна ли виза?"
            ),
            preferred_language="ru",
        ))

        assert response.scenario.value == "kazakhstan_entry"
        assert "безвизов" in response.answer.casefold()
        assert any(item.source_id == "KZ-MFA-VISA-077" for item in response.citations)
        assert response.metadata["source_conflict_detection"]["input_source_count"] == 1
        assert response.metadata["source_publication_gate"]["status"] == "passed"
    finally:
        conflicts.close()


def test_non_document_question_is_not_captured(registry: SourceRegistry) -> None:
    assert build_kazakhstan_consular_document_answer(
        "Can I travel for tourism?", LanguageCode.en, registry,
    ) is None


@pytest.mark.parametrize(
    ("country", "alias"),
    [
        ("Saudi Arabia", "saudi"),
        ("Saudi Arabia", "саудовский"),
        ("Italy", "итальянка"),
        ("Italy", "итальянский"),
        ("Switzerland", "швейцарский"),
        ("Singapore", "сингапурец"),
        ("Thailand", "таец"),
        ("Indonesia", "индонезийский"),
        ("Malaysia", "малайзиец"),
        ("Philippines", "филиппинский"),
        ("Vietnam", "вьетнамский"),
        ("Brazil", "бразилец"),
        ("Mexico", "мексиканец"),
    ],
)
def test_country_aliases_survive_dictionary_merging(country: str, alias: str) -> None:
    source = SourceReference(
        source_id="visa-row",
        title=f"Kazakhstan MFA visa regime: {country}",
        source_type="official",
        trust_level="level_1_official",
    )

    assert _detect_country(alias, [source]) == country
