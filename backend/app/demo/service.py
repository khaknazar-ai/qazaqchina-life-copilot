from backend.app.api_utils.validation import require_known_demo_scenario
from backend.app.demo.models import DemoRunResult, DemoScenario
from backend.app.demo.runner import DemoScenarioRunner
from backend.app.demo.scenarios import (
    demo_scenario_ids,
    get_demo_scenario,
    list_demo_scenarios,
)
from backend.app.services.chat_service import ChatService


class DemoService:
    def list_scenarios(self) -> list[DemoScenario]:
        return list_demo_scenarios()

    def get_scenario(self, scenario_id: str) -> DemoScenario:
        normalized_id = require_known_demo_scenario(
            scenario_id=scenario_id,
            available_ids=demo_scenario_ids(),
        )
        return get_demo_scenario(normalized_id)

    def run_scenario(
        self,
        scenario_id: str,
        use_agent_workflow: bool = True,
    ) -> DemoRunResult:
        scenario = self.get_scenario(scenario_id)
        runner = DemoScenarioRunner(
            chat_service=ChatService(use_agent_workflow=use_agent_workflow),
        )
        return runner.run(scenario)
