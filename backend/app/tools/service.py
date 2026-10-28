from backend.app.retrieval.planner import (
    RetrievalPlanningInput,
    build_retrieval_plan,
)
from backend.app.tools.fake_web import FakeWebSearchTool
from backend.app.tools.models import ToolCallRequest, ToolCallResult, ToolTrace
from backend.app.tools.policies import build_tool_query_from_retrieval_plan


class ToolDiscoveryService:
    def __init__(self, web_search_tool: FakeWebSearchTool | None = None) -> None:
        self.web_search_tool = web_search_tool or FakeWebSearchTool()

    def plan_tool_calls(self, planning_input: RetrievalPlanningInput) -> list[ToolCallRequest]:
        plan = build_retrieval_plan(planning_input)
        return [
            ToolCallRequest(
                tool_name="fake_web_search",
                query=query,
                scenario=planning_input.scenario or plan.scenario,
                risk_level=planning_input.risk_level,
                language=planning_input.language,
                country=planning_input.country,
                city=planning_input.city,
            )
            for query in build_tool_query_from_retrieval_plan(plan)
        ]

    def run_fake_web_discovery(
        self,
        planning_input: RetrievalPlanningInput,
    ) -> list[ToolCallResult]:
        plan = build_retrieval_plan(planning_input)
        return [
            self.web_search_tool.search(request, plan=plan)
            for request in self.plan_tool_calls(planning_input)
        ]

    def build_tool_traces(
        self,
        results: list[ToolCallResult],
        request: ToolCallRequest | None = None,
    ) -> list[ToolTrace]:
        return [
            ToolTrace(
                tool_name=result.tool_name,
                query=result.query,
                scenario=request.scenario if request is not None else None,
                risk_level=request.risk_level if request is not None else None,
                used_network=result.used_network,
                candidate_count=len(result.candidates),
                warnings=result.warnings,
                blocked_reason=result.blocked_reason,
            )
            for result in results
        ]
