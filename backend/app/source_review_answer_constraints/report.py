from backend.app.source_review_answer_constraints.models import (
    SourceReviewAnswerConstraintsReport,
)


def source_review_answer_constraints_report_to_jsonable(
    report: SourceReviewAnswerConstraintsReport,
) -> dict:
    return report.model_dump(mode="json")


def source_review_answer_constraints_report_to_markdown(
    report: SourceReviewAnswerConstraintsReport,
) -> str:
    lines = [
        "# Source Review Answer Constraints Report",
        "",
        "## Executive Decision",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Total domains: {report.total_domains}",
        f"- Constrained domain count: {report.constrained_domain_count}",
        f"- Direct answer allowed count: {report.direct_answer_allowed_count}",
        (
            "- Official verification required count: "
            f"{report.official_verification_required_count}"
        ),
        (
            "- Human escalation recommended count: "
            f"{report.human_escalation_recommended_count}"
        ),
        f"- Refuse specific claims count: {report.refuse_specific_claims_count}",
        f"- Ready for closed beta: {report.ready_for_closed_beta}",
        f"- Ready for public launch: {report.ready_for_public_launch}",
        f"- Used network: {report.used_network}",
        f"- Used external provider: {report.used_external_provider}",
        "",
        "Unpublished source candidates must not be cited in citizen answers.",
        "Publish preview eligibility is not publishing and is not trusted evidence.",
        "",
        "## Constrained Domains",
        "",
        "| Domain | Source review state | Candidates | Blocked | Preview eligible | Mode |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for constraint in report.constraints:
        lines.append(
            f"| {constraint.domain} | {constraint.source_review_status} | "
            f"{constraint.candidate_count} | {constraint.blocked_candidate_count} | "
            f"{constraint.publish_preview_eligible} | {constraint.allowed_mode} |"
        )

    lines.extend(["", "## Source Review State", ""])
    for constraint in report.constraints:
        lines.extend(
            [
                f"### {constraint.domain}",
                "",
                f"- Official source published: {constraint.official_source_published}",
                f"- Publish preview eligible: {constraint.publish_preview_eligible}",
                f"- Candidate count: {constraint.candidate_count}",
                f"- Blocked candidate count: {constraint.blocked_candidate_count}",
                (
                    "- Citizen-visible source review disclosure allowed: "
                    f"{constraint.citizen_visible_source_review_disclosure_allowed}"
                ),
                "",
                "Citizen answer mode:",
                "",
                f"- {constraint.allowed_mode}",
                "",
                "Prohibited claim types:",
            ]
        )
        lines.extend(f"- {claim}" for claim in constraint.prohibited_claim_types)
        lines.extend(
            [
                "",
                "Required warning:",
                "",
                f"- {constraint.required_warning}",
                "",
                "Safe response guidance:",
            ]
        )
        lines.extend(f"- {item}" for item in constraint.safe_response_guidance)
        lines.extend(["", "Admin-only notes:"])
        if constraint.admin_only_notes:
            lines.extend(f"- {note}" for note in constraint.admin_only_notes)
        else:
            lines.append("- None.")
        lines.append("")

    lines.extend(
        [
            "## Admin-Only Vs Citizen-Visible Separation",
            "",
            "- Source review progress is admin/internal state only.",
            "- Citizen answers must not reveal unpublished candidate status as authority.",
            "- Citizen answers may say official verification is required.",
            "- Citizen answers must not cite candidate IDs, local intake, reviewer packets, "
            "draft evidence, review evidence, or preview packages.",
            "",
            "## Why Candidates Are Not Trusted Evidence",
            "",
            "- A candidate can be wrong, stale, unofficial, incomplete, or outside scope.",
            "- Source URL presence does not prove official status.",
            "- Missing review evidence blocks high-risk certainty.",
            "",
            "## Why Publish Preview Is Not Publishing",
            "",
            "- Publish preview only prepares an internal package.",
            "- Preview eligibility does not update trusted registry data.",
            "- A preview package is not trusted citizen-answer evidence.",
            "",
            "## No Citizen-Answer Citation Before Publishing",
            "",
            "- No unpublished source candidate can be cited in citizen answers.",
            "- No reviewer packet, draft evidence, review evidence, or preview package can "
            "be cited in citizen answers.",
            "- Direct high-risk certainty remains blocked until published official source "
            "coverage exists.",
            "",
            "## Launch And Execution Limits",
            "",
            "- Closed beta remains false.",
            "- Public launch remains false.",
            "- No network/provider used.",
            "- No registry write or source publishing occurred.",
            "",
            "## Notes",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in report.notes)
    return "\n".join(lines) + "\n"
