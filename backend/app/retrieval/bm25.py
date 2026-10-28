"""Small BM25 implementation for Latin, Cyrillic and unspaced Chinese text."""

import math
import re
import unicodedata
from collections import Counter

_TOKENS = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+|[^\W_]+", re.UNICODE)
_HAN = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff]+$")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in _TOKENS.findall(unicodedata.normalize("NFKC", text).casefold()):
        if _HAN.fullmatch(token):
            tokens.extend(token)
            tokens.extend(token[index : index + 2] for index in range(len(token) - 1))
        else:
            tokens.append(token)
    return tokens


class BM25Index:
    def __init__(self, documents: list[str], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.documents = [Counter(tokenize(text)) for text in documents]
        self.lengths = [sum(document.values()) for document in self.documents]
        self.average_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0
        self.document_frequency = Counter(
            token for document in self.documents for token in document
        )
        self.k1, self.b = k1, b

    def scores(self, query: str) -> list[float]:
        terms = set(tokenize(query))
        count = len(self.documents)
        scores: list[float] = []
        for document, length in zip(self.documents, self.lengths, strict=True):
            score = 0.0
            for token in terms:
                frequency = document.get(token, 0)
                if not frequency:
                    continue
                df = self.document_frequency[token]
                idf = math.log1p((count - df + 0.5) / (df + 0.5))
                normalizer = frequency + self.k1 * (
                    1 - self.b + self.b * length / max(self.average_length, 1)
                )
                score += idf * frequency * (self.k1 + 1) / normalizer
            scores.append(score)
        return scores
