"""Verified document meaning requires complete, privacy-safe original material."""

import base64
import json
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.cloud_ai.client import QwenCloudClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.memory.redaction import redact_sensitive_text

PERMISSION = "可以提交申请。"
RESTRICTION = "此许可已取消，请勿提交申请。"
PRIVATE_ORIGINAL = PERMISSION + "\nAddress: 123 Test Road, " + RESTRICTION
CHINESE_PRIVATE_ORIGINAL = PERMISSION + "\n地址：测试路123号，" + RESTRICTION
REDACTED_ORIGINAL = PERMISSION + "\n[REDACTED_ADDRESS]。"


@pytest.fixture
def cloud_endpoint(tmp_path):
    calls = []
    token = "document-integrity-participant-placeholder"
    settings = Settings(
        _env_file=None, QWEN_CHAT_ENABLED=True, QWEN_OCR_ENABLED=True,
        DASHSCOPE_API_KEY="unit-provider-placeholder",
        DASHSCOPE_BASE_URL="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        PILOT_ACCESS_TOKENS=json.dumps({"reader": token}),
        LOCAL_DATA_DIR=str(tmp_path), TRACE_DIR=str(tmp_path / "traces"),
        QWEN_DAILY_REQUEST_LIMIT=10,
    )

    def handle(request):
        content = json.loads(request.content)["messages"][-1]["content"]
        if isinstance(content, list):
            calls.append({"kind": "ocr"})
            output = PRIVATE_ORIGINAL
        else:
            payload = json.loads(content)
            calls.append(payload)
            if "passages" in payload:
                assert [p["text"] for p in payload["passages"]] == [RESTRICTION]
                output = json.dumps({"segments": [{
                    "passage_id": payload["passages"][0]["passage_id"],
                    "translation": "This permission has been cancelled; do not submit "
                                   "the application.",
                    "required_actions": ["Do not submit the application."],
                }]})
            else:
                assert payload["items"][0]["original_evidence"] == RESTRICTION
                output = json.dumps({"items": [{
                    "item_id": payload["items"][0]["item_id"], "supported": True,
                    "preserves_conditions": True, "complete": True, "relevant": True,
                    "safe": True, "correct_language": True,
                }]})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": output}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 10},
        })

    app = create_app(settings)
    app.state.cloud_client = QwenCloudClient(settings, httpx.MockTransport(handle))
    with TestClient(app, headers={"Authorization": "Bearer " + token}) as client:
        yield client, calls


def assert_original_withheld(result):
    assert result["mode"] == "document_limited"
    assert result["verification_status"] == "not_semantically_verified"
    assert result["metadata"]["cloud_status"] == "document_original_requires_review"
    assert result["metadata"]["original_requires_review"] is True
    assert result["metadata"]["provider_calls"] == 0
    assert not result["metadata"]["used_provider_call"]
    assert not result["metadata"]["used_network"]
    assert not result["segments"] and not result["required_actions"]
    assert result["explanation"] in result["warnings"]
    assert result["explanation"] in result["limitations"]
    assert PERMISSION not in result["explanation"]
    assert "You may submit" not in result["explanation"]


@pytest.mark.parametrize("language", ["en", "ru", "kk", "zh"])
@pytest.mark.parametrize("text", [
    PRIVATE_ORIGINAL, CHINESE_PRIVATE_ORIGINAL, REDACTED_ORIGINAL,
    PERMISSION + "\n[redacted_private]。",
])
def test_private_or_unavailable_original_is_withheld_before_cloud(
    cloud_endpoint, language, text,
):
    client, calls = cloud_endpoint
    response = client.post("/api/translate/explain", json={
        "text": text, "target_language": language,
    })
    assert response.status_code == 200
    result = response.json()
    assert_original_withheld(result)
    assert calls == []
    assert result["original_text"] == redact_sensitive_text(text)[0]
    assert "123 Test Road" not in response.text
    assert "测试路123号" not in response.text


@pytest.mark.parametrize("manual", [True, False])
def test_ocr_preview_to_document_handoff_does_not_verify_a_surviving_permission(
    cloud_endpoint, manual,
):
    client, calls = cloud_endpoint
    with BytesIO() as output:
        Image.new("RGB", (16, 16), "white").save(output, format="PNG")
        png = base64.b64encode(output.getvalue()).decode("ascii")
    preview = client.post("/api/photo-intake/preview", json={
        "image_base64": png, "content_type": "image/png",
        "allow_cloud_processing": not manual,
        "manual_transcription": PRIVATE_ORIGINAL if manual else None,
    })
    assert preview.status_code == 200
    photo = preview.json()
    assert photo["accepted"] and photo["not_trusted_evidence"]
    assert photo["extracted_text"] == REDACTED_ORIGINAL
    assert photo["ocr"]["text"] == REDACTED_ORIGINAL
    assert photo["ocr"]["provider"] == ("fake" if manual else "qwen")
    assert calls == ([] if manual else [{"kind": "ocr"}])
    response = client.post("/api/translate/explain", json={
        "text": photo["extracted_text"], "target_language": "en",
    })
    assert response.status_code == 200
    assert_original_withheld(response.json())
    # An OCR call may precede the handoff; document generation/review never run.
    assert calls == ([] if manual else [{"kind": "ocr"}])


def test_complete_clean_original_keeps_verified_conditions(cloud_endpoint):
    client, calls = cloud_endpoint
    response = client.post("/api/translate/explain", json={
        "text": RESTRICTION, "target_language": "en",
        "user_context": "private@example.org",
    })
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "cloud_verified"
    assert result["verification_status"] == "semantic_model_review"
    assert result["metadata"]["provider_calls"] == 2
    assert result["metadata"]["cloud_status"] == "generated"
    assert result["segments"][0]["original_quote"] == RESTRICTION
    assert "cancelled; do not submit" in result["explanation"]
    assert result["required_actions"] == [
        "The document states: Do not submit the application.",
    ]
    assert len(calls) == 2
    assert "private@example.org" not in json.dumps(calls)
    assert "private@example.org" not in response.text
