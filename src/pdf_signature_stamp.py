"""Добавляет информационный визуальный штамп в готовый PDF без криптографической подписи."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

import pymupdf


ОБЯЗАТЕЛЬНЫЕ_ПОЛЯ = (
    "input_pdf",
    "output_pdf",
    "certificate",
    "owner",
    "valid_until",
    "power_of_attorney",
)
РЕЖИМЫ_СТРАНИЦ = {"all", "first", "last"}
ПОЗИЦИИ = {"bottom_left", "bottom_right", "top_left", "top_right"}


@dataclass(frozen=True)
class ЗаданиеШтампа:
    входной_pdf: Path
    выходной_pdf: Path
    сертификат: str
    владелец: str
    действителен_до: str
    доверенность: str
    страницы: str | tuple[int, ...] = "all"
    доля_ширины: float = 0.49
    высота: float = 100.0
    отступ_x: float = 40.0
    отступ_y: float = 60.0
    позиция: str = "bottom_left"
    x: float | None = None
    y: float | None = None
    путь_шрифта: str | None = None

    @classmethod
    def из_словаря(cls, данные: Mapping[str, Any]) -> ЗаданиеШтампа:
        if not isinstance(данные, Mapping):
            raise ValueError("Задание должно быть JSON-объектом")
        отсутствуют = [поле for поле in ОБЯЗАТЕЛЬНЫЕ_ПОЛЯ if not данные.get(поле)]
        if отсутствуют:
            raise ValueError("Не заполнены обязательные поля: " + ", ".join(отсутствуют))

        страницы = _проверить_страницы(данные.get("pages", "all"))
        доля_ширины = _положительное_число(данные.get("stamp_width_ratio", 0.49), "stamp_width_ratio")
        if доля_ширины > 1:
            raise ValueError("stamp_width_ratio должен быть не больше 1")
        высота = _положительное_число(данные.get("stamp_height", 100), "stamp_height")
        отступ_x = _неотрицательное_число(данные.get("left_margin", 40), "left_margin")
        отступ_y = _неотрицательное_число(данные.get("bottom_margin", 60), "bottom_margin")
        позиция = str(данные.get("position", "bottom_left"))
        if позиция not in ПОЗИЦИИ:
            raise ValueError("position должен быть bottom_left, bottom_right, top_left или top_right")

        x = _необязательная_координата(данные.get("stamp_x"), "stamp_x")
        y = _необязательная_координата(данные.get("stamp_y"), "stamp_y")
        if (x is None) != (y is None):
            raise ValueError("stamp_x и stamp_y должны быть указаны вместе")

        входной_pdf = Path(str(данные["input_pdf"])).expanduser().resolve()
        выходной_pdf = Path(str(данные["output_pdf"])).expanduser().resolve()
        if входной_pdf == выходной_pdf:
            raise ValueError("Входной и выходной PDF должны быть разными файлами")

        путь_шрифта = данные.get("font_path")
        return cls(
            входной_pdf=входной_pdf,
            выходной_pdf=выходной_pdf,
            сертификат=str(данные["certificate"]).strip(),
            владелец=str(данные["owner"]).strip(),
            действителен_до=str(данные["valid_until"]).strip(),
            доверенность=str(данные["power_of_attorney"]).strip(),
            страницы=страницы,
            доля_ширины=доля_ширины,
            высота=высота,
            отступ_x=отступ_x,
            отступ_y=отступ_y,
            позиция=позиция,
            x=x,
            y=y,
            путь_шрифта=str(путь_шрифта) if путь_шрифта else None,
        )


class ИсполнительШтампа(Protocol):
    def выполнить(self, задание: ЗаданиеШтампа) -> Path: ...


@dataclass(frozen=True)
class РезультатПакета:
    задание: ЗаданиеШтампа
    результат: Path | None
    ошибка: str | None

    @property
    def успешно(self) -> bool:
        return self.ошибка is None


def _положительное_число(значение: Any, имя: str) -> float:
    if isinstance(значение, bool):
        raise ValueError(f"{имя} должно быть числом")
    try:
        число = float(значение)
    except (TypeError, ValueError) as ошибка:
        raise ValueError(f"{имя} должно быть числом") from ошибка
    if not math.isfinite(число) or число <= 0:
        raise ValueError(f"{имя} должно быть больше 0")
    return число


def _неотрицательное_число(значение: Any, имя: str) -> float:
    if isinstance(значение, bool):
        raise ValueError(f"{имя} должно быть числом")
    try:
        число = float(значение)
    except (TypeError, ValueError) as ошибка:
        raise ValueError(f"{имя} должно быть числом") from ошибка
    if not math.isfinite(число) or число < 0:
        raise ValueError(f"{имя} не может быть отрицательным")
    return число


def _необязательная_координата(значение: Any, имя: str) -> float | None:
    if значение is None:
        return None
    return _неотрицательное_число(значение, имя)


def _проверить_страницы(значение: Any) -> str | tuple[int, ...]:
    if isinstance(значение, str):
        if значение not in РЕЖИМЫ_СТРАНИЦ:
            raise ValueError("pages должен быть all, first, last или массивом номеров страниц")
        return значение
    if not isinstance(значение, list) or not значение:
        raise ValueError("pages должен быть непустым массивом положительных номеров страниц")
    if any(isinstance(номер, bool) or not isinstance(номер, int) or номер < 1 for номер in значение):
        raise ValueError("Номера страниц должны быть положительными целыми числами")
    if len(set(значение)) != len(значение):
        raise ValueError("Номера страниц не должны повторяться")
    return tuple(значение)


def загрузить_задания(путь: Path) -> list[ЗаданиеШтампа]:
    try:
        with путь.open("r", encoding="utf-8-sig") as файл:
            данные = json.load(файл)
    except json.JSONDecodeError as ошибка:
        raise ValueError(f"Некорректный JSON: {ошибка}") from ошибка

    элементы = данные["jobs"] if isinstance(данные, dict) and "jobs" in данные else [данные]
    if not isinstance(элементы, list) or not элементы:
        raise ValueError("Пакет должен содержать непустой массив jobs")
    return [ЗаданиеШтампа.из_словаря(элемент) for элемент in элементы]


def загрузить_задание(путь: Path) -> dict[str, Any]:
    """Совместимая точка входа для одиночного задания."""
    задания = загрузить_задания(путь)
    if len(задания) != 1:
        raise ValueError("Ожидалось одно задание, но получен пакет")
    return _в_словарь(задания[0])


def _в_словарь(задание: ЗаданиеШтампа) -> dict[str, Any]:
    return {
        "input_pdf": str(задание.входной_pdf),
        "output_pdf": str(задание.выходной_pdf),
        "certificate": задание.сертификат,
        "owner": задание.владелец,
        "valid_until": задание.действителен_до,
        "power_of_attorney": задание.доверенность,
        "pages": list(задание.страницы) if isinstance(задание.страницы, tuple) else задание.страницы,
        "stamp_width_ratio": задание.доля_ширины,
        "stamp_height": задание.высота,
        "left_margin": задание.отступ_x,
        "bottom_margin": задание.отступ_y,
        "position": задание.позиция,
        "stamp_x": задание.x,
        "stamp_y": задание.y,
        "font_path": задание.путь_шрифта,
    }


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
    raise FileNotFoundError("Не найден шрифт с поддержкой кириллицы. Укажите font_path в задании.")


def выбрать_страницы(документ: pymupdf.Document, режим: str | Sequence[int]) -> list[pymupdf.Page]:
    if режим == "first":
        return [документ[0]]
    if режим == "last":
        return [документ[-1]]
    if режим == "all":
        return list(документ)
    индексы = [номер - 1 for номер in режим]
    if any(индекс >= документ.page_count for индекс in индексы):
        raise ValueError("В pages указан номер, превышающий количество страниц документа")
    return [документ[индекс] for индекс in индексы]


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


def _рамка_штампа(страница: pymupdf.Page, задание: ЗаданиеШтампа) -> pymupdf.Rect:
    ширина = (страница.rect.width - 2 * задание.отступ_x) * задание.доля_ширины
    if ширина <= 0:
        raise ValueError("Ширина штампа должна быть положительной")

    if задание.x is not None and задание.y is not None:
        x0, y0 = задание.x, задание.y
    else:
        x0 = задание.отступ_x
        y0 = страница.rect.height - задание.отступ_y - задание.высота
        if задание.позиция.endswith("right"):
            x0 = страница.rect.width - задание.отступ_x - ширина
        if задание.позиция.startswith("top"):
            y0 = задание.отступ_y

    рамка = pymupdf.Rect(x0, y0, x0 + ширина, y0 + задание.высота)
    if not страница.rect.contains(рамка):
        raise ValueError("Штамп выходит за границы страницы. Проверьте позицию, координаты и размеры")
    return рамка


def добавить_штамп_на_страницу(
    страница: pymupdf.Page,
    задание: ЗаданиеШтампа,
    путь_шрифта: Path,
) -> None:
    рамка = _рамка_штампа(страница, задание)
    синий = (0.0, 70 / 255, 200 / 255)
    внутренний_отступ = 10.0
    доступная_ширина = рамка.width - 2 * внутренний_отступ
    шрифт = pymupdf.Font(fontfile=str(путь_шрифта))

    заголовок = ["ВИЗУАЛЬНЫЙ ШТАМП", "КРИПТОГРАФИЯ НЕ ВЫПОЛНЯЕТСЯ"]
    реквизиты = [
        f"Сертификат {задание.сертификат}",
        f"Владелец {задание.владелец}",
        f"Действителен по {задание.действителен_до}",
        f"Доверенность № {задание.доверенность}",
    ]
    размер_заголовка = подобрать_размер(шрифт, заголовок, 11, доступная_ширина, 7)
    размер_реквизитов = подобрать_размер(шрифт, реквизиты, 8, доступная_ширина, 5)
    требуемая_высота = (
        2 * внутренний_отступ
        + len(заголовок) * размер_заголовка * 1.25
        + 2.5
        + len(реквизиты) * размер_реквизитов * 1.25
    )
    if требуемая_высота > рамка.height:
        raise ValueError("Высоты штампа недостаточно для текста")

    страница.draw_rect(рамка, color=синий, width=1.5, overlay=True)
    текущий_y = рамка.y0 + внутренний_отступ + размер_заголовка
    текущий_y = вставить_строки(
        страница,
        заголовок,
        рамка.x0 + внутренний_отступ,
        текущий_y,
        размер_заголовка,
        путь_шрифта,
        "stampfont",
        синий,
    )
    вставить_строки(
        страница,
        реквизиты,
        рамка.x0 + внутренний_отступ,
        текущий_y + 2.5,
        размер_реквизитов,
        путь_шрифта,
        "stampfont",
        синий,
    )


class ИсполнительPyMuPDF:
    def выполнить(self, задание: ЗаданиеШтампа) -> Path:
        if not задание.входной_pdf.is_file():
            raise FileNotFoundError(f"Входной PDF не найден: {задание.входной_pdf}")
        задание.выходной_pdf.parent.mkdir(parents=True, exist_ok=True)
        путь_шрифта = найти_шрифт(задание.путь_шрифта)
        временный_путь: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{задание.выходной_pdf.stem}-",
                suffix=".pdf.tmp",
                dir=задание.выходной_pdf.parent,
                delete=False,
            ) as временный_файл:
                временный_путь = Path(временный_файл.name)
            with pymupdf.open(задание.входной_pdf) as документ:
                if документ.page_count == 0:
                    raise ValueError("Входной PDF не содержит страниц")
                for страница in выбрать_страницы(документ, задание.страницы):
                    добавить_штамп_на_страницу(страница, задание, путь_шрифта)
                документ.save(временный_путь, garbage=4, deflate=True)
            временный_путь.replace(задание.выходной_pdf)
            временный_путь = None
            return задание.выходной_pdf
        finally:
            if временный_путь is not None:
                временный_путь.unlink(missing_ok=True)


def добавить_штамп(задание: Mapping[str, Any] | ЗаданиеШтампа) -> Path:
    нормализованное = задание if isinstance(задание, ЗаданиеШтампа) else ЗаданиеШтампа.из_словаря(задание)
    return ИсполнительPyMuPDF().выполнить(нормализованное)


def обработать_пакет(
    задания: Iterable[ЗаданиеШтампа],
    исполнитель: ИсполнительШтампа | None = None,
    продолжать_после_ошибки: bool = False,
) -> list[РезультатПакета]:
    выбранный_исполнитель = исполнитель or ИсполнительPyMuPDF()
    результаты: list[РезультатПакета] = []
    for задание in задания:
        try:
            путь = выбранный_исполнитель.выполнить(задание)
            результаты.append(РезультатПакета(задание, путь, None))
        except Exception as ошибка:
            результаты.append(РезультатПакета(задание, None, str(ошибка)))
            if not продолжать_после_ошибки:
                break
    return результаты


def разобрать_аргументы() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Добавляет информационный визуальный штамп в существующий PDF.")
    parser.add_argument("--config", required=True, type=Path, help="Путь к JSON-заданию или пакету")
    parser.add_argument("--continue-on-error", action="store_true", help="Продолжить пакет после ошибки")
    parser.add_argument("--version", action="version", version="2.0.0")
    return parser.parse_args()


def main() -> int:
    аргументы = разобрать_аргументы()
    try:
        задания = загрузить_задания(аргументы.config)
        результаты = обработать_пакет(задания, продолжать_после_ошибки=аргументы.continue_on_error)
        ошибки = [результат for результат in результаты if not результат.успешно]
        for результат in ошибки:
            print(f"Ошибка задания {результат.задание.выходной_pdf}: {результат.ошибка}", file=sys.stderr)
        print(f"Обработано успешно: {len(результаты) - len(ошибки)} из {len(задания)}")
        return 1 if ошибки or len(результаты) != len(задания) else 0
    except Exception as ошибка:
        print(f"Ошибка: {ошибка}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
