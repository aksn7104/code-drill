"""採点（grading.py）の単体テスト

各テストの説明（docstring）は、次の決まった形で書く。run_tests.py が読み取って、
試験仕様書と試験結果報告を作る。

    TC-GRD-01 | 観点 | 試験内容（1行）
    入力：…
    期待：…
    根拠：…
    不具合：D-01（関連する不具合票があるときだけ）
"""

import unittest

from grading import is_correct, normalize, to_answer_text

PYTHON_RULES = {"case_sensitive": True, "ignore_spaces": True}
SQL_RULES = {"case_sensitive": False, "ignore_spaces": True}

CHOICE_Q = {"type": "choice", "choices": ["+", "-", "*", "/"], "answer": "+"}
BLANK_Q = {"type": "blank", "answer": "/"}
MULTI_Q = {"type": "blank", "answer": ["f", "F"]}
EXPR_Q = {"type": "blank", "answer": "doubles * 2"}


class ToAnswerTextTest(unittest.TestCase):
    def test_01_choice_number(self):
        """TC-GRD-01 | 正常系 | 選択式で番号を入力すると、その番号の選択肢の文字になる

        入力：選択肢が4つ（+ - * /）の問題に、「1」と「4」
        期待：「+」と「/」
        根拠：設計書 §5-6「選択肢は番号で選び」
        """
        self.assertEqual(to_answer_text("1", CHOICE_Q), "+")
        self.assertEqual(to_answer_text("4", CHOICE_Q), "/")

    def test_02_choice_number_boundary(self):
        """TC-GRD-02 | 境界値 | 選択肢の番号の範囲の両端と、そのすぐ外

        入力：選択肢が4つの問題に、「1」「4」（両端）と「0」「5」（範囲の外）
        期待：両端は選択肢の文字になる。範囲の外は番号のまま（文字として採点される）
        根拠：設計書 §5-6
        """
        self.assertEqual(to_answer_text("1", CHOICE_Q), "+")
        self.assertEqual(to_answer_text("4", CHOICE_Q), "/")
        self.assertEqual(to_answer_text("0", CHOICE_Q), "0")
        self.assertEqual(to_answer_text("5", CHOICE_Q), "5")

    def test_03_not_a_number(self):
        """TC-GRD-03 | 異常系 | 選択式で、番号として読めない入力はそのまま返す

        入力：空文字、「-1」、「1.5」、「abc」、「1a」
        期待：例外を出さず、入力した文字がそのまま返る
        根拠：設計書 §5-6（誤入力で止まらない）
        """
        for raw in ("", "-1", "1.5", "abc", "1a"):
            self.assertEqual(to_answer_text(raw, CHOICE_Q), raw)

    def test_04_blank_question_keeps_number(self):
        """TC-GRD-04 | 正常系 | 空欄式では、番号に見える入力も変換しない

        入力：空欄式の問題に「1」
        期待：「1」のまま
        根拠：設計書 §4（空欄式は文字で答える）
        """
        self.assertEqual(to_answer_text("1", BLANK_Q), "1")

    def test_05_surrounding_spaces(self):
        """TC-GRD-05 | 正常系 | 入力の前後の空白は取り除く

        入力：空欄式に「  /  」、選択式に「  2 」
        期待：「/」、「-」
        根拠：設計書 §4（_language.yaml の ignore_spaces）
        """
        self.assertEqual(to_answer_text("  /  ", BLANK_Q), "/")
        self.assertEqual(to_answer_text("  2 ", CHOICE_Q), "-")

    def test_06_fullwidth_digits(self):
        """TC-GRD-06 | 環境差 | 日本語入力のまま（全角数字）でも、選択肢の番号として読める

        入力：選択式に全角の「２」と「４」
        期待：「-」と「/」
        根拠：日本語IMEをオンにしたまま入力する使い方を想定
        """
        self.assertEqual(to_answer_text("２", CHOICE_Q), "-")
        self.assertEqual(to_answer_text("４", CHOICE_Q), "/")

    def test_09_special_digit_characters(self):
        """TC-GRD-09 | 異常系 | 数字に似た特殊な文字を入力しても、例外を出さない

        入力：選択式に上付き数字「²」と丸数字「①」
        期待：例外を出さず、文字列を返す
        根拠：設計書 §5-6（誤入力で止まらない）
        不具合：D-02
        """
        for raw in ("²", "①"):
            self.assertIsInstance(to_answer_text(raw, CHOICE_Q), str)


class NormalizeTest(unittest.TestCase):
    def test_10_ignore_spaces(self):
        """TC-GRD-10 | 正常系 | 空白を無視する設定のオン・オフ

        入力：「doubles * 2」を、ignore_spaces が true と false で
        期待：true なら「doubles*2」。false なら空白が残る（前後の空白だけ除く）
        根拠：設計書 §4（_language.yaml の ignore_spaces）
        """
        self.assertEqual(normalize("doubles * 2", PYTHON_RULES), "doubles*2")
        rules = {"case_sensitive": True, "ignore_spaces": False}
        self.assertEqual(normalize(" a b ", rules), "a b")

    def test_11_case_rule(self):
        """TC-GRD-11 | 正常系 | 大文字・小文字を区別する設定のオン・オフ

        入力：「WHERE」を、case_sensitive が false（SQL）と true（Python）で
        期待：false なら「where」。true なら「WHERE」のまま
        根拠：設計書 §4（_language.yaml の case_sensitive）
        """
        self.assertEqual(normalize("WHERE", SQL_RULES), "where")
        self.assertEqual(normalize("WHERE", PYTHON_RULES), "WHERE")


