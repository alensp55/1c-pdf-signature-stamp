import json
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf


КОРЕНЬ_ПРОЕКТА = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(КОРЕНЬ_ПРОЕКТА / "src"))

from pdf_signature_stamp import (  # noqa: E402
    ЗаданиеШтампа,
    добавить_штамп,
    загрузить_задание,
    загрузить_задания,
    обработать_пакет,
)


class ТестШтампаPDF(unittest.TestCase):
    def _задание(self, входной_pdf: Path, выходной_pdf: Path, **дополнительно: object) -> dict[str, object]:
        задание: dict[str, object] = {
            "input_pdf": str(входной_pdf),
            "output_pdf": str(выходной_pdf),
            "certificate": "DEMO-CERTIFICATE",
            "owner": "ПОЛЬЗОВАТЕЛЬ",
            "valid_until": "31.12.2099",
            "power_of_attorney": "DEMO-AUTHORITY",
            "pages": "all",
        }
        задание.update(дополнительно)
        return задание

    def _создать_pdf(self, путь: Path, количество_страниц: int = 2) -> None:
        with pymupdf.open() as документ:
            for _ in range(количество_страниц):
                документ.new_page(width=595, height=842)
            документ.save(путь)

    def test_штамп_добавляется_на_каждую_страницу(self) -> None:
        with tempfile.TemporaryDirectory(dir=КОРЕНЬ_ПРОЕКТА) as каталог:
            каталог = Path(каталог)
            входной_pdf = каталог / "input.pdf"
            выходной_pdf = каталог / "output.pdf"
            файл_задания = каталог / "job.json"

            self._создать_pdf(входной_pdf)
            задание = self._задание(входной_pdf, выходной_pdf)
            файл_задания.write_text(json.dumps(задание, ensure_ascii=False), encoding="utf-8-sig")

            добавить_штамп(загрузить_задание(файл_задания))

            self.assertTrue(выходной_pdf.is_file())
            with pymupdf.open(выходной_pdf) as результат:
                self.assertEqual(результат.page_count, 2)
                for страница in результат:
                    текст = страница.get_text().replace("\u00a0", " ")
                    self.assertIn("ВИЗУАЛЬНЫЙ ШТАМП", текст)
                    self.assertIn("КРИПТОГРАФИЯ НЕ ВЫПОЛНЯЕТСЯ", текст)
                    self.assertIn("ПОЛЬЗОВАТЕЛЬ", текст)

    def test_можно_выбрать_номера_страниц_и_правый_верхний_угол(self) -> None:
        with tempfile.TemporaryDirectory(dir=КОРЕНЬ_ПРОЕКТА) as каталог:
            каталог = Path(каталог)
            входной_pdf = каталог / "input.pdf"
            выходной_pdf = каталог / "output.pdf"
            self._создать_pdf(входной_pdf, 3)

            добавить_штамп(self._задание(входной_pdf, выходной_pdf, pages=[1, 3], position="top_right"))

            with pymupdf.open(выходной_pdf) as результат:
                тексты = [страница.get_text().replace("\u00a0", " ") for страница in результат]
                self.assertIn("ВИЗУАЛЬНЫЙ ШТАМП", тексты[0])
                self.assertNotIn("ВИЗУАЛЬНЫЙ ШТАМП", тексты[1])
                self.assertIn("ВИЗУАЛЬНЫЙ ШТАМП", тексты[2])

    def test_проверка_отклоняет_неполные_координаты_и_повтор_страницы(self) -> None:
        основа = self._задание(Path("input.pdf"), Path("output.pdf"))
        with self.assertRaisesRegex(ValueError, "stamp_x и stamp_y"):
            ЗаданиеШтампа.из_словаря({**основа, "stamp_x": 10})
        with self.assertRaisesRegex(ValueError, "не должны повторяться"):
            ЗаданиеШтампа.из_словаря({**основа, "pages": [1, 1]})
        with self.assertRaisesRegex(ValueError, "stamp_height должно быть больше 0"):
            ЗаданиеШтампа.из_словаря({**основа, "stamp_height": float("nan")})

    def test_загрузка_пакета_и_внедренный_исполнитель(self) -> None:
        class ИсполнительДляТеста:
            def __init__(self) -> None:
                self.вызовы = 0

            def выполнить(self, задание: ЗаданиеШтампа) -> Path:
                self.вызовы += 1
                if self.вызовы == 1:
                    raise RuntimeError("ожидаемая ошибка")
                return задание.выходной_pdf

        with tempfile.TemporaryDirectory(dir=КОРЕНЬ_ПРОЕКТА) as каталог:
            каталог = Path(каталог)
            путь_пакета = каталог / "batch.json"
            задания = [
                self._задание(каталог / "first.pdf", каталог / "first-out.pdf"),
                self._задание(каталог / "second.pdf", каталог / "second-out.pdf"),
            ]
            путь_пакета.write_text(json.dumps({"jobs": задания}, ensure_ascii=False), encoding="utf-8")

            загруженные = загрузить_задания(путь_пакета)
            исполнитель = ИсполнительДляТеста()
            результаты = обработать_пакет(загруженные, исполнитель, продолжать_после_ошибки=True)

            self.assertEqual(2, исполнитель.вызовы)
            self.assertEqual([False, True], [результат.успешно for результат in результаты])

    def test_временный_результат_удаляется_при_ошибке(self) -> None:
        with tempfile.TemporaryDirectory(dir=КОРЕНЬ_ПРОЕКТА) as каталог:
            каталог = Path(каталог)
            входной_pdf = каталог / "input.pdf"
            выходной_pdf = каталог / "output.pdf"
            self._создать_pdf(входной_pdf)

            with self.assertRaisesRegex(ValueError, "превышающий количество страниц"):
                добавить_штамп(self._задание(входной_pdf, выходной_pdf, pages=[3]))

            self.assertFalse(выходной_pdf.exists())
            self.assertEqual([], list(каталог.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
