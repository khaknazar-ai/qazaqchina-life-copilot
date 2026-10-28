from pydantic import BaseModel, Field


class ExpandedQuery(BaseModel):
    query: str
    reason: str
    weight: float = 1.0
    language: str | None = None
    scenario: str | None = None


class QueryExpansionResult(BaseModel):
    original_query: str
    domain: str
    expanded_queries: list[ExpandedQuery]
    warnings: list[str] = Field(default_factory=list)


_SCENARIO_HINTS: dict[str, list[str]] = {
    "passport_document_loss": [
        "passport loss",
        "emergency document",
        "embassy",
        "consulate",
        "police report",
        "exit-entry",
    ],
    "visa_overstay_registration": [
        "visa extension",
        "residence permit",
        "overstay",
        "registration",
        "exit-entry administration",
    ],
    "work_contract_status": [
        "labor contract",
        "work permit",
        "employer",
        "legal work status",
        "labor bureau",
    ],
    "medical_hospital": [
        "hospital registration",
        "insurance",
        "emergency",
        "medical records",
    ],
    "payment_scam": [
        "payment fraud",
        "Alipay",
        "WeChat Pay",
        "bank card",
        "report scam",
    ],
    "study_university": [
        "university registration",
        "dormitory",
        "student office",
        "residence registration",
    ],
    "housing_registration": [
        "accommodation registration",
        "police station",
        "landlord",
        "temporary residence",
    ],
    "emergency": [
        "emergency contact",
        "official help",
        "police report",
        "hospital",
        "consulate",
    ],
    "general_life": [
        "China life",
        "practical checklist",
        "official guidance",
        "local registration",
    ],
}

_MULTILINGUAL_HINTS: dict[str, dict[str, list[str]]] = {
    "passport_document_loss": {
        "zh": [
            "\u62a4\u7167\u9057\u5931",
            "\u65c5\u884c\u8bc1",
            "\u6d3e\u51fa\u6240",
        ],
        "ru": [
            "\u043f\u0430\u0441\u043f\u043e\u0440\u0442",
            "\u043a\u043e\u043d\u0441\u0443\u043b",
        ],
        "kk": [
            "\u043f\u0430\u0441\u043f\u043e\u0440\u0442",
            "\u043a\u043e\u043d\u0441\u0443\u043b",
        ],
    },
    "visa_overstay_registration": {
        "zh": [
            "\u7b7e\u8bc1\u5ef6\u671f",
            "\u5c45\u7559\u8bb8\u53ef",
            "\u51fa\u5165\u5883",
        ],
        "ru": [
            "\u0432\u0438\u0437\u0430",
            "\u0412\u041d\u0416",
            "\u043f\u0440\u043e\u0441\u0440\u043e\u0447\u043a\u0430",
        ],
        "kk": [
            "\u0432\u0438\u0437\u0430",
            "\u0440\u04b1\u049b\u0441\u0430\u0442",
            "\u0442\u0456\u0440\u043a\u0435\u0443",
        ],
    },
    "work_contract_status": {
        "zh": [
            "\u5de5\u4f5c\u8bb8\u53ef",
            "\u52b3\u52a8\u5408\u540c",
            "\u96c7\u4e3b",
        ],
        "ru": [
            "\u0442\u0440\u0443\u0434",
            "\u0440\u0430\u0431\u043e\u0442\u0430",
        ],
        "kk": [
            "\u0436\u04b1\u043c\u044b\u0441",
            "\u0448\u0430\u0440\u0442",
        ],
    },
    "medical_hospital": {
        "zh": [
            "\u533b\u9662\u6302\u53f7",
            "\u533b\u7597\u4fdd\u9669",
            "\u6025\u8bca",
        ],
        "ru": [
            "\u0431\u043e\u043b\u044c\u043d\u0438\u0446\u0430",
            "\u0441\u0442\u0440\u0430\u0445\u043e\u0432\u043a\u0430",
            "\u0441\u043a\u043e\u0440\u0430\u044f",
        ],
        "kk": [
            "\u0430\u0443\u0440\u0443\u0445\u0430\u043d\u0430",
            "\u0441\u0430\u049b\u0442\u0430\u043d\u0434\u044b\u0440\u0443",
            "\u0436\u0435\u0434\u0435\u043b",
        ],
    },
    "payment_scam": {
        "zh": [
            "\u652f\u4ed8\u8bc8\u9a97",
            "\u652f\u4ed8\u5b9d",
            "\u5fae\u4fe1\u652f\u4ed8",
        ],
        "ru": [
            "\u043c\u043e\u0448\u0435\u043d\u043d\u0438\u043a",
            "Alipay",
            "WeChat Pay",
        ],
        "kk": [
            "\u0430\u043b\u0430\u044f\u049b",
            "Alipay",
            "WeChat Pay",
        ],
    },
    "study_university": {
        "zh": [
            "\u5927\u5b66\u6ce8\u518c",
            "\u7559\u5b66\u751f",
            "\u5bbf\u820d",
        ],
        "ru": [
            "\u0443\u043d\u0438\u0432\u0435\u0440\u0441\u0438\u0442\u0435\u0442",
            "\u043e\u0431\u0449\u0435\u0436\u0438\u0442\u0438\u0435",
            "\u043e\u0444\u0438\u0441",
        ],
        "kk": [
            "\u0443\u043d\u0438\u0432\u0435\u0440\u0441\u0438\u0442\u0435\u0442",
            "\u0436\u0430\u0442\u0430\u049b\u0445\u0430\u043d\u0430",
            "\u043a\u0435\u04a3\u0441\u0435",
        ],
    },
    "housing_registration": {
        "zh": [
            "\u4f4f\u5bbf\u767b\u8bb0",
            "\u623f\u4e1c",
            "\u6d3e\u51fa\u6240",
        ],
        "ru": [
            "\u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044f",
            "\u0430\u0440\u0435\u043d\u0434\u0430",
        ],
        "kk": [
            "\u0442\u04b1\u0440\u0493\u044b\u043d",
            "\u043f\u04d9\u0442\u0435\u0440",
        ],
    },
}