class IsCorrectTest(unittest.TestCase):
    def test_12_correct_and_wrong(self):
        """TC-GRD-12 | 正常系 | 正解は正解、間違いは不正解になる

        入力：正解が「/」の問題に「/」と「*」
        期待：True と False
        根拠：設計書 §5-7
        """
        self.assertTrue(is_correct("/", BLANK_Q, PYTHON_RULES))
        self.assertFalse(is_correct("*", BLANK_Q, PYTHON_RULES))

    def test_13_multiple_answers(self):
        """TC-GRD-13 | 正常系 | 正解が複数の書き方（リスト）のとき、どれでも正解になる

        入力：正解が「f」「F」の問題に「f」「F」「g」
        期待：True、True、False
        根拠：設計書 §4（answer は複数の書き方を認めるときはリスト）
        """
        self.assertTrue(is_correct("f", MULTI_Q, PYTHON_RULES))
        self.assertTrue(is_correct("F", MULTI_Q, PYTHON_RULES))
        self.assertFalse(is_correct("g", MULTI_Q, PYTHON_RULES))

    def test_14_language_rules(self):
        """TC-GRD-14 | 正常系 | 言語ごとの採点のきまりが結果に反映される

        入力：正解が「WHERE」の問題に「where」を、SQL のきまりと Python のきまりで
        期待：SQL なら正解、Python なら不正解
        根拠：設計書 §4（言語ごとの _language.yaml）
        """
        q = {"type": "blank", "answer": "WHERE"}
        self.assertTrue(is_correct("where", q, SQL_RULES))
        self.assertFalse(is_correct("where", q, PYTHON_RULES))

    def test_15_empty_input(self):
        """TC-GRD-15 | 境界値 | 何も入力しなかった（空・空白だけ）ときは不正解

        入力：「」と「   」
        期待：どちらも False
        根拠：設計書 §5-7
        """
        self.assertFalse(is_correct("", BLANK_Q, PYTHON_RULES))
        self.assertFalse(is_correct("   ", BLANK_Q, PYTHON_RULES))

    def test_16_answer_written_as_number(self):
        """TC-GRD-16 | 異常系 | 正解が数値として読み込まれても（answer: 1）、「1」で正解になる

        入力：YAML に「answer: 1」と書いた問題（数値の 1 になる）に「1」
        期待：True
        根拠：YAML は引用符のない 1 を数値として読むため
        """
        self.assertTrue(is_correct("1", {"type": "blank", "answer": 1}, PYTHON_RULES))

    def test_07_fullwidth_letters(self):
        """TC-GRD-07 | 環境差 | 日本語入力のまま（全角の英字）でも正解になる

        入力：正解が「f」「F」の問題に、全角の「ｆ」と「Ｆ」
        期待：どちらも True
        根拠：日本語IMEをオンにしたまま入力する使い方を想定
        不具合：D-01
        """
        self.assertTrue(is_correct("ｆ", MULTI_Q, PYTHON_RULES))
        self.assertTrue(is_correct("Ｆ", MULTI_Q, PYTHON_RULES))

    def test_08_fullwidth_symbols_and_space(self):
        """TC-GRD-08 | 環境差 | 全角の記号や全角スペースが混じっても正解になる

        入力：正解が「/」の問題に全角の「／」。正解が「doubles * 2」の問題に全角スペース入りの「doubles　*　2」
        期待：どちらも True
        根拠：日本語IMEをオンにしたまま入力する使い方を想定
        不具合：D-01
        """
        self.assertTrue(is_correct("／", BLANK_Q, PYTHON_RULES))
        self.assertTrue(is_correct("doubles　*　2", EXPR_Q, PYTHON_RULES))

    def test_17_answer_written_as_null(self):
        """TC-GRD-17 | 異常系 | 正解が None（引用符なしの NULL）の問題でも、採点がエラーで落ちず、True か False を返す

        入力：answer が None の問題（YAML で「answer: NULL」と書いた場合）に、「NULL」と入力
        期待：エラーにならず、True か False が返る（正解にはならない。None は文字「None」として扱われる）
        根拠：SQL の問題で NULL を答えさせる場面を想定。引用符なしの NULL は、出題の前に検査で止める
        不具合：D-07（段階6-1で対応。検出して「引用符で囲んでください」と知らせる方針に決めた。検出の試験は TC-CHK-08・TC-CLI-35）
        """
        result = is_correct("NULL", {"type": "blank", "answer": None}, SQL_RULES)
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
