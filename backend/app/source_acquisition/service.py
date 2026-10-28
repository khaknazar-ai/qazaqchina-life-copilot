from backend.app.source_acquisition.models import (
    SourceAcquisitionCreateRequest,
    SourceAcquisitionStatus,
    SourceAcquisitionSummary,
    SourceAcquisitionTaskRecord,
    SourceAcquisitionUpdateRequest,
    utc_now,
)
from backend.app.source_coverage.models import (
    SourceAcquisitionTask,
    SourceCoverageReport,
)

DEFAULT_ACCEPTANCE_CRITERIA = [
    "official URL/document captured",
    "classification completed",
    "freshness checked",
    "reviewer approved",
    "version recorded",
    "publish preview generated",
]

OPEN_STATUSES = {
    "new",
    "assigned",
    "researching",
    "candidate_created",
    "in_review",
    "approved_for_publishing_preview",
    "blocked",
}


class SourceAcquisitionService:
    def __init__(
        self,
        tasks: list[SourceAcquisitionTaskRecord] | None = None,
    ) -> None:
        self._tasks: dict[str, SourceAcquisitionTaskRecord] = {
            task.task_id: task for task in tasks or []
        }

    def create_task(
        self,
        request: SourceAcquisitionCreateRequest,
    ) -> SourceAcquisitionTaskRecord:
        criteria = request.acceptance_criteria or DEFAULT_ACCEPTANCE_CRITERIA
        task = SourceAcquisitionTaskRecord(
            domain=request.domain,
            priority=request.priority,
            target_trust_tier=request.target_trust_tier,
            description=request.description,
            suggested_owner_role=request.suggested_owner_role,
            assigned_to=request.assigned_to,
            status="assigned" if request.assigned_to else "new",
            acceptance_criteria=list(criteria),
            not_trusted_until_reviewed=True,
            notes=[
                *request.notes,
                "Acquisition task only; not trusted evidence until review and publishing.",
            ],
        )
        self._tasks[task.task_id] = task
        return task

    def create_tasks_from_coverage_report(
        self,
        report: SourceCoverageReport,
    ) -> list[SourceAcquisitionTaskRecord]:
        records: list[SourceAcquisitionTaskRecord] = []
        for task in report.acquisition_backlog:
            record = self._record_from_coverage_task(task)
            self._tasks[record.task_id] = record
            records.append(record)
        return records

    def list_tasks(
        self,
        status: str | None = None,
        priority: str | None = None,
        domain: str | None = None,
        limit: int = 100,
    ) -> list[SourceAcquisitionTaskRecord]:
        tasks = sorted(self._tasks.values(), key=lambda task: (task.created_at, task.task_id))
        if status:
            tasks = [task for task in tasks if task.status == status]
        if priority:
            tasks = [task for task in tasks if task.priority == priority]
        if domain:
            tasks = [task for task in tasks if task.domain == domain]
        return tasks[:limit]

    def get_task(self, task_id: str) -> SourceAcquisitionTaskRecord | None:
        return self._tasks.get(task_id)

    def update_task(
        self,
        task_id: str,
        request: SourceAcquisitionUpdateRequest,
    ) -> SourceAcquisitionTaskRecord:
        task = self._require_task(task_id)
        next_status = request.status or task.status
        source_candidate_id = request.source_candidate_id or task.source_candidate_id
        _validate_transition(task, next_status, source_candidate_id)

        notes = list(task.notes)
        if request.note:
            notes.append(request.note)
        updated = task.model_copy(
            update={
                "status": next_status,
                "assigned_to": request.assigned_to
                if request.assigned_to is not None
                else task.assigned_to,
                "source_candidate_id": source_candidate_id,
                "notes": notes,
                "not_trusted_until_reviewed": True,
                "updated_at": utc_now(),
            }
        )
        self._tasks[task_id] = updated
        return updated

    def summarize(self) -> SourceAcquisitionSummary:
        tasks = list(self._tasks.values())
        return SourceAcquisitionSummary(
            total_tasks=len(tasks),
            open_tasks=sum(1 for task in tasks if task.status in OPEN_STATUSES),
            critical_tasks=sum(1 for task in tasks if task.priority == "critical"),
            assigned_tasks=sum(1 for task in tasks if task.assigned_to),
            candidate_created_count=sum(
                1 for task in tasks if task.status == "candidate_created"
            ),
            not_trusted_until_reviewed_count=sum(
                1 for task in tasks if task.not_trusted_until_reviewed
            ),
            used_network=False,
            used_external_provider=False,
            warnings=[
                "Acquisition tasks are not trusted evidence.",
                "Source task completion still requires source candidate review.",
                "No source registry files were modified.",
            ],
        )

    def _record_from_coverage_task(
        self,
        task: SourceAcquisitionTask,
    ) -> SourceAcquisitionTaskRecord:
        return SourceAcquisitionTaskRecord(
            task_id=task.task_id,
            domain=task.domain,
            priority=task.priority,
            target_trust_tier=task.target_trust_tier,
            description=task.description,
            suggested_owner_role=task.suggested_owner_role,
            status="new",
            acceptance_criteria=list(task.acceptance_criteria),
            not_trusted_until_reviewed=True,
            notes=[
                "Created from source coverage gap analysis.",
                "Planned source is not trusted until review and publishing.",
            ],
        )

    def _require_task(self, task_id: str) -> SourceAcquisitionTaskRecord:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"source acquisition task not found: {task_id}")
        return task


def _validate_transition(
    task: SourceAcquisitionTaskRecord,
    next_status: SourceAcquisitionStatus,
    source_candidate_id: str | None,
) -> None:
    if next_status == "candidate_created" and not source_candidate_id:
        raise ValueError("candidate_created status requires source_candidate_id")
    if next_status == "approved_for_publishing_preview":
        if not source_candidate_id:
            raise ValueError(
                "approved_for_publishing_preview requires source_candidate_id"
            )
        if task.status not in {"in_review", "approved_for_publishing_preview"}:
            raise ValueError(
                "approved_for_publishing_preview requires prior in_review state"
            )
