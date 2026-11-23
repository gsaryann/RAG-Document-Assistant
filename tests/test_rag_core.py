import numpy as np
import pytest

from src.rag_core import (
    answer_evaluation_label, cache_matches, evaluate_retrieval,
    is_safe_archive_member, retrieval_hit, should_abstain, validate_chunk_config,
)


@pytest.mark.parametrize("size,overlap", [(1, 0), (400, 50), (300, 100)])
def test_valid_chunk_configuration(size, overlap):
    validate_chunk_config(size, overlap)


@pytest.mark.parametrize("size,overlap", [(0, 0), (-1, 0), (400, -1), (50, 50), (10, 11)])
def test_invalid_chunk_configuration_is_rejected(size, overlap):
    with pytest.raises(ValueError):
        validate_chunk_config(size, overlap)


def test_embedding_cache_requires_matching_manifest_and_shape():
    arr = np.zeros((3, 384), dtype=np.float32)
    manifest = {"model": "e5", "corpus_hash": "abc"}
    assert cache_matches(arr, manifest, manifest, 3, 384)
    assert not cache_matches(arr, {"model": "e5"}, manifest, 3, 384)
    assert not cache_matches(arr, manifest, manifest, 4, 384)
    assert not cache_matches(np.zeros((3, 2)), manifest, manifest, 3, 384)
    assert not cache_matches(arr, None, manifest, 3, 384)


def test_abstention_threshold_is_validated_and_applied():
    assert should_abstain(0.69, 0.70)
    assert not should_abstain(0.70, 0.70)
    with pytest.raises(ValueError):
        should_abstain(0.5, 1.2)
    with pytest.raises(ValueError):
        should_abstain(float("nan"), 0.7)


def test_retrieval_hit_is_not_answer_correctness():
    retrieved = [{"document_title": "Луна"}, {"document_title": "Марс"}]
    assert retrieval_hit("Луна", retrieved, 1)
    assert not retrieval_hit("Марс", retrieved, 1)
    assert retrieval_hit("Марс", retrieved, 2)
    assert answer_evaluation_label(True, "Неправильный ответ", 0.9, 0.7) == "ТРЕБУЕТ РУЧНОЙ ПРОВЕРКИ"


def test_ood_evaluation_distinguishes_refusal_and_hallucination():
    refusal = "В предоставленных документах базы знаний нет ответа на этот вопрос"
    assert answer_evaluation_label(False, refusal, 0.4, 0.7).startswith("Отказ по порогу")
    assert answer_evaluation_label(False, "Вот выдуманный ответ", 0.4, 0.7).startswith("Нет отказа")
    assert answer_evaluation_label(False, "Вот выдуманный ответ", 0.8, 0.7).startswith("Ответ вне корпуса")


def test_retrieval_evaluation_reports_only_hit_rates():
    questions = [
        {"question": "q1", "is_in_corpus": True, "document_title": "Луна"},
        {"question": "q2", "is_in_corpus": False, "document_title": None},
    ]
    rows = evaluate_retrieval(questions, lambda q, k: [{"document_title": "Луна"}], ks=(1, 3))
    assert rows == [
        {"k": 1, "hits": 1, "total": 1, "hit_rate": 1.0},
        {"k": 3, "hits": 1, "total": 1, "hit_rate": 1.0},
    ]


def test_zip_member_path_traversal_is_rejected():
    assert is_safe_archive_member("documents/article_001.txt")
    assert not is_safe_archive_member("../outside.txt")
    assert not is_safe_archive_member("documents/../../outside.txt")
    assert not is_safe_archive_member("C:/outside.txt")
    assert not is_safe_archive_member("/absolute/path.txt")
