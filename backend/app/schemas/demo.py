from pydantic import BaseModel

from backend.app.demo.models import DemoRunResult, DemoScenario


class DemoScenarioListResponse(BaseModel):
    scenarios: list[DemoScenario]


class DemoScenarioResponse(BaseModel):
    scenario: DemoScenario


class DemoRunScenarioRequest(BaseModel):
    scenario_id: str
    use_agent_workflow: bool = True


class DemoRunScenarioResponse(BaseModel):
    result: DemoRunResult
