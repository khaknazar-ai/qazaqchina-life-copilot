"""Run the durable local workspace with one-step sign-in and local inference.

The launch credential exists only in process memory. Saved profiles and cases use
stable owner identifiers; local sign-in sessions expire when the backend stops.
"""

import argparse
import ctypes
import hashlib
import json
import os
import secrets
import socket
import sqlite3
import sys
from ctypes import wintypes
from pathlib import Path

from backend.app.admin_auth.permissions import (
    PERMISSION_SOURCE_CORPUS_REVIEW,
    permissions_for_roles,
)
from backend.app.admin_auth.service import build_admin_auth_service
from backend.app.config import Settings

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "local" / "personal-workspace"
ACTOR = "local-owner"
TARGET = (
    "QazaqChina/LocalWorkspace/"
    + hashlib.sha256(str(ROOT).casefold().encode("utf-8")).hexdigest()[:16]
)


class Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(wintypes.BYTE)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def access_code() -> str:
    """Legacy credential lookup; ordinary local startup does not call this helper."""
    if os.name != "nt":
        raise OSError("Windows Credential Manager is required")
    dll = ctypes.WinDLL("advapi32", use_last_error=True)
    pointer = ctypes.POINTER(Credential)
    dll.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(pointer),
    ]
    dll.CredReadW.restype = wintypes.BOOL
    dll.CredWriteW.argtypes = [pointer, wintypes.DWORD]
    dll.CredWriteW.restype = wintypes.BOOL
    dll.CredFree.argtypes = [ctypes.c_void_p]
    dll.CredFree.restype = None
    record = pointer()
    if dll.CredReadW(TARGET, 1, 0, ctypes.byref(record)):
        try:
            value = ctypes.string_at(
                record.contents.CredentialBlob, record.contents.CredentialBlobSize
            ).decode("ascii")
        finally:
            dll.CredFree(record)
        if not 32 <= len(value) <= 256 or not all(33 <= ord(c) <= 126 for c in value):
            raise ValueError("Stored local access code is invalid; it was not replaced")
        return value
    error = ctypes.get_last_error()
    if error != 1168:  # ERROR_NOT_FOUND; never retry an access denial elsewhere.
        raise OSError(error, "Windows Credential Manager read failed")
    value = secrets.token_urlsafe(32)
    blob = (wintypes.BYTE * len(value)).from_buffer_copy(value.encode("ascii"))
    record_value = Credential()
    record_value.Type = 1  # CRED_TYPE_GENERIC
    record_value.TargetName = TARGET
    record_value.UserName = ACTOR
    record_value.Comment = "QazaqChina local workspace access code"
    record_value.CredentialBlobSize = len(value)
    record_value.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(wintypes.BYTE))
    record_value.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE, scoped to this Windows user.
    if not dll.CredWriteW(ctypes.byref(record_value), 0):
        raise OSError(ctypes.get_last_error(), "Windows Credential Manager write failed")
    return value


