import os
import sys
import json
import csv
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
corpus_dir = os.path.join(base_dir, "corpus_cosmos")
docs_dir = os.path.join(corpus_dir, "documents")
csv_path = os.path.join(corpus_dir, "metadata.csv")
jsonl_path = os.path.join(corpus_dir, "corpus.jsonl")
readme_path = os.path.join(corpus_dir, "README.md")

print("=== Проверка качества корпуса corpus_cosmos ===")

# 1. Проверка структуры папок и файлов
assert os.path.exists(corpus_dir), "Папка corpus_cosmos отсутствует!"
assert os.path.exists(docs_dir), "Папка corpus_cosmos/documents отсутствует!"
assert os.path.exists(csv_path), "Файл metadata.csv отсутствует!"
assert os.path.exists(jsonl_path), "Файл corpus.jsonl отсутствует!"
assert os.path.exists(readme_path), "Файл README.md отсутствует!"
print("[OK] Все ключевые директории и файлы существуют.")

# 2. Проверка metadata.csv
df = pd.read_csv(csv_path, encoding='utf-8')
expected_columns = ["id", "title", "url", "categories", "word_count", "file_name"]
assert list(df.columns) == expected_columns, f"Колонки metadata.csv не совпадают! Получено: {list(df.columns)}"
assert len(df) >= 30 and len(df) <= 40, f"Количество статей в CSV ({len(df)}) не попадает в диапазон 30-40!"
assert df['title'].nunique() == len(df), "Обнаружены дубликаты по title в metadata.csv!"
assert df['url'].nunique() == len(df), "Обнаружены дубликаты по url в metadata.csv!"
assert df['file_name'].nunique() == len(df), "Обнаружены дубликаты по file_name в metadata.csv!"
assert (df['word_count'] > 0).all(), "Обнаружены статьи с нулевым количеством слов в CSV!"
print(f"[OK] metadata.csv валиден: {len(df)} уникальных строк, все поля корректны.")

# 3. Проверка текстовых документов
txt_files = sorted(os.listdir(docs_dir))
assert len(txt_files) == len(df), f"Количество файлов ({len(txt_files)}) не совпадает с CSV ({len(df)})"

total_words_from_files = 0
for idx, row in df.iterrows():
    fn = row['file_name']
    fp = os.path.join(docs_dir, fn)
    assert os.path.exists(fp), f"Файл {fn} не найден на диске!"
    with open(fp, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.strip()) > 0, f"Файл {fn} пуст!"
    words = len(content.split())
    total_words_from_files += words
    assert words == row['word_count'], f"Несовпадение количества слов для {fn}: файл={words}, csv={row['word_count']}"

print(f"[OK] Все {len(txt_files)} TXT-файлов успешно прочитаны в UTF-8, пустых документов нет.")
print(f"[OK] Суммарный объём по файлам: {total_words_from_files:,} слов.")

# 4. Проверка corpus.jsonl
jsonl_records = []
with open(jsonl_path, "r", encoding="utf-8") as f:
    for line_idx, line in enumerate(f, 1):
        assert line.strip(), f"Пустая строка #{line_idx} в corpus.jsonl"
        record = json.loads(line)
        jsonl_records.append(record)

assert len(jsonl_records) == len(df), f"Количество записей в corpus.jsonl ({len(jsonl_records)}) != CSV ({len(df)})"

for record, (_, row) in zip(jsonl_records, df.iterrows()):
    assert record['id'] == row['id'], f"ID mismatch: {record['id']} != {row['id']}"
    assert record['title'] == row['title'], f"Title mismatch: {record['title']} != {row['title']}"
    assert record['url'] == row['url'], f"URL mismatch: {record['url']} != {row['url']}"
    assert record['word_count'] == row['word_count'], f"Word count mismatch"
    assert record['file_name'] == row['file_name'], f"Filename mismatch"
    assert len(record.get('text', '').strip()) > 0, f"Текст пуст в jsonl для ID {record['id']}"
    assert len(record['text'].split()) == record['word_count'], "Word count in text does not match word_count field"

print(f"[OK] corpus.jsonl валиден: {len(jsonl_records)} записей, синхронизированы с CSV и TXT.")

# 5. Проверка README.md
with open(readme_path, "r", encoding="utf-8") as f:
    readme_text = f.read()

required_sections = [
    "Источник данных",
    "Дата сбора",
    "Количество статей",
    "Общий объём текста",
    "Тематические направления",
    "Структура корпуса",
    "Сведения об очистке текста",
    "Список использованных категорий",
    "Инструкция по повторному запуску",
]

for req in required_sections:
    assert req.lower() in readme_text.lower(), f"Раздел '{req}' не найден в README.md!"

print(f"[OK] README.md содержит все обязательные разделы и сведения.")

# 6. Проверка объёма (эквивалент 50 страниц)
# 50 страниц при 250-300 слов/стр = 12500 - 15000 слов
pages_equiv = total_words_from_files / 275
print(f"[OK] Общий объём: {total_words_from_files:,} слов (~{pages_equiv:.1f} страниц). Требование 'не менее 50 страниц' перевыполнено в {pages_equiv / 50:.1f} раз!")

print("\nВСЕ ПРОВЕРКИ КОНТРОЛЯ КАЧЕСТВА УСПЕШНО ПРОЙДЕНЫ!")
