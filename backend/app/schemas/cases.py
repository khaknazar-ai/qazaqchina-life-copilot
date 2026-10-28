from pydantic import BaseModel

from backend.app.domain.cases import UserCase
from backend.app.domain.enums import UserScenario


class CaseCreateRequest(BaseModel):
    case_type: UserScenario
    city: str | None = None
    user_id: str | None = None


class CaseResponse(BaseModel):
    case: UserCase


class CaseListResponse(BaseModel):
    cases: list[UserCase]
