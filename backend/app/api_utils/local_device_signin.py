"""One-step sign-in for the explicitly enabled, single-user local workspace.

Local computer processes are trusted in this development mode. Request headers
prevent browser-origin requests; they are not proof of WeChat identity.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from backend.app.api_utils.pilot_access import PilotAccessService
from backend.app.config import Settings

PUBLIC_SIGNIN_PATHS = frozenset({"/api/local-access/start"})
router = APIRouter(tags=["local-device-signin"])


class LocalDeviceSignin:
    def __init__(self, settings: Settings, access: PilotAccessService) -> None:
        if (
            not settings.LOCAL_DEVICE_SIGNIN_ENABLED
            or not settings.LOCAL_DEVICE_SIGNIN_DEVTOOLS_REFERER
            or settings.APP_ENV != "local" or not settings.ENABLE_LOCAL_PERSISTENCE
            or not access.supports_local_owner or settings.ADMIN_AUTH_ENABLED
            or any((settings.LLM_ENABLE_EXTERNAL, settings.QWEN_CHAT_ENABLED,
                    settings.QWEN_OCR_ENABLED, settings.CLOUD_RETRIEVAL_ENABLED,
                    settings.QWEN_RERANK_ENABLED, settings.SEMANTIC_CONFLICT_REVIEW_ENABLED,
                    settings.LLM_PROVIDER_ENABLED))
        ):
            raise ValueError(
                "Device sign-in requires the isolated persistent local-owner workspace"
            )
        self._access = access

    def start(self, account_type: Literal["citizen", "consul"] = "citizen") -> dict:
        return {"session_token": self._access.issue_local_session(account_type),
                "expires_in_seconds": 7200, "account_type": account_type, "local_preview": True}


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocalSigninRequest(EmptyRequest):
    account_type: Literal["citizen", "consul"] = "citizen"


def _private_response(data: dict) -> JSONResponse:
    return JSONResponse(data, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


@router.post("/api/local-access/start")
def start_local_signin(request: Request, body: LocalSigninRequest):
    service = getattr(request.app.state, "local_device_signin", None)
    if service is None:
        raise HTTPException(404, "local_signin_disabled")
    return _private_response(service.start(body.account_type))


@router.post("/api/local-access/logout")
def logout_local_signin(request: Request, body: EmptyRequest):
    request.app.state.pilot_access_service.revoke_local_session(
        request.headers.get("authorization", ""),
    )
    return _private_response({"signed_out": True})
