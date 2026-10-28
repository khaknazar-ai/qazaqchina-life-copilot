from fastapi import APIRouter

from backend.app.api_utils.errors import http_exception
from backend.app.demo.service import DemoService
from backend.app.schemas.demo import (
    DemoRunScenarioRequest,
    DemoRunScenarioResponse,
    DemoScenarioListResponse,
    DemoScenarioResponse,
)

# RequestGuard requires loopback access or pilot authentication for these fixtures.
router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("/scenarios", response_model=DemoScenarioListResponse)
def list_demo_scenarios() -> DemoScenarioListResponse:
    return DemoScenarioListResponse(scenarios=DemoService().list_scenarios())


@router.get("/scenarios/{scenario_id}", response_model=DemoScenarioResponse)
def get_demo_scenario(scenario_id: str) -> DemoScenarioResponse:
    try:
        scenario = DemoService().get_scenario(scenario_id)
    except ValueError as exc:
        raise http_exception(
            status_code=404,
            code="demo_scenario_not_found",
            message=str(exc),
            field="scenario_id",
        ) from exc
    return DemoScenarioResponse(scenario=scenario)


@router.post("/run", response_model=DemoRunScenarioResponse)
def run_demo_scenario(request: DemoRunScenarioRequest) -> DemoRunScenarioResponse:
    try:
        result = DemoService().run_scenario(
            scenario_id=request.scenario_id,
            use_agent_workflow=request.use_agent_workflow,
        )
    except ValueError as exc:
        raise http_exception(
            status_code=404,
            code="demo_scenario_not_found",
            message=str(exc),
            field="scenario_id",
        ) from exc
    return DemoRunScenarioResponse(result=result)
