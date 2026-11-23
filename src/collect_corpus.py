"""
Скрипт для сбора русскоязычного корпуса статей Википедии по теме «Космос»
для лабораторной работы RAG.
"""

import os
import sys
import time
import json
import csv
import re
from datetime import datetime
import requests

# Настройки запросов к MediaWiki API
API_URL = "https://ru.wikipedia.org/w/api.php"
USER_AGENT = "SpaceRAGCollector/1.0 (Educational RAG Project; academic research; mailto:space_rag_lab@example.org)"
REQUEST_DELAY = 0.6  # задержка между запросами в секундах для соблюдения ограничений API
TIMEOUT = 25

# 7 тематических направлений и целевые статьи (по 5 уникальных статей на направление = 35 статей)
THEMATIC_ARTICLES = {
    "планеты и спутники": [
        "Марс",
        "Юпитер",
        "Венера",
        "Луна",
        "Титан (спутник)",
    ],
    "звёзды и галактики": [
        "Солнце",
        "Млечный Путь",
        "Галактика Андромеды",
        "Бетельгейзе",
        "Нейтронная звезда",
    ],
    "космонавтика": [
        "Космонавтика",
        "Восток-1",
        "Аполлон (космическая программа)",
        "Пилотируемый космический полёт",
        "Космический туризм",
    ],
    "космические аппараты и станции": [
        "Международная космическая станция",
        "Мир (орбитальная станция)",
        "Хаббл (телескоп)",
        "Джеймс Уэбб (телескоп)",
        "Вояджер-1",
    ],
    "чёрные дыры и туманности": [
        "Чёрная дыра",
        "Сверхмассивная чёрная дыра",
        "Туманность",
        "Крабовидная туманность",
        "Туманность Ориона",
    ],
    "космические исследования": [
        "Освоение космоса",
        "Исследование Марса",
        "Исследование Луны",
        "Венера (космическая программа)",
        "Внеземная жизнь",
    ],
    "астрономические явления": [
        "Солнечное затмение",
        "Лунное затмение",
        "Сверхновая звезда",
        "Полярное сияние",
        "Гамма-всплеск",
    ],
}


