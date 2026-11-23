import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("collect_corpus", ROOT / "src" / "collect_corpus.py")
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


def test_clean_text_removes_trailing_references_and_normalizes_whitespace():
    text = "Основной текст.\u00a0\u00a0\n\n== Примечания ==\nСлужебный текст"
    assert collector.clean_text(text) == "Основной текст."


def test_clean_text_keeps_body_when_no_trailing_section_exists():
    assert collector.clean_text("Текст\u0301 статьи") == "Текст статьи"
