from backend.app.durable_storage.models import DurableStorageHealthReport
from backend.app.durable_storage.sqlite_store import SQLiteDurableStore


def build_durable_storage_readiness_report(
    store: SQLiteDurableStore,
) -> DurableStorageHealthReport:
    return store.health_check()


def durable_storage_report_to_jsonable(report: DurableStorageHealthReport) -> dict:
    return report.model_dump(mode="json")


def durable_storage_report_to_markdown(report: DurableStorageHealthReport) -> str:
    lines = [
        "# Durable Storage Readiness Report",
        "",
        f"- DB path: `{report.db_path}`",
        f"- Initialized: {report.initialized}",
        f"- Expected tables present: {report.expected_tables_present}",
        f"- Table count: {report.table_count}",
        f"- Raw image storage allowed: {report.raw_image_storage_allowed}",
        f"- Production database: {report.production_database}",
        f"- Used network: {report.used_network}",
        "",
        "## Record Counts",
        "",
    ]
    lines.extend(f"- {table}: {count}" for table, count in sorted(report.record_counts.items()))
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {warning}" for warning in report.warnings)
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {recommendation}" for recommendation in report.recommendations)
    return "\n".join(lines) + "\n"
