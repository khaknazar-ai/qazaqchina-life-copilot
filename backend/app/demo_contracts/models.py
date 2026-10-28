from dataclasses import dataclass, field


@dataclass(frozen=True)
class DemoSmokeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class DemoSmokeSummary:
    checks: list[DemoSmokeCheck] = field(default_factory=list)
    scenario_ids: list[str] = field(default_factory=list)
    default_llm_provider: str | None = None
    external_llm_enabled: bool | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> list[DemoSmokeCheck]:
        return [check for check in self.checks if not check.passed]

    @property
    def passed_count(self) -> int:
        return sum(1 for check in self.checks if check.passed)


@dataclass(frozen=True)
class FrontendContractSummary:
    app_pages: list[str] = field(default_factory=list)
    api_paths_present: list[str] = field(default_factory=list)
    api_paths_missing: list[str] = field(default_factory=list)
    wrapper_names_present: list[str] = field(default_factory=list)
    wrapper_names_missing: list[str] = field(default_factory=list)
    missing_page_files: list[str] = field(default_factory=list)
    fallback_scenario_ids: list[str] = field(default_factory=list)
    unexpected_fallback_scenario_ids: list[str] = field(default_factory=list)
    missing_fallback_scenario_ids: list[str] = field(default_factory=list)
    executable_external_urls: list[str] = field(default_factory=list)
    secret_markers_found: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(
            [
                self.api_paths_missing,
                self.wrapper_names_missing,
                self.missing_page_files,
                self.unexpected_fallback_scenario_ids,
                self.missing_fallback_scenario_ids,
                self.executable_external_urls,
                self.secret_markers_found,
            ]
        )
