import json
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf


КОРЕНЬ_ПРОЕКТА = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(КОРЕНЬ_ПРОЕКТА / "src"))

from pdf_signature_stamp import добавить_штамп, загрузить_задание  # noqa: E402


class ТестШтампаPDF(unittest.TestCase):
    def test_штамп_добавляется_на_каждую_страницу(self) -> None:
        with tempfile.TemporaryDirectory() as каталог:
            каталог = Path(каталог)
            входной_pdf = каталог / "input.pdf"
            выходной_pdf = каталог / "output.pdf"
            файл_задания = каталог / "job.json"

            with pymupdf.open() as документ:
                документ.new_page(width=595, height=842)
                документ.new_page(width=595, height=842)
                документ.save(входной_pdf)

            задание = {
                "input_pdf": str(входной_pdf),
                "output_pdf": str(выходной_pdf),
                "certificate": "0000000000000000000000000000000000000000",
                "owner": "ПОЛЬЗОВАТЕЛЬ",
                "valid_until": "31.12.2099",
                "power_of_attorney": "00000000-0000-0000-0000-000000000000",
                "pages": "all",
            }
            файл_задания.write_text(json.dumps(задание, ensure_ascii=False), encoding="utf-8-sig")

            добавить_штамп(загрузить_задание(файл_задания))

            self.assertTrue(выходной_pdf.is_file())
            with pymupdf.open(выходной_pdf) as результат:
                self.assertEqual(результат.page_count, 2)
                for страница in результат:
                    текст = страница.get_text().replace("\u00a0", " ")
                    self.assertIn("ДОКУМЕНТ ПОДПИСАН", текст)
                    self.assertIn("ПОЛЬЗОВАТЕЛЬ", текст)


if __name__ == "__main__":
    unittest.main()
