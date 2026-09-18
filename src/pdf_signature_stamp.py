"""Добавляет векторный визуальный штамп электронной подписи в готовый PDF."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import pymupdf


ОБЯЗАТЕЛЬНЫЕ_ПОЛЯ = (
    "input_pdf",
    "output_pdf",
    "certificate",
    "owner",
    "valid_until",
    "power_of_attorney",
)


def загрузить_задание(путь: Path) -> dict[str, Any]:
    try:
        with путь.open("r", encoding="utf-8-sig") as файл:
            задание = json.load(файл)
    except json.JSONDecodeError as ошибка:
        raise ValueError(f"Некорректный JSON: {ошибка}") from ошибка

    отсутствуют = [поле for поле in ОБЯЗАТЕЛЬНЫЕ_ПОЛЯ if not задание.get(поле)]
    if отсутствуют:
        raise ValueError("Не заполнены обязательные поля: " + ", ".join(отсутствуют))

    return задание


def найти_шрифт(указанный_путь: str | None = None) -> Path:
    if указанный_путь:
        путь = Path(указанный_путь)
        if путь.is_file():
            return путь
        raise FileNotFoundError(f"Указанный шрифт не найден: {путь}")

    каталог_windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
    кандидаты = (
        каталог_windows / "Fonts" / "arial.ttf",
        каталог_windows / "Fonts" / "tahoma.ttf",
        каталог_windows / "Fonts" / "segoeui.ttf",
        каталог_windows / "Fonts" / "calibri.ttf",
    )

    for путь in кандидаты:
        if путь.is_file():
            return путь

    raise FileNotFoundError(
        "Не найден шрифт с поддержкой кириллицы. Укажите поле font_path в JSON-задании."
    )


def выбрать_страницы(документ: pymupdf.Document, режим: str) -> list[pymupdf.Page]:
    if режим == "first":
        return [документ[0]]
    if режим == "last":
        return [документ[-1]]
    if режим == "all":
        return list(документ)
    raise ValueError("Поле pages должно иметь значение all, first или last")


def подобрать_размер(
    шрифт: pymupdf.Font,
    строки: list[str],
    начальный_размер: float,
    доступная_ширина: float,
    минимальный_размер: float,
) -> float:
    размер = начальный_размер
    while размер >= минимальный_размер:
        if all(шрифт.text_length(строка, fontsize=размер) <= доступная_ширина for строка in строки):
            return размер
        размер -= 0.25
    raise ValueError("Текст штампа не помещается в рамку даже при минимальном размере шрифта")


def вставить_строки(
    страница: pymupdf.Page,
    строки: list[str],
    x: float,
    y: float,
    размер: float,
    путь_шрифта: Path,
    имя_шрифта: str,
    цвет: tuple[float, float, float],
) -> float:
    межстрочный_интервал = размер * 1.25
    текущий_y = y
    for строка in строки:
        страница.insert_text(
            pymupdf.Point(x, текущий_y),
            строка,
            fontsize=размер,
            fontname=имя_шрифта,
            fontfile=str(путь_шрифта),
            color=цвет,
            overlay=True,
        )
        текущий_y += межстрочный_интервал
    return текущий_y


def добавить_штамп_на_страницу(
    страница: pymupdf.Page,
    задание: dict[str, Any],
    путь_шрифта: Path,
) -> None:
    ширина_страницы = страница.rect.width
    высота_страницы = страница.rect.height

    отступ_x = float(задание.get("left_margin", 40))
    нижний_отступ = float(задание.get("bottom_margin", 60))
    высота_штампа = float(задание.get("stamp_height", 100))
    доля_ширины = float(задание.get("stamp_width_ratio", 0.49))
    ширина_штампа = (ширина_страницы - 2 * отступ_x) * доля_ширины

    if ширина_штампа <= 0 or высота_штампа <= 0:
        raise ValueError("Размеры штампа должны быть положительными")

    рамка = pymupdf.Rect(
        отступ_x,
        высота_страницы - нижний_отступ - высота_штампа,
        отступ_x + ширина_штампа,
        высота_страницы - нижний_отступ,
    )

    if not страница.rect.contains(рамка):
        raise ValueError("Штамп выходит за границы страницы. Проверьте отступы и размеры")

    синий = (0.0, 70 / 255, 200 / 255)
    внутренний_отступ = 10.0
    доступная_ширина = рамка.width - 2 * внутренний_отступ
    имя_шрифта = "stampfont"
    шрифт = pymupdf.Font(fontfile=str(путь_шрифта))

    заголовок = ["ДОКУМЕНТ ПОДПИСАН", "ЭЛЕКТРОННОЙ ПОДПИСЬЮ"]
    реквизиты = [
        f"Сертификат {задание['certificate']}",
        f"Владелец {задание['owner']}",
        f"Действителен по {задание['valid_until']}",
        f"Доверенность № {задание['power_of_attorney']}",
    ]

    размер_заголовка = подобрать_размер(шрифт, заголовок, 11, доступная_ширина, 7)
    размер_реквизитов = подобрать_размер(шрифт, реквизиты, 8, доступная_ширина, 5)

    страница.draw_rect(рамка, color=синий, width=1.5, overlay=True)
    текущий_y = рамка.y0 + внутренний_отступ + размер_заголовка
    текущий_y = вставить_строки(
        страница,
        заголовок,
        рамка.x0 + внутренний_отступ,
        текущий_y,
        размер_заголовка,
        путь_шрифта,
        имя_шрифта,
        синий,
    )

    текущий_y += 2.5
    вставить_строки(
        страница,
        реквизиты,
        рамка.x0 + внутренний_отступ,
        текущий_y,
        размер_реквизитов,
        путь_шрифта,
        имя_шрифта,
        синий,
    )


def добавить_штамп(задание: dict[str, Any]) -> Path:
    входной_pdf = Path(задание["input_pdf"]).resolve()
    выходной_pdf = Path(задание["output_pdf"]).resolve()

    if not входной_pdf.is_file():
        raise FileNotFoundError(f"Входной PDF не найден: {входной_pdf}")
    if входной_pdf == выходной_pdf:
        raise ValueError("Входной и выходной PDF должны быть разными файлами")

    выходной_pdf.parent.mkdir(parents=True, exist_ok=True)
    путь_шрифта = найти_шрифт(задание.get("font_path"))
    режим_страниц = str(задание.get("pages", "all"))

    with pymupdf.open(входной_pdf) as документ:
        if документ.page_count == 0:
            raise ValueError("Входной PDF не содержит страниц")
        for страница in выбрать_страницы(документ, режим_страниц):
            добавить_штамп_на_страницу(страница, задание, путь_шрифта)
        документ.save(выходной_pdf, garbage=4, deflate=True)

    return выходной_pdf


def разобрать_аргументы() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Добавляет визуальный штамп электронной подписи в существующий PDF."
    )
    parser.add_argument("--config", required=True, type=Path, help="Путь к JSON-заданию")
    parser.add_argument("--version", action="version", version="1.0.0")
    return parser.parse_args()


def main() -> int:
    аргументы = разобрать_аргументы()
    try:
        задание = загрузить_задание(аргументы.config)
        результат = добавить_штамп(задание)
        print(f"Готово: {результат}")
        return 0
    except Exception as ошибка:
        print(f"Ошибка: {ошибка}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