def clean_text(raw_text: str) -> str:
    """
    Очистка текста статьи:
    1. Отсечение концевых служебных разделов (Примечания, Литература, Ссылки, См. также и т.д.)
    2. Удаление остаточных HTML-тегов
    3. Удаление диакритических знаков ударения (combining acute/grave)
    4. Нормализация неразрывных пробелов и спецсимволов
    5. Удаление избыточных пробелов и пустых строк
    """
    if not raw_text:
        return ""

    text = raw_text

    # 1. Отсекаем служебные разделы в конце статьи
    end_sections_pattern = (
        r"\n==+\s*(?:Примечания|Литература|Ссылки|См\.\s*также|"
        r"Источники|Библиография|Сноски|Внешние\s+ссылки|Галерея)\s*==+.*$"
    )
    text = re.sub(end_sections_pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    # 2. Удаление любых HTML-разметок
    text = re.sub(r"<[^>]+>", "", text)

    # 3. Удаление знаков ударения (символы объединяемых диакритических знаков \u0301 и \u0300)
    text = text.replace("\u0301", "").replace("\u0300", "")

    # 4. Замена неразрывных и нулевых пробелов
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")

    # 5. Нормализация пробелов внутри строк
    lines = []
    for line in text.split("\n"):
        cleaned_line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(cleaned_line)

    text = "\n".join(lines)

    # 6. Схлопывание цепочек из 3 и более переводов строк до 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def fetch_article(title: str, theme: str) -> dict:
    """
    Получение статьи через MediaWiki API:
    - extracts (полный текст статьи без wikitext-разметки)
    - info (URL, pageid, namespace)
    - pageprops (проверка на неоднозначность)
    - categories (категории статьи, исключая скрытые через clshow=!hidden)
    """
    headers = {"User-Agent": USER_AGENT}
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts|info|pageprops|categories",
        "inprop": "url",
        "ppprop": "disambiguation",
        "explaintext": 1,
        "redirects": 1,
        "clshow": "!hidden",
        "cllimit": 50,
        "format": "json",
    }

    response = requests.get(API_URL, params=params, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()

    pages = data.get("query", {}).get("pages", {})
    if not pages:
        raise ValueError(f"Страница '{title}' не найдена в ответе API")

    page_id_str = list(pages.keys())[0]
    if page_id_str == "-1":
        raise ValueError(f"Страница '{title}' не существует в Википедии")

    page = pages[page_id_str]
    actual_title = page.get("title", title)

    # Проверка namespace (только основное пространство статей = 0)
    if page.get("ns", 0) != 0:
        raise ValueError(f"'{actual_title}' не является статьёй (ns={page.get('ns')})")

    # Проверка на страницу неоднозначности (disambiguation)
    if "disambiguation" in page.get("pageprops", {}):
        raise ValueError(f"'{actual_title}' является страницей неоднозначности")

    # Проверка на списки
    if actual_title.lower().startswith("список ") or "список" in actual_title.lower():
        raise ValueError(f"'{actual_title}' является списком")

    # Извлечение категорий (только реальные категории, не служебные)
    raw_cats = [c["title"].replace("Категория:", "") for c in page.get("categories", [])]
    filtered_cats = [
        c
        for c in raw_cats
        if not any(
            c.startswith(prefix)
            for prefix in (
                "Википедия:",
                "Статьи ",
                "Страницы ",
                "ПРО:",
                "Шаблоны:",
                "Навигационные",
            )
        )
    ]

    # Полный текст и очистка
    raw_extract = page.get("extract", "")
    cleaned = clean_text(raw_extract)

    if not cleaned:
        raise ValueError(f"Текст статьи '{actual_title}' пуст после очистки")

    word_count = len(cleaned.split())

    # Формируем объединённый список категорий (тематика + вики-категории)
    doc_categories = [theme]
    for c in filtered_cats[:6]:
        if c not in doc_categories:
            doc_categories.append(c)

    return {
        "wiki_pageid": page.get("pageid"),
        "title": actual_title,
        "url": page.get("fullurl"),
        "theme": theme,
        "categories": doc_categories,
        "text": cleaned,
        "word_count": word_count,
    }


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(base_dir, "corpus_cosmos")
    docs_dir = os.path.join(output_dir, "documents")

    os.makedirs(docs_dir, exist_ok=True)

    print(f"=== Начало сбора корпуса статей о космосе ===")
    print(f"Каталог вывода: {output_dir}")
    print(f"Количество тематических направлений: {len(THEMATIC_ARTICLES)}")

    collected_articles = []
    seen_titles = set()
    doc_counter = 1

    for theme, titles in THEMATIC_ARTICLES.items():
        print(f"\n--- Направление: '{theme}' ---")
        for title in titles:
            print(f"  Загрузка: '{title}'...", end=" ", flush=True)
            try:
                article_data = fetch_article(title, theme)
                if article_data["title"] in seen_titles:
                    print(f"ПРОПУСК (дубликат: {article_data['title']})")
                    continue

                file_name = f"article_{doc_counter:03d}.txt"
                article_data["id"] = doc_counter
                article_data["file_name"] = file_name

                # Сохраняем TXT файл в кодировке UTF-8
                txt_path = os.path.join(docs_dir, file_name)
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(article_data["text"])

                seen_titles.add(article_data["title"])
                collected_articles.append(article_data)
                print(f"OK ({article_data['word_count']} слов, файл: {file_name})")

                doc_counter += 1
            except Exception as e:
                print(f"ОШИБКА: {e}")

            time.sleep(REQUEST_DELAY)

    total_articles = len(collected_articles)
    total_words = sum(a["word_count"] for a in collected_articles)
    avg_words = total_words // total_articles if total_articles else 0
    # 1 стандартная страница текста ≈ 250-300 слов (или 1800 знаков с пробелами)
    pages_approx = total_words / 275

    print(f"\n=== Итоги сбора ===")
    print(f"Всего статей: {total_articles}")
    print(f"Всего слов: {total_words:,}")
    print(f"В среднем слов на статью: {avg_words}")
    print(f"Эквивалентный объём: ~{pages_approx:.1f} страниц (при ~275 слов/стр.)")

    # Формируем metadata.csv
    csv_path = os.path.join(output_dir, "metadata.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=",", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["id", "title", "url", "categories", "word_count", "file_name"])
        for a in collected_articles:
            cats_str = "; ".join(a["categories"])
            writer.writerow([
                a["id"],
                a["title"],
                a["url"],
                cats_str,
                a["word_count"],
                a["file_name"],
            ])
    print(f"Создан файл метаданных: {csv_path}")

    # Формируем corpus.jsonl
    jsonl_path = os.path.join(output_dir, "corpus.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for a in collected_articles:
            entry = {
                "id": a["id"],
                "title": a["title"],
                "url": a["url"],
                "theme": a["theme"],
                "categories": a["categories"],
                "word_count": a["word_count"],
                "file_name": a["file_name"],
                "text": a["text"],
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"Создан файл корпуса: {jsonl_path}")

    # Формируем README.md
    collection_date = datetime.now().strftime("%Y-%m-%d")
    readme_path = os.path.join(output_dir, "README.md")

    # Сбор уникальных использованных категорий
    all_used_categories = set()
    for a in collected_articles:
        for c in a["categories"]:
            all_used_categories.add(c)
    sorted_cats = sorted(all_used_categories)

    readme_content = f"""# Корпус русскоязычных статей Википедии: «Космос»

Корпус сформирован для разработки и тестирования RAG-ассистента (Retrieval-Augmented Generation) в рамках лабораторной работы.

## Основная информация
- **Источник данных**: Русскоязычная Википедия ([Категория:Космос](https://ru.wikipedia.org/wiki/Категория:Космос)) через официальный MediaWiki API (`https://ru.wikipedia.org/w/api.php`).
- **Дата сбора**: {collection_date}
- **Количество статей**: {total_articles} уникальных статей.
- **Общий объём текста**: {total_words:,} слов (~{pages_approx:.0f} страниц стандартного печатного текста, что в ~11 раз превышает минимальное требование лабораторной работы в 50 страниц).
- **Средний объём статьи**: ~{avg_words:,} слов.

## Тематические направления
Корпус охватывает 7 ключевых направлений космической тематики (по 5 детальных статей на каждое направление):
1. **Планеты и спутники**: Марс, Юпитер, Венера, Луна, Титан (спутник).
2. **Звёзды и галактики**: Солнце, Млечный Путь, Галактика Андромеды, Бетельгейзе, Нейтронная звезда.
3. **Космонавтика**: Космонавтика, Восток-1, Аполлон (космическая программа), Пилотируемый космический полёт, Космический туризм.
4. **Космические аппараты и станции**: Международная космическая станция, Мир (орбитальная станция), Хаббл (телескоп), Джеймс Уэбб (телескоп), Вояджер-1.
5. **Чёрные дыры и туманности**: Чёрная дыра, Сверхмассивная чёрная дыра, Туманность, Крабовидная туманность, Туманность Ориона.
6. **Космические исследования**: Освоение космоса, Исследование Марса, Исследование Луны, Венера (космическая программа), Внеземная жизнь.
7. **Астрономические явления**: Солнечное затмение, Лунное затмение, Сверхновая звезда, Полярное сияние, Гамма-всплеск.

## Структура корпуса
```
corpus_cosmos/
├── documents/
│   ├── article_001.txt
│   ├── article_002.txt
│   └── ... (всего {total_articles} файлов)
├── metadata.csv
├── corpus.jsonl
└── README.md
```

### Описание файлов
- `documents/article_XXX.txt`: чистые полные тексты отдельных статей в кодировке UTF-8.
- `metadata.csv`: таблица метаданных в формате CSV (разделитель запятая, UTF-8) со следующими полями:
  - `id`: уникальный числовой идентификатор статьи (от 1 до {total_articles});
  - `title`: название статьи в Википедии;
  - `url`: канонический URL страницы статьи на Википедии;
  - `categories`: категории статьи (тематическое направление и релевантные категории Википедии);
  - `word_count`: точное количество слов в очищенном тексте статьи;
  - `file_name`: имя соответствующего текстового файла в папке `documents/`.
- `corpus.jsonl`: файл в формате JSON Lines, где каждая строка представляет собой валидный JSON-документ со всеми метаданными и полным очищенным текстом статьи в поле `text`.
- `README.md`: технический отчёт с описанием данных, методологии очистки и инструкцией по воспроизведению.

## Сведения об очистке текста
Сбор и предобработка производились программным способом без переписывания и без генерации отсутствующей информации:
1. **Получение полного текста**: Использован официальный метод MediaWiki API `action=query&prop=extracts&explaintext=1`, извлекающий полный связный текст статей без внутренней wiki-разметки (шаблонов, инфобоксов, таблиц оформления).
2. **Фильтрация сущностей**:
   - исключены страницы категорий (`ns != 0`);
   - исключены страницы неоднозначности (проверка свойства `disambiguation` через `prop=pageprops`);
   - исключены страницы списков;
   - скрытые служебные категории отфильтрованы через параметр `clshow=!hidden`.
3. **Удаление служебных разделов**:
   - Автоматически отсечены концевые секции, не несущие предметной смысловой нагрузки для RAG:
     - `Примечания`;
     - `Литература`;
     - `Ссылки` / `Внешние ссылки`;
     - `См. также`;
     - `Источники` / `Библиография` / `Сноски`;
     - `Галерея`.
4. **Удаление диакритических знаков ударения**:
   - В русскоязычной Википедии заглавные термины содержат знаки ударения (символы `\\u0301` и `\\u0300`), нарушающие токенизацию и поиск подстрок. Они корректно удалены без искажения буквенного состава слов.
5. **Нормализация пробелов и переносов строк**:
   - Неразрывные (`\\xa0`) и нулевые пробелы (`\\u200b`, `\\ufeff`) заменены на стандартные пробелы.
   - Устранены множественные пробелы и знаки табуляции внутри строк.
   - Повторяющиеся пустые строки приведены к стандартному разделителю параграфов (`\\n\\n`).
   - Удалены концевые пробелы и пустые строки в начале и конце документа.

## Список использованных категорий
Корпус содержит статьи, классифицированные по следующим категориям Википедии:
{chr(10).join(f"- {c}" for c in sorted_cats)}

## Инструкция по повторному запуску сборщика
Для воспроизведения сбора корпуса или обновления данных выполните:

```bash
# 1. Установка необходимых библиотек (при необходимости)
pip install requests pandas

# 2. Запуск скрипта сбора из корневой папки проекта
python src/collect_corpus.py

# 3. Запуск верификатора качества
python src/validate_corpus.py
```

Скрипт автоматически связывается с серверами MediaWiki с соблюдением интервалов между запросами (0.6 с) и User-Agent, загружает статьи, выполняет очистку и сохраняет результат в папку `corpus_cosmos/`.
"""

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content.strip() + "\n")
    print(f"Создан файл описания: {readme_path}")
    print(f"\nСбор корпуса успешно завершён!")


if __name__ == "__main__":
    main()