def local_settings(
    code: str, data_dir: Path = DATA_DIR, *, use_ollama: bool = True,
    model: str = "qwen3.5:9b-q4_K_M",
    reviewed_sources: bool = False,
    local_ocr: bool = False,
    tesseract_cmd: str = "tesseract",
    tessdata_dir: str = "",
    ocr_languages: str = "chi_sim+eng+rus+kaz",
) -> Settings:
    """Use the existing owner and persistence gates; never load a project .env."""
    project = json.loads(
        (ROOT / "frontend" / "wechat-miniprogram" / "project.config.json").read_text(
            encoding="utf-8",
        )
    )
    devtools_referer = f"https://servicewechat.com/{project['appid']}/devtools/page-frame.html"
    settings = Settings(
        _env_file=None,
        APP_ENV="local",
        ENABLE_LOCAL_PERSISTENCE=True,
        LOCAL_DATA_DIR=str(data_dir),
        TRACE_DIR=str(data_dir / "traces"),
        PILOT_ACCESS_TOKENS=json.dumps({ACTOR: code}),
        PILOT_ACCOUNT_TYPES="{}",
        LOCAL_DEVICE_SIGNIN_ENABLED=True,
        LOCAL_DEVICE_SIGNIN_DEVTOOLS_REFERER=devtools_referer,
        LLM_DEFAULT_PROVIDER="mock",
        LLM_DEFAULT_MODEL="mock-qazaqchina-local",
        LLM_PROVIDER="fake",
        LLM_PROVIDER_ENABLED=False,
        LLM_ENABLE_EXTERNAL=False,
        USE_AGENT_WORKFLOW=True,
        AGENT_USE_LANGGRAPH=True,
        OLLAMA_CHAT_ENABLED=use_ollama,
        OLLAMA_BASE_URL="http://127.0.0.1:11434",
        OLLAMA_MODEL=model,
        OLLAMA_CONTEXT_TOKENS=8192,
        OLLAMA_MAX_TOKENS=1200,
        OLLAMA_TIMEOUT_SECONDS=120,
        QWEN_CHAT_ENABLED=False,
        QWEN_OCR_ENABLED=False,
        LOCAL_OCR_ENABLED=local_ocr,
        LOCAL_OCR_TESSERACT_CMD=tesseract_cmd,
        LOCAL_OCR_TESSDATA_DIR=tessdata_dir,
        LOCAL_OCR_LANGUAGES=ocr_languages,
        CLOUD_RETRIEVAL_ENABLED=False,
        QWEN_RERANK_ENABLED=False,
        SEMANTIC_CONFLICT_REVIEW_ENABLED=False,
        ADMIN_AUTH_ENABLED=False,
        SOURCE_CORPUS_READONLY_REVIEWERS_ENABLED=False,
        DASHSCOPE_API_KEY="",
        LLM_API_KEY="",
        ADMIN_AUTH_TOKEN="",
        ADMIN_REVIEW_AUTH_TOKEN="",
    )
    if reviewed_sources:
        settings = with_source_reviewers(settings)
    return settings