_LANGUAGE_ALIASES = {
    "chinese": "zh",
    "cn": "zh",
    "mandarin": "zh",
    "russian": "ru",
    "kazakh": "kk",
}


def normalize_query_text(text: str) -> str:
    return " ".join(text.split()).strip()


def scenario_keyword_hints(domain: str) -> list[str]:
    return list(_SCENARIO_HINTS.get(domain, _SCENARIO_HINTS["general_life"]))


def multilingual_keyword_hints(domain: str, language: str | None = None) -> list[str]:
    if language is None:
        return []

    normalized_language = _LANGUAGE_ALIASES.get(language.casefold(), language.casefold())
    return list(_MULTILINGUAL_HINTS.get(domain, {}).get(normalized_language, []))


def expand_retrieval_query(
    user_message: str,
    scenario: str | None = None,
    risk_level: str | None = None,
    language: str | None = None,
) -> QueryExpansionResult:
    from backend.app.retrieval.planner import classify_retrieval_domain

    original_query = normalize_query_text(user_message)
    domain = classify_retrieval_domain(original_query, scenario)
    expanded_queries: list[ExpandedQuery] = []

    base_query = original_query or "China life official guidance"
    expanded_queries.append(
        ExpandedQuery(
            query=base_query,
            reason="original_query",
            weight=1.0,
            language=language,
            scenario=scenario or domain,
        )
    )

    scenario_terms = scenario_keyword_hints(domain)
    if scenario_terms:
        expanded_queries.append(
            ExpandedQuery(
                query=_join_unique_terms([base_query, *scenario_terms]),
                reason=f"scenario_keyword_hints:{domain}",
                weight=0.9,
                language=language,
                scenario=scenario or domain,
            )
        )

    if _is_sensitive_risk(risk_level):
        expanded_queries.append(
            ExpandedQuery(
                query=_join_unique_terms(
                    [
                        base_query,
                        "official source",
                        "curated guide",
                        *scenario_terms[:4],
                    ]
                ),
                reason="high_risk_official_source_coverage",
                weight=0.95,
                language=language,
                scenario=scenario or domain,
            )
        )

    language_terms = multilingual_keyword_hints(domain, language)
    if language_terms:
        expanded_queries.append(
            ExpandedQuery(
                query=_join_unique_terms([base_query, *language_terms]),
                reason=f"multilingual_keyword_hints:{language}",
                weight=0.75,
                language=language,
                scenario=scenario or domain,
            )
        )

    return QueryExpansionResult(
        original_query=original_query,
        domain=domain,
        expanded_queries=_dedupe_expanded_queries(expanded_queries),
    )


def expanded_queries_to_strings(
    result: QueryExpansionResult,
    max_queries: int = 6,
) -> list[str]:
    if max_queries <= 0:
        return []
    return [query.query for query in result.expanded_queries[:max_queries]]


def _join_unique_terms(terms: list[str]) -> str:
    normalized_terms = [normalize_query_text(term) for term in terms if normalize_query_text(term)]
    return " ".join(dict.fromkeys(normalized_terms))


def _dedupe_expanded_queries(queries: list[ExpandedQuery]) -> list[ExpandedQuery]:
    deduped: list[ExpandedQuery] = []
    seen: set[str] = set()
    for query in queries:
        normalized_query = query.query.casefold()
        if normalized_query in seen:
            continue
        seen.add(normalized_query)
        deduped.append(query)
    return deduped


def _is_sensitive_risk(risk_level: str | None) -> bool:
    return (risk_level or "").casefold() in {
        "high",
        "legal_sensitive",
        "work_status_sensitive",
        "medical_sensitive",
        "emergency",
        "unsafe",
        "prompt_injection",
    }
