"""A request-local capability issued only after the typed semantic review call.

It is never a request schema field or a metadata flag. Its exact claims,
passages, citations, full source snapshots and rendered answer are rebound at
delivery. Model approval cannot exempt the separate explicit safety checks.
"""

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field, replace

from backend.app.cloud_ai.answer_contract import CloudAnswer, SourcePassage
from backend.app.cloud_ai.claim_safety import (
    claim_preserves_details,
    claim_preserves_explicit_safety,
)
from backend.app.cloud_ai.client import CloudAIError
from backend.app.cloud_ai.semantic_review import CloudOperation, review_items
from backend.app.domain.sources import Citation, SourceReference
from backend.app.embeddings.safety import eligible_cloud_source

# Process-local signing material, never persisted or exposed through a schema.
_SIGNING_KEY = secrets.token_bytes(32)


def source_digest(source: SourceReference) -> str:
    return hashlib.sha256(json.dumps(
        source.model_dump(mode="json"), sort_keys=True, ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def _citation_pool(citations: list[Citation]) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(sorted((c.citation_id, c.source_id, c.claim, c.supporting_quote or "")
                        for c in citations))


@dataclass(frozen=True)
class BoundClaimReview:
    claims: tuple[str, ...]
    passages: tuple[tuple[str, str, str], ...]
    source_snapshots: tuple[tuple[str, str], ...]
    citations: tuple[tuple[str, str, str, str], ...]
    answer_hash: str = ""
    _signature: str = field(default="", repr=False)

    def _signed_payload(self) -> bytes:
        return json.dumps((self.claims, self.passages, self.source_snapshots,
                           self.citations, self.answer_hash), ensure_ascii=False).encode("utf-8")

    def _issued(self) -> bool:
        expected = hmac.new(_SIGNING_KEY, self._signed_payload(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(self._signature, expected)

    def bind_answer(self, answer: str) -> "BoundClaimReview":
        if not self._issued():
            raise CloudAIError("cloud_review_binding_rejected", attempted=True)
        return _sign(replace(self, answer_hash=hashlib.sha256(answer.encode("utf-8")).hexdigest()))

    def valid_for(self, answer: str, evidence: list[dict], citations: list[Citation],
                  *, risk_level: str | None) -> bool:
        if not self._issued() or self.answer_hash != hashlib.sha256(
            answer.encode("utf-8"),
        ).hexdigest() or self.citations != _citation_pool(citations):
            return False
        try:
            sources = [SourceReference.model_validate(item) for item in evidence]
        except (ValueError, TypeError):
            return False
        if len({s.source_id for s in sources}) != len(sources):
            return False
        if tuple(sorted((s.source_id, source_digest(s)) for s in sources)) != self.source_snapshots:
            return False
        by_id = {source.source_id: source for source in sources}
        for passage_id, source_id, text in self.passages:
            if source_id not in by_id or text not in (by_id[source_id].content or ""):
                return False
            expected_id = "passage-" + hashlib.sha256(
                (source_id + "\0" + text).encode(),
            ).hexdigest()[:24]
            if passage_id != expected_id:
                return False
        return all(eligible_cloud_source(source, risk_level=risk_level) for source in sources)


def _sign(review: BoundClaimReview) -> BoundClaimReview:
    signature = hmac.new(_SIGNING_KEY, review._signed_payload(), hashlib.sha256).hexdigest()
    return replace(review, _signature=signature)


def review_grounded_claims(
    operation: CloudOperation, *, generated: CloudAnswer,
    passage_by_id: dict[str, SourcePassage], sources: list[SourceReference],
    citations: list[Citation], language: str, question: str,
) -> BoundClaimReview:
    claims = generated.claims
    if not claims or len({c.claim_id for c in claims}) != len(claims):
        raise CloudAIError("cloud_review_binding_rejected", attempted=True)
    source_map = {source.source_id: source for source in sources}
    expected = []
    items = []
    for claim in claims:
        if not claim.passage_ids or not set(claim.passage_ids) <= set(generated.passage_ids):
            raise CloudAIError("cloud_review_binding_rejected", attempted=True)
        passages = [passage_by_id[pid] for pid in dict.fromkeys(claim.passage_ids)]
        for passage in passages:
            source = source_map.get(passage.source_id)
            if source is None or passage.text not in (source.content or ""):
                raise CloudAIError("cloud_review_binding_rejected", attempted=True)
        original = " ".join(p.text for p in passages)
        if not claim_preserves_details(original, claim.text, language=language):
            raise CloudAIError("cloud_detail_rejected", attempted=True)
        if not claim_preserves_explicit_safety(original, claim.text, language=language):
            raise CloudAIError("cloud_claim_safety_rejected", attempted=True)
        expected.extend(Citation(
            citation_id=f"QWEN-{claim.claim_id}-{i}", source_id=passage.source_id,
            claim=claim.text, supporting_quote=passage.text,
        ) for i, passage in enumerate(passages, start=1))
        items.append({
            "item_id": claim.claim_id, "kind": claim.kind, "candidate": claim.text,
            "original_evidence": [passage.model_dump() for passage in passages],
        })
    if _citation_pool(expected) != _citation_pool(citations):
        raise CloudAIError("cloud_review_binding_rejected", attempted=True)
    snapshots = tuple(sorted((s.source_id, source_digest(s)) for s in sources))
    review_items(operation, language=language, question=question,
                 task="source_grounded_answer", items=items)
    reviewed_passages = tuple(sorted({
        (pid, passage_by_id[pid].source_id, passage_by_id[pid].text)
        for claim in claims for pid in claim.passage_ids
    }))
    return _sign(BoundClaimReview(
        tuple(c.text for c in claims), reviewed_passages, snapshots, _citation_pool(citations),
    ))
