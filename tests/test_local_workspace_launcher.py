"""Local launcher persistence contracts; these are not UI persona walkthroughs."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.main import create_app
from scripts.run_local_workspace import ACTOR, local_settings

CODE = "test-only-local-workspace-access-code"


def test_explicit_mock_mode_ignores_external_environment(monkeypatch, tmp_path):
    for key in [
        "OLLAMA_CHAT_ENABLED",
        "QWEN_CHAT_ENABLED",
        "QWEN_OCR_ENABLED",
        "CLOUD_RETRIEVAL_ENABLED",
        "SEMANTIC_CONFLICT_REVIEW_ENABLED",
    ]:
        monkeypatch.setenv(key, "true")
    monkeypatch.setenv("ENABLE_LOCAL_PERSISTENCE", "false")
    settings = local_settings(CODE, tmp_path, use_ollama=False)
    assert settings.ENABLE_LOCAL_PERSISTENCE
    assert settings.LOCAL_DATA_DIR == str(tmp_path)
    assert settings.APP_ENV == "local"
    assert settings.LLM_DEFAULT_PROVIDER == "mock"
    assert not any(
        [
            settings.OLLAMA_CHAT_ENABLED,
            settings.QWEN_CHAT_ENABLED,
            settings.QWEN_OCR_ENABLED,
            settings.CLOUD_RETRIEVAL_ENABLED,
            settings.SEMANTIC_CONFLICT_REVIEW_ENABLED,
            settings.LLM_ENABLE_EXTERNAL,
            settings.LLM_PROVIDER_ENABLED,
        ]
    )
    assert not settings.ADMIN_AUTH_ENABLED
    assert settings.LLM_API_KEY == ""
    assert settings.DASHSCOPE_API_KEY.get_secret_value() == ""
    create_app(settings)  # Existing runtime validation must remain enabled.


def test_local_ocr_requires_explicit_launcher_configuration(tmp_path):
    settings = local_settings(
        CODE,
        tmp_path,
        use_ollama=False,
        local_ocr=True,
        tesseract_cmd=r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        tessdata_dir=r"C:\Program Files\Tesseract-OCR\tessdata",
        ocr_languages="chi_sim+eng+rus+kaz",
    )

    assert settings.LOCAL_OCR_ENABLED is True
    assert settings.LOCAL_OCR_TESSERACT_CMD.endswith("tesseract.exe")
    assert settings.LOCAL_OCR_TESSDATA_DIR.endswith("tessdata")
    assert settings.LOCAL_OCR_LANGUAGES == "chi_sim+eng+rus+kaz"
    assert settings.QWEN_OCR_ENABLED is False


def test_launcher_defaults_to_loopback_ollama_with_same_durable_owner(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("OLLAMA_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("OLLAMA_MODEL", "unwanted-cloud")
    monkeypatch.setenv("QWEN_CHAT_ENABLED", "true")
    monkeypatch.setenv("LLM_ENABLE_EXTERNAL", "true")
    settings = local_settings(CODE, tmp_path)
    assert settings.OLLAMA_CHAT_ENABLED
    assert settings.OLLAMA_BASE_URL == "http://127.0.0.1:11434"
    assert settings.OLLAMA_MODEL == "qwen3.5:9b-q4_K_M"
    assert not settings.LLM_ENABLE_EXTERNAL
    assert not settings.QWEN_CHAT_ENABLED
    assert not settings.QWEN_OCR_ENABLED
    assert not settings.CLOUD_RETRIEVAL_ENABLED
    assert not settings.QWEN_RERANK_ENABLED
    assert not settings.SEMANTIC_CONFLICT_REVIEW_ENABLED
    assert settings.PILOT_ACCESS_TOKENS.get_secret_value() == local_settings(
        CODE, tmp_path, use_ollama=False
    ).PILOT_ACCESS_TOKENS.get_secret_value()
    with TestClient(create_app(settings)) as client:
        health = client.get("/health").json()
        assert health["llm_provider"] == "ollama"
        assert health["llm_model"] == "qwen3.5:9b-q4_K_M"
        capabilities = client.get("/api/capabilities").json()
        assert capabilities["local_persistence_enabled"] is True
        assert capabilities["external_llm_enabled"] is False
        assert client.post("/api/workspace/session", json={}).status_code == 401
        session = client.post("/api/workspace/session", json={}, headers={
            "Authorization": "Bearer " + CODE,
        }).json()
        assert session["persistent"] is True
        assert session["owner_scope"] == "authenticated_pilot"


def test_workspace_survives_separate_process_restart_and_requires_login(tmp_path):
    child = r"""
import json, sys
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.main import create_app
from scripts.run_local_workspace import local_settings

