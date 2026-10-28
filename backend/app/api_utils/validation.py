def require_non_empty_text(value: str, field_name: str = "text") -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return stripped


def require_known_demo_scenario(scenario_id: str, available_ids: list[str]) -> str:
    normalized = require_non_empty_text(scenario_id, field_name="scenario_id").casefold()
    if normalized not in set(available_ids):
        raise ValueError("Unknown demo scenario.")
    return normalized


def normalize_optional_language(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped.casefold()
