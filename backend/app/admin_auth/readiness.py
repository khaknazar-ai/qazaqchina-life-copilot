from pathlib import Path

from backend.app.admin_auth.models import AdminAuthConfig, AdminAuthReadinessReport
from backend.app.admin_auth.permissions import ROLE_PERMISSIONS, all_permissions


def build_admin_auth_readiness_report(
    project_root: Path | str = ".",
    config: AdminAuthConfig | None = None,
) -> AdminAuthReadinessReport:
    root = Path(project_root)
    active_config = config or AdminAuthConfig()
    docs_exist = (root / "docs" / "admin_auth_rbac_foundation.md").exists()
    warnings = [
        "Admin auth foundation is local/dev token-based and is not production-ready.",
    ]
    if not active_config.enabled:
        warnings.append("Admin auth is disabled by default for local deterministic demos.")
    if not docs_exist:
        warnings.append("Admin auth/RBAC documentation is missing.")
    return AdminAuthReadinessReport(
        enabled=active_config.enabled,
        mode=active_config.mode,
        configured_token_count=len(active_config.tokens),
        production_ready=False,
        hardcoded_secret_detected=False,
        default_open_mode=not active_config.enabled,
        roles_defined=sorted(ROLE_PERMISSIONS),
        permissions_defined=sorted(all_permissions()),
        warnings=warnings,
        recommendations=[
            "Integrate with a production identity provider before public launch.",
            "Store admin secrets outside code and reports, with rotation and revocation.",
            "Require HTTPS/TLS, rate limiting, monitoring, and incident response for admin routes.",
            "Persist admin audit logs in production storage with access controls.",
            "Enforce RBAC consistently on all deployed admin and trace surfaces.",
        ],
        used_network=False,
        used_external_provider=False,
    )


def admin_auth_report_to_jsonable(report: AdminAuthReadinessReport) -> dict:
    return report.model_dump(mode="json")


def admin_auth_report_to_markdown(report: AdminAuthReadinessReport) -> str:
    lines = [
        "# Admin Auth and RBAC Readiness Report",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Enabled: {report.enabled}",
        f"- Mode: {report.mode}",
        f"- Configured token count: {report.configured_token_count}",
        f"- Production ready: {report.production_ready}",
        f"- Default open mode: {report.default_open_mode}",
        f"- Hardcoded secret detected: {report.hardcoded_secret_detected}",
        f"- Used network: {report.used_network}",
        f"- Used external provider: {report.used_external_provider}",
        "",
        "## Roles",
        "",
    ]
    lines.extend(f"- {role}" for role in report.roles_defined)
    lines.extend(["", "## Permissions", ""])
    lines.extend(f"- {permission}" for permission in report.permissions_defined)
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in report.warnings)
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {recommendation}" for recommendation in report.recommendations)
    return "\n".join(lines) + "\n"
