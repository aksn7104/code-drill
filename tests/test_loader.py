"""読み込み（loader.py）の単体テスト

説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import tempfile
import unittest
from pathlib import Path

import loader

SAMPLE = Path(__file__).resolve().parent.parent / "questions" / "python" / "batting_01_variables.yaml"

ONE_QUESTION = (
    "- id: t-1\n"
    "  unit: テスト\n"
    "  level: 1\n"
    "  type: blank\n"
    "  question: 問題文\n"
    "  code: x = ___\n"
    "  answer: a\n"
    "  explanation: 解説\n"
)


class LoadQuestionsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)

    def test_01_sample_loads(self):
        """TC-LDR-01 | 正常系 | 同梱の見本の問題集を読み込める

        入力：questions/python/batting_01_variables.yaml
        期待：問題（辞書）のリストが返り、1問以上ある
        根拠：設計書 §4
        """
        questions = loader.load_questions(SAMPLE)
        self.assertIsInstance(questions, list)
        self.assertGreater(len(questions), 0)
        self.assertIsInstance(questions[0], dict)

    def test_02_utf8_with_bom(self):
        """TC-LDR-02 | 環境差 | BOM付きのUTF-8のファイルも読み込める（Windowsのメモ帳で保存した場合）

        入力：先頭にBOMがあるUTF-8のYAML
        期待：読み込めて、日本語の項目が文字化けしない
        根拠：Windowsのメモ帳でUTF-8（BOM付き）として保存する使い方を想定
        """
        path = self.folder / "bom.yaml"
        path.write_bytes(b"\xef\xbb\xbf" + ONE_QUESTION.encode("utf-8"))
        questions = loader.load_questions(path)
        self.assertEqual(questions[0]["id"], "t-1")
        self.assertEqual(questions[0]["unit"], "テスト")

    def test_03_crlf_line_endings(self):
        """TC-LDR-03 | 環境差 | Windowsの改行（CRLF）のファイルも読み込める

        入力：改行が CRLF のYAML
        期待：読み込めて、answer の末尾に改行文字が残らない
        根拠：Windowsで編集したファイルを想定
        """
        path = self.folder / "crlf.yaml"
        path.write_bytes(ONE_QUESTION.replace("\n", "\r\n").encode("utf-8"))
        questions = loader.load_questions(path)
        self.assertEqual(questions[0]["answer"], "a")

    def test_04_missing_file(self):
        """TC-LDR-04 | 異常系 | 存在しないファイルを指定すると、読み込みエラー（QuestionFileError）になる

        入力：存在しないパス
        期待：QuestionFileError（メッセージにファイル名を含む）
        根拠：設計書 §5-1。誤ったパスの指定でも分かるエラーにする
        不具合：D-04
        """
        with self.assertRaises(loader.QuestionFileError) as ctx:
            loader.load_questions(self.folder / "none.yaml")
        self.assertIn("none.yaml", str(ctx.exception))

    def test_05_empty_file(self):
        """TC-LDR-05 | 境界値 | 中身が空のファイルは、問題が0問として扱う

        入力：0バイトのYAML
        期待：空のリスト
        根拠：設計書 §4
        不具合：D-03
        """
        path = self.folder / "empty.yaml"
        path.write_text("", encoding="utf-8")
        self.assertEqual(loader.load_questions(path), [])

    def test_06_syntax_error(self):
        """TC-LDR-06 | 異常系 | YAMLの書き方に誤りがあると、読み込みエラーになる

        入力：インデントが崩れ、引用符が閉じていないYAML
        期待：QuestionFileError
        根拠：AIが作ったYAMLの書き間違いを想定（設計書 §9）
        不具合：D-04
        """
        path = self.folder / "broken.yaml"
        path.write_text('- id: "t-1\n   unit: [テスト\n', encoding="utf-8")
        with self.assertRaises(loader.QuestionFileError):
            loader.load_questions(path)

    def test_07_not_a_list(self):
        """TC-LDR-07 | 異常系 | 問題のリストではない形式だと、読み込みエラーになる

        入力：先頭が辞書のYAML、問題が文字列のリストのYAML
        期待：どちらも QuestionFileError
        根拠：設計書 §4（1ファイルは問題のリスト）
        不具合：D-03
        """
        for name, text in (("dict.yaml", "id: t-1\nunit: テスト\n"), ("strings.yaml", "- a\n- b\n")):
            path = self.folder / name
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(loader.QuestionFileError, msg=name):
                loader.load_questions(path)


class LoadRulesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.question_file = self.folder / "dummy.yaml"

    def test_08_default_without_language_file(self):
        """TC-LDR-08 | 正常系 | _language.yaml がないときは、既定値を使う

        入力：_language.yaml のないフォルダ
        期待：区別する・空白は無視する（既定値）
        根拠：設計書 §4（このファイルがない言語は、既定値で動く）
        """
        self.assertEqual(loader.load_rules(self.question_file), loader.DEFAULT_RULES)

    def test_09_language_file_overrides(self):
        """TC-LDR-09 | 正常系 | _language.yaml に書いた項目だけが上書きされる

        入力：case_sensitive: false と name: SQL だけを書いた _language.yaml
        期待：case_sensitive は false、ignore_spaces は既定値の true、name は SQL
        根拠：設計書 §4
        """
        (self.folder / "_language.yaml").write_text(
            "name: SQL\ncase_sensitive: false\n", encoding="utf-8"
        )
        rules = loader.load_rules(self.question_file)
        self.assertFalse(rules["case_sensitive"])
        self.assertTrue(rules["ignore_spaces"])
        self.assertEqual(rules["name"], "SQL")

    def test_10_defaults_not_modified(self):
        """TC-LDR-10 | 正常系 | 読み込みのあとも、既定値（DEFAULT_RULES）が書き換わらない

        入力：case_sensitive: false の _language.yaml を読み込んだあと、DEFAULT_RULES を確認
        期待：case_sensitive は true のまま
        根拠：ある言語の設定が、ほかの言語に影響しないようにするため
        """
        (self.folder / "_language.yaml").write_text("case_sensitive: false\n", encoding="utf-8")
        loader.load_rules(self.question_file)
        self.assertTrue(loader.DEFAULT_RULES["case_sensitive"])

    def test_11_empty_language_file(self):
        """TC-LDR-11 | 境界値 | _language.yaml が空のときは、既定値を使う

        入力：0バイトの _language.yaml
        期待：既定値
        根拠：設計書 §4
        """
        (self.folder / "_language.yaml").write_text("", encoding="utf-8")
        self.assertEqual(loader.load_rules(self.question_file), loader.DEFAULT_RULES)

    def test_12_language_file_syntax_error(self):
        """TC-LDR-12 | 異常系 | _language.yaml の書き方に誤りがあると、読み込みエラーになる

        入力：引用符が閉じていない _language.yaml
        期待：QuestionFileError
        根拠：AIが作った設定ファイルの書き間違いを想定（設計書 §9）
        不具合：D-04
        """
        (self.folder / "_language.yaml").write_text('name: "SQL\n', encoding="utf-8")
        with self.assertRaises(loader.QuestionFileError):
            loader.load_rules(self.question_file)

    def test_13_language_file_not_a_mapping(self):
        """TC-LDR-13 | 異常系 | _language.yaml が「項目: 値」の形でないと、読み込みエラーになる

        入力：リストの形（「- a」「- b」）の _language.yaml
        期待：QuestionFileError
        根拠：AIが作った設定ファイルの書き間違いを想定（設計書 §9）
        """
        (self.folder / "_language.yaml").write_text("- a\n- b\n", encoding="utf-8")
        with self.assertRaises(loader.QuestionFileError):
            loader.load_rules(self.question_file)


if __name__ == "__main__":
    unittest.main()