root = Path(sys.argv[1])
mode = sys.argv[2]
code = "test-only-local-workspace-access-code"
with TestClient(create_app(local_settings(code, root / "store", use_ollama=False))) as c:
    assert c.post("/api/workspace/session", json={}).status_code == 401
    headers = {"Authorization": "Bearer " + code}
    session = c.post("/api/workspace/session", json={}, headers=headers).json()
    assert session["persistent"] is True and session["mode"] == "pilot"
    if mode == "create":
        assert (
            c.patch(
                "/api/workspace/profile", headers=headers, json={"city": "UNIT city"}
            ).status_code
            == 200
        )
        response = c.post(
            "/api/workspace/cases",
            headers=headers,
            json={"title": "UNIT persistence; not a persona", "scenario": "study"},
        )
        assert response.status_code == 200, response.text
        cid = response.json()["case"]["case_id"]
        path = "/api/workspace/cases/" + cid
        assert (
            c.post(
                path + "/tasks",
                headers=headers,
                json={"title": "UNIT action", "due_at": "2026-11-01"},
            ).status_code
            == 200
        )
        assert (
            c.post(
                path + "/documents",
                headers=headers,
                json={
                    "title": "UNIT document",
                    "text": "Original fictional unit notice",
                    "confirmed": True,
                },
            ).status_code
            == 200
        )
        assert (
            c.post(
                path + "/messages",
                headers=headers,
                json={"kind": "note", "text": "UNIT draft; not sent"},
            ).status_code
            == 200
        )
        (root / "case-id.json").write_text(json.dumps({"case_id": cid}))
    else:
        cid = json.loads((root / "case-id.json").read_text())["case_id"]
        path = "/api/workspace/cases/" + cid
        assert (
            c.get(
                path, headers={"Authorization": "Bearer invalid-fixture"}
            ).status_code
            == 401
        )
        response = c.get(path, headers=headers)
        assert response.status_code == 200, response.text
        item = response.json()["case"]
        assert item["title"] == "UNIT persistence; not a persona"
        assert item["tasks"][0]["due_at"] == "2026-11-01"
        assert item["documents"][0]["text"] == "Original fictional unit notice"
        assert item["messages"][0]["text"] == "UNIT draft; not sent"
        assert (
            c.get("/api/workspace/profile", headers=headers).json()["profile"]["city"]
            == "UNIT city"
        )
    print(mode + " PASS (technical test, not UI acceptance)")
"""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for mode in ["create", "restore"]:
        result = subprocess.run(
            [sys.executable, "-c", child, str(tmp_path), mode],
            capture_output=True,
            text=True,
            timeout=45,
            env=env,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert mode + " PASS" in result.stdout


def test_noninteractive_launcher_never_reads_or_prints_access_code(monkeypatch, capsys):
    import scripts.run_local_workspace as launcher

    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

    def forbidden():
        raise AssertionError("No secret access from captured command output")

    monkeypatch.setattr(launcher, "access_code", forbidden)
    assert launcher.main([]) == 2
    assert "interactive console" in capsys.readouterr().err


def test_normal_launcher_uses_memory_only_credentials(monkeypatch, tmp_path, capsys):
    import uvicorn

    import scripts.run_local_workspace as launcher

    settings = local_settings(CODE, tmp_path / "store", use_ollama=False)
    credentials, starts = [], []

    class FreePort:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def connect_ex(self, address):
            return 1

    def forbidden():
        raise AssertionError("Normal startup must not open the credential vault")

    def configure(code, **kwargs):
        credentials.append(code)
        assert kwargs["data_dir"] == tmp_path / "store"
        return settings

    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "DATA_DIR", tmp_path / "store")
    monkeypatch.setattr(launcher.socket, "socket", FreePort)
    monkeypatch.setattr(launcher, "access_code", forbidden)
    monkeypatch.setattr(launcher, "local_settings", configure)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(uvicorn, "run", lambda application, **kwargs: starts.append(kwargs))
    assert launcher.main(["--mock"]) == 0
    assert launcher.main(["--mock"]) == 0
    assert len(starts) == 2 and starts[0]["host"] == "127.0.0.1"
    assert len(set(credentials)) == 2 and all(len(code) >= 32 for code in credentials)
    output = capsys.readouterr().out
    assert all(code not in output for code in credentials)


@pytest.mark.skipif(os.name != "nt", reason="Windows credential error contract")
def test_credential_access_denial_has_no_fallback_or_write(monkeypatch):
    import ctypes

    import scripts.run_local_workspace as launcher

    class Function:
        def __init__(self, result):
            self.result = result

        def __call__(self, *args):
            return self.result(*args)

    def denied(*args):
        ctypes.set_last_error(5)
        return False

    def forbidden(*args):
        raise AssertionError("Must stop on a credential-manager denial")

    class DeniedVault:
        CredReadW = Function(denied)
        CredWriteW = Function(forbidden)
        CredFree = Function(forbidden)

    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: DeniedVault())
    with pytest.raises(OSError) as error:
        launcher.access_code()
    assert error.value.errno == 5


def test_owner_namespace_is_fixed_for_this_local_workspace():
    assert ACTOR == "local-owner"


def test_launcher_help_requires_no_console_credentials_or_backend(monkeypatch, capsys):
    import scripts.run_local_workspace as launcher

    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)

    def forbidden():
        raise AssertionError("Help must not access stored credentials")

    monkeypatch.setattr(launcher, "access_code", forbidden)
    with pytest.raises(SystemExit) as result:
        launcher.main(["--help"])
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert "--mock" in help_text
    assert "--local-ocr" in help_text
    assert "--tesseract" in help_text


@pytest.mark.skipif(os.name != "nt", reason="Windows command launcher")
def test_windows_launcher_forwards_arguments_to_selected_python():
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, QMINIGUIDE_PYTHON=sys.executable)
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(root / "START_LOCAL_WORKSPACE.cmd"), "--help"],
        env=env, capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert all(option in result.stdout for option in ["--mock", "--model", "--local-ocr"])


@pytest.mark.skipif(os.name != "nt", reason="Windows command launcher")
@pytest.mark.parametrize("explicit", [False, True])
def test_windows_launcher_missing_environment_explains_setup_without_fallback(tmp_path, explicit):
    root = Path(__file__).resolve().parents[1]
    launcher = tmp_path / "START_LOCAL_WORKSPACE.cmd"
    launcher.write_bytes((root / launcher.name).read_bytes())
    env = dict(os.environ)
    env.pop("QMINIGUIDE_PYTHON", None)
    if explicit:
        env["QMINIGUIDE_PYTHON"] = str(tmp_path / "missing-python.exe")
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(launcher)],
        env=env, capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    assert result.returncode == 2
    assert ("QMINIGUIDE_PYTHON" if explicit else "README.md") in result.stdout
    assert not (tmp_path / ".venv").exists()