def with_source_reviewers(settings: Settings) -> Settings:
    """Read existing reviewer authority without enabling administrator APIs."""
    primary = (
        "ADMIN_AUTH_ENABLED", "ADMIN_AUTH_TOKEN", "ADMIN_AUTH_ACTOR_ID", "ADMIN_AUTH_ROLES",
    )
    secondary = (
        "ADMIN_REVIEW_AUTH_TOKEN", "ADMIN_REVIEW_AUTH_ACTOR_ID", "ADMIN_REVIEW_AUTH_ROLES",
    )
    message = "Reviewed sources require explicit, valid source-reviewer environment configuration."
    if any(not os.environ.get(key, "").strip() for key in primary):
        raise ValueError(message)
    has_secondary = any(os.environ.get(key, "").strip() for key in secondary)
    if has_secondary and any(not os.environ.get(key, "").strip() for key in secondary):
        raise ValueError(message)
    actor_keys = ("ADMIN_AUTH_ACTOR_ID",) + (
        ("ADMIN_REVIEW_AUTH_ACTOR_ID",) if has_secondary else ()
    )
    if any(os.environ[key] != os.environ[key].strip() for key in actor_keys):
        raise ValueError(message)
    # model_dump excludes secrets. Preserve every explicit base value instead, so
    # constructing Settings again cannot pick up unrelated process environment.
    values = {key: getattr(settings, key) for key in Settings.model_fields}
    for key in (*primary, *(secondary if has_secondary else ())):
        values[key] = os.environ[key]
    try:
        configured = Settings(_env_file=None, **values)
        auth = build_admin_auth_service(configured)
        if not auth.is_enabled() or not any(
            token.active and token.actor_id.strip() == token.actor_id and token.actor_id
            and PERMISSION_SOURCE_CORPUS_REVIEW in permissions_for_roles(token.roles)
            for token in auth.config.tokens
        ):
            raise ValueError(message)
    except ValueError:
        # Validation errors may contain inputs. Never echo credentials or chain
        # their validation details into the launcher's startup diagnostics.
        raise ValueError(message) from None
    return configured.model_copy(update={
        "ADMIN_AUTH_ENABLED": False, "SOURCE_CORPUS_READONLY_REVIEWERS_ENABLED": True,
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3.5:9b-q4_K_M",
                        help="An already installed local Ollama model; never downloaded.")
    parser.add_argument("--mock", action="store_true",
                        help="Offline local preview; does not run a real model.")
    parser.add_argument("--local-ocr", action="store_true",
                        help="Enable local Tesseract OCR; do not send photos to cloud OCR.")
    parser.add_argument("--tesseract", default="tesseract",
                        help="Tesseract executable name or full path (default: tesseract on PATH).")
    parser.add_argument("--tessdata-dir", default="",
                        help="Optional path to Tesseract language data (tessdata).")
    parser.add_argument("--ocr-languages", default="chi_sim+eng+rus+kaz",
                        help="Languages joined by + (default: chi_sim+eng+rus+kaz).")
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument(
        "--reviewed-sources", action="store_true",
        help="Read existing source-reviewer configuration; no admin access or automatic approval.",
    )
    sources.add_argument(
        "--demo-sources", action="store_true",
        help="Approve prepared materials in a separate local MVP simulation; no expert review.",
    )
    args = parser.parse_args(argv)
    # Help requires no console, credential lookup, server or model connection.
    if not sys.stdout.isatty():
        print("Open START_LOCAL_WORKSPACE.cmd in an interactive console.", file=sys.stderr)
        return 2
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8000)) == 0:
            print(
                "Port 8000 is occupied. No process was stopped. Close the previous backend first."
            )
            return 2
    if not DATA_DIR.resolve().is_relative_to(ROOT.resolve()):
        print("The local storage path must remain inside this project.")
        return 2
    try:
        code = secrets.token_urlsafe(48)
        import uvicorn

        from backend.app.main import create_app

        demo_receipt = None
        directory = ROOT / "data/local/mvp-source-demo" if args.demo_sources else DATA_DIR
        settings = local_settings(
            code, data_dir=directory, use_ollama=not args.mock, model=args.model,
            reviewed_sources=args.reviewed_sources,
            local_ocr=args.local_ocr,
            tesseract_cmd=args.tesseract,
            tessdata_dir=args.tessdata_dir,
            ocr_languages=args.ocr_languages,
        )
        if args.demo_sources:
            from scripts.mvp_source_demo import prepare_demo_sources

            settings, demo_receipt = prepare_demo_sources(settings)
        application = create_app(settings)
        if demo_receipt is not None:
            application.state.source_review_mode = "local_mvp_simulation"
            receipt_path = directory / "source-demo-receipt.local.json"
            receipt_path.write_text(json.dumps(demo_receipt, indent=2), encoding="utf-8")
    except (OSError, ValueError, sqlite3.Error) as error:
        error_code = getattr(error, "winerror", None) or getattr(error, "errno", None)
        print(
            f"Local startup failed ({type(error).__name__}; Windows code {error_code}). "
            "No security settings were changed."
        )
        return 2
    inference = "TEST ONLY / mock AI" if args.mock else "Ollama / " + settings.OLLAMA_MODEL
    print("QminiGuide LOCAL WORKSPACE | persistent storage | " + inference)
    if settings.LOCAL_OCR_ENABLED:
        print("Photo OCR: local Tesseract | " + settings.LOCAL_OCR_LANGUAGES)
    else:
        print("Photo OCR: manual/demo mode; use --local-ocr to enable Tesseract")
    if demo_receipt is not None:
        print("MVP source approvals: simulation only; independent expert review is not performed.")
    print("Profile > Sign in. No access code or confirmation window.")
    print("Single-user development mode: use only on your own computer.")
    print("Keep this window open. Closing it stops the backend; saved cases remain on disk.")
    uvicorn.run(
        application, host="127.0.0.1", port=8000, workers=1, access_log=False, log_level="info"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
