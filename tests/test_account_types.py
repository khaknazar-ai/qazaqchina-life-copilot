"""Account authorization, owner isolation and explicit request sharing; no live LLM."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.api_utils.pilot_access import PilotAccessService
from backend.app.main import create_app
from scripts.run_local_workspace import local_settings

OWNER = "isolated-account-owner-fixture-000000"
CONSUL = "isolated-account-consul-fixture-00000"
OTHER = "isolated-account-other-fixture-000000"


def auth(value):
    return {"Authorization": "Bearer " + value}


def settings_for(tmp_path):
    return local_settings(OWNER, tmp_path, use_ollama=False).model_copy(
        update={
            "LOCAL_DEVICE_SIGNIN_ENABLED": False,
            "PILOT_ACCESS_TOKENS": SecretStr(
                json.dumps({"citizen": OWNER, "consul": CONSUL, "other": OTHER})
            ),
            "PILOT_ACCOUNT_TYPES": '{"consul":"consul"}',
            "API_USER_REQUESTS_PER_MINUTE": 120,
            "API_IP_REQUESTS_PER_MINUTE": 300,
        }
    )


def local_headers(settings):
    return {
        "Referer": settings.LOCAL_DEVICE_SIGNIN_DEVTOOLS_REFERER,
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "X-Q-Local-Access": "devtools",
    }


@pytest.mark.parametrize(
    "mapping",
    [
        '{"consul":"admin"}',
        '{"unknown":"consul"}',
        "[]",
        '{"consul":"consul","consul":"citizen"}',
        '{"consul":["consul"]}',
    ],
)
def test_only_explicit_known_server_account_types_are_valid(tmp_path, mapping):
    with pytest.raises(ValueError):
        PilotAccessService(
            settings_for(tmp_path).model_copy(update={"PILOT_ACCOUNT_TYPES": mapping})
        )


def test_account_types_are_server_assigned_and_do_not_grant_admin_or_trust(tmp_path):
    with TestClient(create_app(settings_for(tmp_path))) as client:
        for token, role in [(OWNER, "citizen"), (OTHER, "citizen"), (CONSUL, "consul")]:
            session = client.post("/api/workspace/session", json={}, headers=auth(token)).json()
            assert session["account_type"] == role and not session["local_preview"]
            assert (
                client.get("/api/admin/workspace/support", headers=auth(token)).status_code == 403
            )
            profile = client.get("/api/workspace/profile", headers=auth(token)).json()
            assert profile["account"]["account_type"] == role
            assert "verified_role" not in json.dumps(profile)
        for claim in [
            {"account_type": "consul"},
            {"verified_role": "verified_consul"},
            {"owner": "consul"},
        ]:
            assert (
                client.patch("/api/workspace/profile", json=claim, headers=auth(OWNER)).status_code
                == 422
            )
        forged = {**auth(OWNER), "X-Account-Type": "consul", "X-Role": "consul"}
        for method, path, body in [
            ("GET", "/api/consul/requests", None),
            ("GET", "/api/consul/requests/missing", None),
            ("PATCH", "/api/consul/requests/missing", {"status": "resolved"}),
            ("POST", "/api/consul/requests/missing/replies", {"text": "forged"}),
        ]:
            assert client.request(method, path, json=body, headers=forged).status_code == 403
        assert client.get("/api/consul/requests").status_code == 401
        assert (
            client.post(
                "/api/local-access/start",
                json={"account_type": "consul"},
                headers=local_headers(settings_for(tmp_path)),
            ).status_code
            == 401
        )


def test_request_sharing_reply_status_idempotency_and_private_case_isolation(tmp_path):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)) as client:
        case = client.post(
            "/api/workspace/cases",
            json={
                "title": "PRIVATE CASE",
                "scenario": "study",
                "context": {"notes": "PRIVATE NOTES"},
            },
            headers=auth(OWNER),
        ).json()["case"]
        cid = case["case_id"]
        assert (
            client.post(
                f"/api/workspace/cases/{cid}/documents",
                json={"title": "PRIVATE DOC", "text": "PRIVATE CONTENT"},
                headers=auth(OWNER),
            ).status_code
            == 200
        )
        assert (
            client.patch(
                "/api/workspace/profile",
                json={"display_name": "PRIVATE PROFILE", "city": "Private City"},
                headers=auth(OWNER),
            ).status_code
            == 200
        )
        assert client.get("/api/consul/requests", headers=auth(CONSUL)).json()["total"] == 0
        assert client.get(f"/api/workspace/cases/{cid}", headers=auth(CONSUL)).status_code == 404
        ticket = client.post(
            "/api/workspace/support",
            json={"summary": "SHARED summary", "case_id": cid},
            headers=auth(OWNER),
        ).json()["ticket"]
        tid = ticket["ticket_id"]
        queue = client.get("/api/consul/requests", headers=auth(CONSUL)).json()
        assert queue["total"] == 1 and queue["tickets"][0]["summary"] == "SHARED summary"
        assert "PRIVATE" not in json.dumps(queue) and cid not in json.dumps(queue)
        assert "case_id" not in queue["tickets"][0] and "escalation_id" not in queue["tickets"][0]
        assert client.get(f"/api/workspace/support/{tid}", headers=auth(OTHER)).status_code == 404
        assert (
            client.patch(
                f"/api/consul/requests/{tid}", json={"status": "in_review"}, headers=auth(CONSUL)
            ).status_code
            == 200
        )
        assert (
            client.get("/api/consul/requests?status=new", headers=auth(CONSUL)).json()["total"] == 0
        )
        assert (
            client.get(
                "/api/consul/requests?status=in_review&limit=1&offset=1", headers=auth(CONSUL)
            ).json()["tickets"]
            == []
        )
        reply = {"text": "CONSUL REPLY", "client_request_id": "retryable-reply"}
        for _ in range(2):
            response = client.post(
                f"/api/consul/requests/{tid}/replies", json=reply, headers=auth(CONSUL)
            )
            assert response.status_code == 200 and len(response.json()["ticket"]["replies"]) == 1
            assert "responder_id" not in response.text
        received = client.get(f"/api/workspace/support/{tid}", headers=auth(OWNER)).json()["ticket"]
        assert (
            received["replies"][0]["text"] == "CONSUL REPLY"
            and received["replies"][0]["role"] == "consul"
            and received["status"] == "waiting_for_user"
        )
        conflict = client.post(
            f"/api/consul/requests/{tid}/replies",
            json={**reply, "text": "Changed"},
            headers=auth(CONSUL),
        )
        assert conflict.status_code == 409
        assert (
            client.patch(
                f"/api/consul/requests/{tid}", json={"status": "resolved"}, headers=auth(CONSUL)
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/consul/requests/{tid}/replies",
                json={"text": "closed reply"},
                headers=auth(CONSUL),
            ).status_code
            == 409
        )
        assert (
            client.patch(
                f"/api/consul/requests/{tid}", json={"status": "in_review"}, headers=auth(CONSUL)
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/workspace/support/{tid}/replies",
                json={"text": "CITIZEN REPLY"},
                headers=auth(OWNER),
            ).status_code
            == 200
        )
        assert (
            client.get(f"/api/consul/requests/{tid}", headers=auth(CONSUL)).json()["ticket"][
                "replies"
            ][-1]["role"]
            == "citizen"
        )
        assert (
            client.get("/api/consul/requests?status=invalid", headers=auth(CONSUL)).status_code
            == 422
        )
    with TestClient(create_app(settings)) as client:
        restored = client.get(f"/api/consul/requests/{tid}", headers=auth(CONSUL)).json()["ticket"]
        assert len(restored["replies"]) == 2
        assert (
            client.get(f"/api/workspace/cases/{cid}", headers=auth(OWNER)).json()["case"]["title"]
            == "PRIVATE CASE"
        )
    # Revocation is a deployment decision and survives a new authentication service.
    revoked = settings.model_copy(update={"PILOT_ACCOUNT_TYPES": "{}"})
    with TestClient(create_app(revoked)) as client:
        assert client.get("/api/consul/requests", headers=auth(CONSUL)).status_code == 403


def test_local_previews_keep_distinct_stable_profiles_and_old_citizen_owner(tmp_path):
    settings = local_settings(OWNER, tmp_path, use_ollama=False)
    with TestClient(create_app(settings)) as client:
        client.headers.update(local_headers(settings))
        client.patch(
            "/api/workspace/profile", json={"city": "Original Citizen"}, headers=auth(OWNER)
        )
        for role in ("citizen", "consul"):
            result = client.post("/api/local-access/start", json={"account_type": role}).json()
            token = result["session_token"]
            profile = client.get("/api/workspace/profile", headers=auth(token)).json()
            assert (
                profile["account"]["account_type"] == role and profile["account"]["local_preview"]
            )
            assert profile["profile"]["city"] == ("Original Citizen" if role == "citizen" else None)
            client.patch(
                "/api/workspace/profile",
                json={"display_name": role, "position": "Staff" if role == "consul" else ""},
                headers=auth(token),
            )
        assert (
            client.post("/api/local-access/start", json={"account_type": "admin"}).status_code
            == 422
        )
    with TestClient(create_app(settings)) as client:
        client.headers.update(local_headers(settings))
        for role in ("citizen", "consul"):
            token = client.post("/api/local-access/start", json={"account_type": role}).json()[
                "session_token"
            ]
            assert (
                client.get("/api/workspace/profile", headers=auth(token)).json()["profile"][
                    "display_name"
                ]
                == role
            )
