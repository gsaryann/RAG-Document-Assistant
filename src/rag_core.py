"""Pure helpers shared by the RAG notebook and its regression tests."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


def is_safe_archive_member(name: str) -> bool:
    """Reject absolute paths and traversal entries in ZIP archives."""
    normalized = name.replace("\\", "/")
    parts = normalized.split("/")
    return bool(normalized) and not normalized.startswith("/") and ".." not in parts and not (len(normalized) >= 2 and normalized[1] == ":")


def validate_chunk_config(chunk_size: int, overlap: int) -> None:
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    if isinstance(overlap, bool) or not isinstance(overlap, int) or overlap < 0:
        raise ValueError("overlap must be a non-negative integer")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")


def cache_matches(embeddings: Any, manifest: Mapping[str, Any] | None,
                  expected_manifest: Mapping[str, Any], expected_rows: int,
                  expected_dim: int) -> bool:
    """Return True only when cache metadata and array shape match exactly."""
    shape = getattr(embeddings, "shape", None)
    return bool(
        manifest is not None
        and dict(manifest) == dict(expected_manifest)
        and shape is not None
        and len(shape) == 2
        and shape[0] == expected_rows
        and shape[1] == expected_dim
    )


def should_abstain(score: float, threshold: float) -> bool:
    if not math.isfinite(float(score)) or not math.isfinite(float(threshold)):
        raise ValueError("score and threshold must be finite")
    if not 0.0 <= float(threshold) <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    return float(score) < float(threshold)


def retrieval_hit(target_document: str | None, retrieved: Sequence[Mapping[str, Any]], k: int) -> bool:
    if k < 1:
        raise ValueError("k must be >= 1")
    if not target_document:
        return False
    return any(item.get("document_title") == target_document for item in retrieved[:k])


def evaluate_retrieval(questions: Sequence[Mapping[str, Any]], search_fn, ks=(1, 3, 5)) -> list[dict[str, Any]]:
    """Evaluate document retrieval only; it deliberately makes no answer-quality claim."""
    rows: list[dict[str, Any]] = []
    for k in ks:
        hits = 0
        total = 0
        for item in questions:
            if not item.get("is_in_corpus"):
                continue
            total += 1
            retrieved = search_fn(item["question"], max(ks))
            hits += int(retrieval_hit(item.get("document_title"), retrieved, k))
        rows.append({"k": k, "hits": hits, "total": total, "hit_rate": hits / total if total else 0.0})
    return rows


def answer_evaluation_label(is_in_corpus: bool, answer: str, score: float, threshold: float) -> str:
    """Only classify refusal behavior; factual correctness always requires human review."""
    refused = "в предоставленных документах базы знаний нет ответа" in (answer or "").lower()
    if is_in_corpus:
        return "ТРЕБУЕТ РУЧНОЙ ПРОВЕРКИ"
    if should_abstain(score, threshold) and refused:
        return "Отказ по порогу (проверить вручную)"
    if should_abstain(score, threshold) and not refused:
        return "Нет отказа при низком score — ошибка"
    if not should_abstain(score, threshold) and refused:
        return "Отказ при score выше порога — проверить"
    return "Ответ вне корпуса — вероятная галлюцинация"
