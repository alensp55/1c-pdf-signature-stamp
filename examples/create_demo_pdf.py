"""Создает обезличенный PDF для локальной проверки примера."""

import sys
from pathlib import Path

import pymupdf


КОРЕНЬ_ПРОЕКТА = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(КОРЕНЬ_ПРОЕКТА / "src"))

from pdf_signature_stamp import найти_шрифт  # noqa: E402


def main() -> None:
    путь = Path(__file__).with_name("input.pdf")
    путь_шрифта = найти_шрифт()
    with pymupdf.open() as документ:
        страница = документ.new_page(width=595, height=842)
        страница.insert_text(
            pymupdf.Point(72, 90),
            "ДЕМОНСТРАЦИОННЫЙ PDF ДЛЯ ЛОКАЛЬНОЙ ПРОВЕРКИ",
            fontsize=16,
            fontname="demofont",
            fontfile=str(путь_шрифта),
        )
        страница.draw_rect(pymupdf.Rect(72, 120, 523, 650), color=(0.7, 0.7, 0.7), width=0.8)
        документ.save(путь)
    print(f"Создан файл: {путь}")


if __name__ == "__main__":
    main()
