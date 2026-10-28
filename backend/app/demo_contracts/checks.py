import json
import re
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.demo.scenarios import demo_scenario_ids
from backend.app.demo_contracts.models import (
    DemoSmokeCheck,
    DemoSmokeSummary,
    FrontendContractSummary,
)
from backend.app.demo_contracts.secret_scan import frontend_secret_markers
from backend.app.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_ROOT = PROJECT_ROOT / "frontend" / "wechat-miniprogram"

EXPECTED_DEMO_API_ENDPOINTS = (
    "/health",
    "/api/capabilities",
    "/api/demo/scenarios",
    "/api/demo/run",
)

EXPECTED_FRONTEND_API_PATHS = (
    "/api/capabilities",
    "/api/demo/scenarios",
    "/api/demo/run",
    "/api/chat",
    "/api/checklists",
    "/api/translate/explain",
)

EXPECTED_FRONTEND_WRAPPERS = (
    "getCapabilities",
    "listDemoScenarios",
    "getDemoScenario",
    "runDemoScenario",
    "sendChatMessage",
    "createChecklist",
    "explainChineseText",
    "createCommunityPost",
)

EXPECTED_FRONTEND_PAGES = (
    "pages/home/index",
    "pages/demo/index",
    "pages/demo-detail/index",
    "pages/chat/index",
    "pages/checklist/index",
    "pages/explain/index",
    "pages/emergency/index",
)

def run_api_demo_smoke() -> DemoSmokeSummary:
    client = TestClient(app)
    checks: list[DemoSmokeCheck] = []
    scenario_ids: list[str] = []
    default_llm_provider: str | None = None
    external_llm_enabled: bool | None = None

    health_response = client.get("/health")
    checks.append(
        _check(
            name="GET /health",
            passed=health_response.status_code == 200,
            detail=f"status={health_response.status_code}",
        )
    )

    capabilities_response = client.get("/api/capabilities")
    capabilities = _json_if_ok(capabilities_response)
    default_llm_provider = capabilities.get("default_llm_provider")
    external_llm_enabled = capabilities.get("external_llm_enabled")
    checks.append(
        _check(
            name="GET /api/capabilities",
            passed=capabilities_response.status_code == 200,
            detail=(
                f"status={capabilities_response.status_code}, "
                f"provider={default_llm_provider}, external_llm={external_llm_enabled}"
            ),
        )
    )
    checks.append(
        _check(
            name="External LLM disabled by default",
            passed=external_llm_enabled is False and default_llm_provider == "mock",
            detail=f"provider={default_llm_provider}, external_llm={external_llm_enabled}",
        )
    )

    scenarios_response = client.get("/api/demo/scenarios")
    scenarios_body = _json_if_ok(scenarios_response)
    scenario_ids = [
        scenario.get("scenario_id", "")
        for scenario in scenarios_body.get("scenarios", [])
        if scenario.get("scenario_id")
    ]
    expected_ids = demo_scenario_ids()
    checks.append(
        _check(
            name="GET /api/demo/scenarios",
            passed=scenarios_response.status_code == 200 and len(scenario_ids) >= 6,
            detail=f"status={scenarios_response.status_code}, scenarios={len(scenario_ids)}",
        )
    )
    checks.append(
        _check(
            name="Demo scenario IDs match registry",
            passed=scenario_ids == expected_ids,
            detail=", ".join(scenario_ids),
        )
    )

    for scenario_id in scenario_ids:
        response = client.post("/api/demo/run", json={"scenario_id": scenario_id})
        body = _json_if_ok(response)
        result = body.get("result", {})
        useful_output = any(
            result.get(field)
            for field in (
                "chat_response",
                "checklist",
                "translation_explanation",
                "moderation_result",
                "notes",
            )
        )
        checks.append(
            _check(
                name=f"POST /api/demo/run {scenario_id}",
                passed=(
                    response.status_code == 200
                    and result.get("scenario", {}).get("scenario_id") == scenario_id
                    and useful_output
                ),
                detail=f"status={response.status_code}, useful_output={useful_output}",
            )
        )

    return DemoSmokeSummary(
        checks=checks,
        scenario_ids=scenario_ids,
        default_llm_provider=default_llm_provider,
        external_llm_enabled=external_llm_enabled,
    )


def inspect_frontend_contract(frontend_root: Path = FRONTEND_ROOT) -> FrontendContractSummary:
    app_json = _read_json(frontend_root / "app.json")
    api_js = _read_text(frontend_root / "utils" / "api.js")
    env_js = _read_text(frontend_root / "config" / "env.js")
    demo_index_js = _read_text(frontend_root / "pages" / "demo" / "index.js")
    demo_detail_js = _read_text(frontend_root / "pages" / "demo-detail" / "index.js")
    all_js = "\n".join([api_js, env_js, demo_index_js, demo_detail_js])

    app_pages = list(app_json.get("pages", []))
    missing_page_files = _missing_page_files(frontend_root, app_pages)
    api_paths_present = [path for path in EXPECTED_FRONTEND_API_PATHS if path in api_js]
    api_paths_missing = [path for path in EXPECTED_FRONTEND_API_PATHS if path not in api_js]
    wrapper_names_present = [
        name for name in EXPECTED_FRONTEND_WRAPPERS if f"function {name}" in api_js
    ]
    wrapper_names_missing = [
        name for name in EXPECTED_FRONTEND_WRAPPERS if f"function {name}" not in api_js
    ]
    fallback_scenario_ids = _extract_scenario_ids(demo_index_js + "\n" + demo_detail_js)
    expected_ids = set(demo_scenario_ids())
    fallback_ids = set(fallback_scenario_ids)

    return FrontendContractSummary(
        app_pages=app_pages,
        api_paths_present=api_paths_present,
        api_paths_missing=api_paths_missing,
        wrapper_names_present=wrapper_names_present,
        wrapper_names_missing=wrapper_names_missing,
        missing_page_files=missing_page_files,
        fallback_scenario_ids=fallback_scenario_ids,
        unexpected_fallback_scenario_ids=sorted(fallback_ids - expected_ids),
        missing_fallback_scenario_ids=sorted(expected_ids - fallback_ids),
        executable_external_urls=_executable_external_urls([api_js, env_js]),
        secret_markers_found=frontend_secret_markers(all_js),
    )


def _check(name: str, passed: bool, detail: str) -> DemoSmokeCheck:
    return DemoSmokeCheck(name=name, passed=passed, detail=detail)


def _json_if_ok(response: Any) -> dict[str, Any]:
    if response.status_code >= 200 and response.status_code < 300:
        return response.json()
    return {}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _missing_page_files(frontend_root: Path, app_pages: list[str]) -> list[str]:
    missing_files: list[str] = []
    for page in app_pages:
        page_path = frontend_root / page
        for suffix in (".js", ".json", ".wxml", ".wxss"):
            candidate = page_path.with_suffix(suffix)
            if not candidate.exists():
                missing_files.append(str(candidate.relative_to(frontend_root)))
    return missing_files


def _extract_scenario_ids(text: str) -> list[str]:
    ids = re.findall(r"scenario_id:\s*\"([a-z0-9-]+)\"", text)
    ids.extend(re.findall(r"\"([a-z0-9-]+)\":\s*\{", text))
    return list(dict.fromkeys(ids))


def _executable_external_urls(js_texts: list[str]) -> list[str]:
    urls: list[str] = []
    for text in js_texts:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            for url in re.findall(r"https?://[^\"'`\\s]+", stripped):
                if url != "http://127.0.0.1:8000":
                    urls.append(url)
    return list(dict.fromkeys(urls))
