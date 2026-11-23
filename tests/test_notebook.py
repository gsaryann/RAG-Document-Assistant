import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "RAG_Document_Assistant.ipynb"


def test_all_notebook_code_cells_are_valid_python():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "code":
            ast.parse("".join(cell["source"]), filename=f"notebook-cell-{index}")


def test_gradio_never_receives_the_tokenwave_secret():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    source = "\n".join("".join(cell["source"]) for cell in notebook["cells"])
    assert "value=env_tokenwave_key" not in source
    assert "tokenwave_key_input" not in source
    assert "key = os.getenv(\"TOKENWAVE_API_KEY\", \"\").strip()" in source


def test_notebook_has_a_real_chunking_parameter_experiment():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    source = "\n".join("".join(cell["source"]) for cell in notebook["cells"])
    assert "for size in (300, 400, 500)" in source
    assert "for overlap in (30, 50, 100)" in source
    assert "chunking_experiment.csv" in source
    assert "НЕ ОЦЕНЕНА — требуется ручная проверка" in source
