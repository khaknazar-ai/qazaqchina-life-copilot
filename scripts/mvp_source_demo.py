"""User-authorized local MVP approvals; never independent human/expert review."""

import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.source_corpus.intake import repository_path
from backend.app.source_corpus.models import CorpusPacket

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "data/local/mvp-source-demo"
PREPARED = ROOT / "data/local/source_review_20261024/selected-demo-packets.local.json"
ACTORS = ("mvp-demo-reviewer-one", "mvp-demo-reviewer-two")
NOTE = (
    "User-authorized local MVP simulation. One automation operated both demo accounts; "
    "this is not independent human or expert review. Reuse is assumed for local testing "
    "only, not a redistribution license. Do not migrate these approvals to real service."
)


def prepare_demo_sources(
    settings: Settings,
    *,
    prepared: Path = PREPARED,
    demo_root: Path = DEMO_DIR,
) -> tuple[Settings, dict]:
    """Exercise real authenticated API gates in separate, ignored demonstration storage."""
    directory = repository_path(ROOT, demo_root)
    test_scratch = (ROOT / ".pytest_cache").resolve()
    if directory != DEMO_DIR.resolve() and not (
        directory.is_relative_to(test_scratch) and directory.name == "mvp-source-demo"
    ):
        raise ValueError(
            'MVP source storage must use the local demo directory or an ' \
            'isolated pytest scratch directory'
        )
    if Path(settings.LOCAL_DATA_DIR).resolve() != directory:
        raise ValueError("MVP sources cannot change or overwrite the personal workspace")
    if settings.APP_ENV != "local" or not settings.ENABLE_LOCAL_PERSISTENCE:
        raise ValueError("MVP source approval is local and persistent only")
    if any(
        (
            settings.LLM_ENABLE_EXTERNAL,
            settings.QWEN_CHAT_ENABLED,
            settings.QWEN_OCR_ENABLED,
            settings.CLOUD_RETRIEVAL_ENABLED,
            settings.QWEN_RERANK_ENABLED,
            settings.SEMANTIC_CONFLICT_REVIEW_ENABLED,
            settings.LLM_PROVIDER_ENABLED,
        )
    ):
        raise ValueError("MVP source approval cannot enable external providers")
    source_file = repository_path(ROOT, prepared)
    if source_file.stat().st_size > 128_000:
        raise ValueError("MVP source packet input exceeds the limit")
    value = json.loads(source_file.read_text(encoding="utf-8"))
    if value.get("runtime_import_allowed") is not False or value.get("human_reviewed") is not False:
        raise ValueError("MVP input must explicitly declare pending non-human-reviewed material")
    packets = [CorpusPacket.model_validate(item) for item in value["packets"]]
    if not 1 <= len(packets) <= 3 or len({p.candidate_id for p in packets}) != len(packets):
        raise ValueError("MVP input requires one to three distinct source packets")
    if any(
        p.status != "pending" or p.allow_ai_retrieval or not 300 <= len(p.text) <= 2400
        for p in packets
    ):
        raise ValueError("MVP approval requires complete, bounded pending text")
    passages = value.get("answer_passages", {})
    if set(passages) != {p.source_id for p in packets} or any(
        not isinstance(passages[p.source_id], list) or not passages[p.source_id] for p in packets
    ):
        raise ValueError("MVP input requires explicitly selected exact answer passages")

    # Tokens exist only in this process. Actors and notes explicitly identify the
    # demonstration; two accounts demonstrate the gate, not independent people.
    tokens = (secrets.token_urlsafe(32), secrets.token_urlsafe(32))
    configured = settings.model_copy(
        update={
            "ADMIN_AUTH_TOKEN": SecretStr(tokens[0]),
            "ADMIN_AUTH_ACTOR_ID": ACTORS[0],
            "ADMIN_AUTH_ROLES": "source_publisher",
            "ADMIN_REVIEW_AUTH_TOKEN": SecretStr(tokens[1]),
            "ADMIN_REVIEW_AUTH_ACTOR_ID": ACTORS[1],
            "ADMIN_REVIEW_AUTH_ROLES": "source_reviewer",
        }
    )
    operator = configured.model_copy(
        update={
            "ADMIN_AUTH_ENABLED": True,
            "LOCAL_DEVICE_SIGNIN_ENABLED": False,
            "SOURCE_CORPUS_READONLY_REVIEWERS_ENABLED": False,
            "OLLAMA_CHAT_ENABLED": False,
        }
    )
    packet_dir = directory / "source_corpus/packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    packet_file = packet_dir / "review_packets-mvp.local.json"
    encoded = json.dumps(
        {"runtime_import_allowed": False, "packets": value["packets"], "answer_passages": passages},
        ensure_ascii=False,
        sort_keys=True,
    )
    if packet_file.exists() and packet_file.read_text(encoding="utf-8") != encoded:
        raise ValueError("Existing MVP originals changed; explicit review reset is required")
    if not packet_file.exists():
        packet_file.write_text(encoded, encoding="utf-8")
    application = create_app(operator)
    headers = [{"Authorization": "Bearer " + token} for token in tokens]
    receipt = {
        "mode": "local_mvp_simulation",
        "independent_human_review": False,
        "expert_review": False,
        "published_sources": [],
        "operations": [],
    }

    def call(client, suffix, body, account=0, expected=200):
        response = client.post(
            "/api/admin/source-corpus" + suffix, json=body, headers=headers[account]
        )
        receipt["operations"].append(
            {"operation": suffix.rsplit("/", 1)[-1], "status": response.status_code}
        )
        if response.status_code != expected:
            raise ValueError("MVP source API rejected an operation; no fallback approval was used")
        return response.json()

    try:
        with TestClient(application, client=("127.0.0.1", 42000)) as client:
            existing = {
                s.revision.packet.source_id: s
                for s in application.state.source_corpus_service.list_states()
            }
            for packet in packets:
                state = existing.get(packet.source_id)
                if state is not None:
                    if (
                        state.revision.packet != packet
                        or state.status != "approved"
                        or {a["actor_id"] for a in state.approvals} != set(ACTORS)
                        or any(
                            a["review"]["note"] != NOTE
                            or a["review"]["answer_passages"] != passages[packet.source_id]
                            for a in state.approvals
                        )
                    ):
                        raise ValueError(
                            "MVP review state changed; no automatic reapproval is allowed"
                        )
                    continue
                revision = call(client, "/stage", {"candidate_id": packet.candidate_id})["revision"]
                decision = {
                    "expected_revision_hash": revision["revision_hash"],
                    "expected_text_sha256": packet.text_sha256,
                    "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                    "scenario": "study" if "study" in packet.topics else "housing",
                    "city": "Shanghai" if "study" in packet.topics else "China",
                    "risk_tags": ["legal_sensitive"],
                    "answer_passages": passages[packet.source_id],
                    "answer_passages_complete": True,
                    "publisher_verified": True,
                    "full_text_verified": True,
                    "applicability_verified": True,
                    "dates_verified": True,
                    "reuse_verified": True,
                    "note": NOTE,
                }
                rid = revision["revision_id"]
                call(client, f"/{rid}/review", decision)
                call(
                    client,
                    f"/{rid}/publish",
                    {"expected_revision_hash": revision["revision_hash"]},
                    expected=409,
                )
                call(client, f"/{rid}/review", decision, account=1)
                call(
                    client,
                    f"/{rid}/publish",
                    {
                        "expected_revision_hash": revision["revision_hash"],
                    },
                )
            active = application.state.source_corpus_service.active_sources()
            if {s.source_id for s in active} != {p.source_id for p in packets}:
                raise ValueError("MVP sources are expired, revoked or changed; startup stops")
            receipt["published_sources"] = [
                {"source_id": s.source_id, "url": s.url, "content_hash": s.content_hash}
                for s in active
            ]
    finally:
        application.state.source_corpus_service.close()
    # Citizen HTTP authority stays disabled; the reader cannot mutate this ledger.
    return configured.model_copy(
        update={
            "ADMIN_AUTH_ENABLED": False,
            "SOURCE_CORPUS_READONLY_REVIEWERS_ENABLED": True,
        }
    ), receipt
