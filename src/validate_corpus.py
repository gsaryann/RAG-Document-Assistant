"""Strict consistency checks for the generated Wikipedia corpus."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    corpus_dir = base_dir / "corpus_cosmos"
    docs_dir = corpus_dir / "documents"
    csv_path = corpus_dir / "metadata.csv"
    jsonl_path = corpus_dir / "corpus.jsonl"
    readme_path = corpus_dir / "README.md"
    archive_path = corpus_dir / "documents.zip"

    print("=== Проверка качества корпуса corpus_cosmos ===")
    for path in (corpus_dir, docs_dir, csv_path, jsonl_path, readme_path):
        require(path.exists(), f"Обязательный путь отсутствует: {path}")
    require(docs_dir.is_dir(), "documents должен быть каталогом")
    print("[OK] Структура корпуса существует.")

    df = pd.read_csv(csv_path, encoding="utf-8")
    expected_columns = ["id", "title", "url", "categories", "word_count", "file_name"]
    require(list(df.columns) == expected_columns, f"Ожидались колонки {expected_columns}; получено {list(df.columns)}")
    require(30 <= len(df) <= 40, f"Ожидалось 30–40 статей, получено {len(df)}")
    for column in ("id", "title", "url", "file_name"):
        require(df[column].notna().all(), f"В колонке {column} есть пустые значения")
        require(df[column].nunique() == len(df), f"В колонке {column} есть дубликаты")
    require(df["id"].is_unique, "ID статей должны быть уникальными")
    require((df["word_count"] > 0).all(), "Обнаружены документы с нулевым word_count")
    require(df["url"].astype(str).str.startswith("https://").all(), "URL источников должны использовать HTTPS")
    print(f"[OK] metadata.csv: {len(df)} уникальных записей.")

    expected_files = set(df["file_name"].astype(str))
    actual_files = {p.name for p in docs_dir.iterdir() if p.is_file() and p.suffix.lower() == ".txt"}
    require(actual_files == expected_files, f"TXT-файлы не совпадают с CSV; отсутствуют={sorted(expected_files-actual_files)}, лишние={sorted(actual_files-expected_files)}")
    total_words = 0
    texts_by_name: dict[str, str] = {}
    for row in df.to_dict("records"):
        filename = str(row["file_name"])
        require(Path(filename).name == filename and filename.lower().endswith(".txt"), f"Небезопасное имя файла: {filename}")
        content = (docs_dir / filename).read_text(encoding="utf-8")
        require(bool(content.strip()), f"Файл {filename} пуст")
        word_count = len(content.split())
        require(word_count == int(row["word_count"]), f"word_count mismatch для {filename}: файл={word_count}, CSV={row['word_count']}")
        total_words += word_count
        texts_by_name[filename] = content
    print(f"[OK] {len(actual_files)} TXT-файлов соответствуют метаданным.")

    records = []
    with jsonl_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            require(bool(line.strip()), f"Пустая строка #{line_number} в corpus.jsonl")
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Некорректный JSON в строке {line_number}: {exc}") from exc
    require(len(records) == len(df), f"Количество JSONL-записей {len(records)} != CSV {len(df)}")
    records_by_name = {record.get("file_name"): record for record in records}
    require(len(records_by_name) == len(records), "В JSONL есть дублирующиеся file_name")
    require(set(records_by_name) == expected_files, "Набор file_name в JSONL не совпадает с CSV")
    for row in df.to_dict("records"):
        record = records_by_name[str(row["file_name"])]
        for field in ("id", "title", "url", "word_count", "file_name"):
            require(str(record.get(field)) == str(row[field]), f"JSONL/CSV mismatch: {field} для {row['file_name']}")
        require(record.get("text") == texts_by_name[str(row["file_name"])], f"Полный текст JSONL не совпадает с TXT: {row['file_name']}")
        require(len(record["text"].split()) == int(row["word_count"]), f"Количество слов JSONL не совпадает: {row['file_name']}")
    print(f"[OK] JSONL полностью синхронизирован с CSV и TXT ({len(records)} записей).")

    require(archive_path.exists(), "Архив documents.zip отсутствует")
    expected_members = {"metadata.csv"} | {f"documents/{name}" for name in expected_files}
    with zipfile.ZipFile(archive_path, "r") as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "В documents.zip есть дублирующиеся пути")
        require(set(names) == expected_members, "Содержимое documents.zip не соответствует текущим CSV/TXT")
        require(archive.read("metadata.csv") == csv_path.read_bytes(), "metadata.csv внутри архива устарел")
        for filename in expected_files:
            require(
                archive.read(f"documents/{filename}") == (docs_dir / filename).read_bytes(),
                f"Файл {filename} внутри архива устарел"
            )
    print("[OK] documents.zip полностью синхронизирован с текущими CSV/TXT.")

    readme_text = readme_path.read_text(encoding="utf-8")
    required_sections = [
        "Источник данных", "Дата сбора", "Количество статей", "Общий объём текста",
        "Тематические направления", "Структура корпуса", "Сведения об очистке текста",
        "Список использованных категорий", "Инструкция по повторному запуску"
    ]
    missing = [section for section in required_sections if section.lower() not in readme_text.lower()]
    require(not missing, f"В README отсутствуют разделы: {missing}")

    pages_equiv = total_words / 275
    require(pages_equiv >= 50, f"Объём корпуса меньше 50 страниц: {pages_equiv:.1f}")
    print(f"[OK] Объём: {total_words:,} слов (~{pages_equiv:.1f} страниц), минимум 50 страниц соблюдён.")
    print("\nВСЕ ПРОВЕРКИ КОНТРОЛЯ КАЧЕСТВА УСПЕШНО ПРОЙДЕНЫ!")


if __name__ == "__main__":
    main()
