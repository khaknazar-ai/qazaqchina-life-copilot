"""One-step local development login, ownership and browser ingress boundaries."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.api_utils.local_device_signin import LocalDeviceSignin
from backend.app.api_utils.pilot_access import PilotAccessService
from backend.app.api_utils.request_guard import _local_signin_origin
from backend.app.main import create_app
from scripts.run_local_workspace import local_settings

CODE = "isolated-local-device-test-owner-code"


def _headers(settings):
    return {
        "Referer": settings.LOCAL_DEVICE_SIGNIN_DEVTOOLS_REFERER,
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "X-Q-Local-Access": "devtools",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"APP_ENV": "production"},
        {"ENABLE_LOCAL_PERSISTENCE": False},
        {"LOCAL_DEVICE_SIGNIN_ENABLED": False},
        {"LOCAL_DEVICE_SIGNIN_DEVTOOLS_REFERER": ""},
        {"ADMIN_AUTH_ENABLED": True},
        {"LLM_ENABLE_EXTERNAL": True},
        {"QWEN_CHAT_ENABLED": True},
        {"CLOUD_RETRIEVAL_ENABLED": True},
        {
            "PILOT_ACCESS_TOKENS": SecretStr(
                '{"someone-else":"isolated-other-actor-test-credential"}'
            )
        },
    ],
)
def test_local_login_is_not_a_public_or_privileged_identity_provider(tmp_path, change):
    settings = local_settings(CODE, tmp_path, use_ollama=False).model_copy(update=change)
    with pytest.raises(ValueError):
        LocalDeviceSignin(settings, PilotAccessService(settings))


def test_one_request_login_preserves_owner_logout_and_relogin(tmp_path):
    settings = local_settings(CODE, tmp_path, use_ollama=False)
    with TestClient(create_app(settings)) as client:
        client.headers.update(_headers(settings))
        assert client.get("/api/workspace/profile").status_code == 401
        assert client.get("/api/capabilities").json()["feature_flags"]["local_device_signin"]
        old_headers = {"Authorization": "Bearer " + CODE}
        assert (
            client.patch(
                "/api/workspace/profile", json={"city": "UNIT city"}, headers=old_headers
            ).status_code
            == 200
        )
        first = client.post("/api/local-access/start", json={})
        assert first.status_code == 200 and first.headers["cache-control"] == "no-store"
        assert first.headers["pragma"] == "no-cache"
        assert first.json()["expires_in_seconds"] == 7200
        assert "request_id" not in first.json() and CODE not in first.text
        token = first.json()["session_token"]
        access = client.app.state.pilot_access_service
        principal = access.authenticate("Bearer " + token)
        assert principal.actor_id == "local-owner"
        assert principal.session_id("example") == access.authenticate("Bearer " + CODE).session_id(
            "example"
        )
        auth = {"Authorization": "Bearer " + token}
        session = client.post("/api/workspace/session", json={}, headers=auth).json()
        assert session["persistent"] and session["owner_scope"] == "authenticated_pilot"
        assert (
            client.get("/api/workspace/profile", headers=auth).json()["profile"]["city"]
            == "UNIT city"
        )
        assert client.get("/api/admin/human-support/feedback", headers=auth).status_code == 403
        assert client.post("/api/local-access/logout", json={}, headers=auth).status_code == 200
        assert client.get("/api/workspace/profile", headers=auth).status_code == 401
        second = client.post("/api/local-access/start", json={})
        assert second.status_code == 200 and second.json()["session_token"] != token
        # No dialog/ticket lock exists, even on an immediate repeat request.
        assert client.post("/api/local-access/start", json={}).status_code == 200
        assert (
            client.post("/api/local-access/poll", json={}, headers=old_headers).status_code == 404
        )
        assert client.get("/api/workspace/profile", headers=old_headers).status_code == 200


def test_login_after_backend_restart_restores_the_same_profile(tmp_path):
    settings = local_settings(CODE, tmp_path, use_ollama=False)
    with TestClient(create_app(settings)) as client:
        client.headers.update(_headers(settings))
        token = client.post("/api/local-access/start", json={}).json()["session_token"]
        assert (
            client.patch(
                "/api/workspace/profile",
                json={"city": "UNIT restart"},
                headers={"Authorization": "Bearer " + token},
            ).status_code
            == 200
        )
        auth = {"Authorization": "Bearer " + token}
        case = client.post(
            "/api/workspace/cases", json={"title": "Fictional restart case", "scenario": "study"},
            headers=auth,
        ).json()["case"]
        path = "/api/workspace/cases/" + case["case_id"]
        assert client.post(path + "/documents", headers=auth, json={
            "title": "Meeting notice", "text": "Meeting in Room B at 10:00.", "confirmed": True,
        }).status_code == 200
    restarted = local_settings(
        "rotated-in-memory-startup-credential-0000", tmp_path, use_ollama=False,
    )
    with TestClient(create_app(restarted)) as client:
        client.headers.update(_headers(restarted))
        assert (
            client.get(
                "/api/workspace/profile", headers={"Authorization": "Bearer " + token}
            ).status_code
            == 401
        )
        new_token = client.post("/api/local-access/start", json={}).json()["session_token"]
        assert (
            client.get(
                "/api/workspace/profile", headers={"Authorization": "Bearer " + new_token}
            ).json()["profile"]["city"]
            == "UNIT restart"
        )
        restored = client.get(path, headers={"Authorization": "Bearer " + new_token}).json()["case"]
        assert restored["documents"][0]["text"] == "Meeting in Room B at 10:00."


@pytest.mark.parametrize(
    "header,value",
    [
        ("referer", "https://evil.invalid/"),
        (
            "referer",
            "https://servicewechat.com.evil.invalid/wx0123456789abcdef/devtools/page-frame.html",
        ),
        ("referer", "https://servicewechat.com/wx0123456789abcdef/devtools/page-frame.html"),
        ("origin", "https://servicewechat.com"),
        ("x-q-local-access", ""),
        ("host", "evil.invalid"),
    ],
)
def test_browser_and_wrong_project_requests_are_rejected(tmp_path, header, value):
    settings = local_settings(CODE, tmp_path, use_ollama=False)
    with TestClient(create_app(settings)) as client:
        headers = _headers(settings)
        headers = {k.lower(): v for k, v in headers.items()}
        headers[header] = value
        assert client.post("/api/local-access/start", json={}, headers=headers).status_code == 403
        assert client.app.state.pilot_access_service._local_sessions == {}


@pytest.mark.parametrize(
    "header", ["Referer", "X-Q-Local-Access"]
)
def test_missing_or_duplicate_request_markers_are_rejected(tmp_path, header):
    settings = local_settings(CODE, tmp_path)
    pairs = [(k.lower().encode(), v.encode()) for k, v in _headers(settings).items()]
    pairs += [(b"host", b"127.0.0.1:8000"), (b"content-type", b"application/json")]
    scope = {"client": ("127.0.0.1", 123), "headers": pairs}
    assert _local_signin_origin(scope, settings.LOCAL_DEVICE_SIGNIN_DEVTOOLS_REFERER)
    marker = header.lower().encode()
    removed = [p for p in pairs if p[0] != marker]
    duplicate = pairs + [next(p for p in pairs if p[0] == marker)]
    for invalid in (removed, duplicate):
        assert not _local_signin_origin(
            dict(scope, headers=invalid), settings.LOCAL_DEVICE_SIGNIN_DEVTOOLS_REFERER
        )
    assert not _local_signin_origin(
        dict(scope, client=("203.0.113.8", 123)), settings.LOCAL_DEVICE_SIGNIN_DEVTOOLS_REFERER
    )


def test_native_miniprogram_request_does_not_need_browser_fetch_metadata(tmp_path):
    settings = local_settings(CODE, tmp_path)
    headers = [
        (b"host", b"127.0.0.1:8000"),
        (b"content-type", b"application/json"),
        (b"referer", settings.LOCAL_DEVICE_SIGNIN_DEVTOOLS_REFERER.encode("ascii")),
        (b"x-q-local-access", b"devtools"),
    ]
    assert _local_signin_origin(
        {"client": ("127.0.0.1", 123), "headers": headers},
        settings.LOCAL_DEVICE_SIGNIN_DEVTOOLS_REFERER,
    )


def test_client_cannot_supply_identity_and_disabled_mode_has_no_public_login(tmp_path):
    settings = local_settings(CODE, tmp_path, use_ollama=False)
    with TestClient(create_app(settings)) as client:
        client.headers.update(_headers(settings))
        for extra in ({"actor_id": "verified_consul"}, {"approved": True}):
            assert client.post("/api/local-access/start", json=extra).status_code == 422
        assert (
            client.post(
                "/api/local-access/start", content="{}", headers={"Content-Type": "text/plain"}
            ).status_code
            == 403
        )
        assert (
            client.options(
                "/api/local-access/start", headers={"Origin": "https://evil.invalid"}
            ).status_code
            == 401
        )
        assert client.app.state.pilot_access_service._local_sessions == {}
    disabled = settings.model_copy(update={"LOCAL_DEVICE_SIGNIN_ENABLED": False})
    with TestClient(create_app(disabled)) as client:
        assert (
            client.post("/api/local-access/start", json={}, headers=_headers(settings)).status_code
            == 401
        )


def test_session_expiry_revocation_and_bounds(tmp_path):
    settings = local_settings(CODE, tmp_path)
    access = PilotAccessService(settings)
    access._session_clock = lambda: 100.0
    token = access.issue_local_session()
    assert access.authenticate("Bearer " + token) is not None
    assert PilotAccessService(settings).authenticate("Bearer " + token) is None
    access.revoke_local_session("Bearer " + token)
    assert access.authenticate("Bearer " + token) is None
    token = access.issue_local_session()
    access._session_clock = lambda: 7300.0
    assert access.authenticate("Bearer " + token) is None
    for _ in range(32):
        access.issue_local_session()
    with pytest.raises(HTTPException) as limit:
        access.issue_local_session()
    assert limit.value.status_code == 429
    assert access.authenticate("Bearer " + CODE) is not None
