from math import isfinite, sqrt


def validate_vector(vector: list[float]) -> bool:
    if not vector:
        return False
    return all(_is_number(value) for value in vector)


def vector_norm(vector: list[float]) -> float:
    if not vector:
        return 0.0
    _raise_if_non_numeric(vector)
    return sqrt(sum(value * value for value in vector))


def dot_product(a: list[float], b: list[float]) -> float:
    _raise_if_length_mismatch(a, b)
    if not a or not b:
        return 0.0
    _raise_if_non_numeric(a)
    _raise_if_non_numeric(b)
    return sum(left * right for left, right in zip(a, b, strict=True))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    _raise_if_length_mismatch(a, b)
    if not a or not b:
        return 0.0
    norm_a = vector_norm(a)
    norm_b = vector_norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product(a, b) / (norm_a * norm_b)


def _raise_if_length_mismatch(a: list[float], b: list[float]) -> None:
    if len(a) != len(b):
        raise ValueError("Vector dimensions must match.")


def _raise_if_non_numeric(vector: list[float]) -> None:
    if not all(_is_number(value) for value in vector):
        raise ValueError("Vector values must be finite numbers.")


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and isfinite(value)
