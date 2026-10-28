from pathlib import Path

from backend.app.demo_contracts.checks import (
    EXPECTED_DEMO_API_ENDPOINTS,
    EXPECTED_FRONTEND_PAGES,
    inspect_frontend_contract,
    run_api_demo_smoke,
)
from backend.app.demo_contracts.models import DemoSmokeSummary, FrontendContractSummary


def generate_demo_readiness_markdown(
    smoke_summary: DemoSmokeSummary | None = None,
    frontend_summary: FrontendContractSummary | None = None,
) -> str:
    smoke = smoke_summary or run_api_demo_smoke()
    frontend = frontend_summary or inspect_frontend_contract()
    fallback_mismatches = (
        frontend.unexpected_fallback_scenario_ids
        + frontend.missing_fallback_scenario_ids
    )

    lines = [
        "# Demo Readiness Report",
        "",
        "## Summary",
        "",
        f"- API smoke: {_status(smoke.passed)} ({smoke.passed_count}/{len(smoke.checks)} checks)",
        f"- Frontend contract: {_status(frontend.passed)}",
        f"- Default LLM provider: `{smoke.default_llm_provider}`",
        f"- External LLM enabled: `{smoke.external_llm_enabled}`",
        "",
        "## API Smoke Checks",
        "",
    ]
    lines.extend(
        f"- {_status(check.passed)} {check.name}: {check.detail}" for check in smoke.checks
    )
    lines.extend(
        [
            "",
            "## Demo API Endpoints",
            "",
        ]
    )
    lines.extend(f"- `{endpoint}`" for endpoint in EXPECTED_DEMO_API_ENDPOINTS)
    lines.extend(
        [
            "",
            "## Demo Scenarios",
            "",
        ]
    )
    lines.extend(f"- `{scenario_id}`" for scenario_id in smoke.scenario_ids)
    lines.extend(
        [
            "",
            "## Frontend Contract",
            "",
            f"- Pages configured: {len(frontend.app_pages)}",
            f"- Missing page files: {_list_or_none(frontend.missing_page_files)}",
            f"- API paths missing: {_list_or_none(frontend.api_paths_missing)}",
            f"- Wrapper names missing: {_list_or_none(frontend.wrapper_names_missing)}",
            f"- Fallback scenario IDs: {_list_or_none(frontend.fallback_scenario_ids)}",
            (
                "- Fallback scenario ID mismatches: "
                f"{_list_or_none(fallback_mismatches)}"
            ),
            f"- External executable URLs: {_list_or_none(frontend.executable_external_urls)}",
            f"- Secret markers found: {_list_or_none(frontend.secret_markers_found)}",
            "",
            "## Expected Mini Program Pages",
            "",
        ]
    )
    lines.extend(f"- `{page}`" for page in EXPECTED_FRONTEND_PAGES)
    lines.extend(
        [
            "",
            "## Related Docs",
            "",
            "- `docs/demo_walkthrough.md`",
            "- `docs/demo_readiness_checklist.md`",
            "- `docs/architecture_overview.md`",
            "",
            "## Limitations",
            "",
            "- This is a deterministic local demo, not production deployment.",
            "- The default provider is MockLLM; no external LLM is called by default.",
            (
                "- The demo does not provide certified legal, medical, emergency, "
                "or translation advice."
            ),
            (
                "- Production requires HTTPS request domain configuration, authentication, "
                "real source ingestion, provider evals, and human review operations."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_demo_readiness_report(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "demo_readiness.md"
    output_path.write_text(generate_demo_readiness_markdown(), encoding="utf-8")
    return output_path


def _status(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def _list_or_none(items: list[str]) -> str:
    if not items:
        return "none"
    return ", ".join(f"`{item}`" for item in items)
