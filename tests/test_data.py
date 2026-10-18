"""同梱の問題集（questions/ の下のすべてのYAML）のデータ検証

言語のフォルダを足したときも、自動でこのテストの対象になる。
説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import unittest
from pathlib import Path

import loader

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_KEYS = ["id", "unit", "level", "type", "question", "code", "answer", "explanation"]


def all_question_files():
    """questions/ の下にある問題集のファイル（_language.yaml は除く）を返す。"""
    files = sorted((ROOT / "questions").glob("*/*.yaml"))
    return [f for f in files if not f.name.startswith("_")]


def all_questions():
    """(ファイル名, 問題) の組を、すべての問題集から集めて返す。"""
    found = []
    for path in all_question_files():
        for q in loader.load_questions(path):
            found.append((f"{path.parent.name}/{path.name}", q))
    return found


class SampleDataTest(unittest.TestCase):
    def test_01_files_exist(self):
        """TC-DAT-01 | 正常系 | 問題集のファイルが1つ以上ある

        入力：questions/*/*.yaml
        期待：1ファイル以上、1問以上
        根拠：設計書 §3
        """
        self.assertGreater(len(all_question_files()), 0)
        self.assertGreater(len(all_questions()), 0)

    def test_02_required_keys(self):
        """TC-DAT-02 | データ品質 | すべての問題に、必須の項目がある

        入力：すべての問題
        期待：id・unit・level・type・question・code・answer・explanation がある
        根拠：設計書 §4
        """
        for where, q in all_questions():
            for key in REQUIRED_KEYS:
                self.assertIn(key, q, f"{where} の {q.get('id')} に {key} がありません")

    def test_03_unique_ids(self):
        """TC-DAT-03 | データ品質 | 問題のidが、すべての問題集をまたいで重複しない

        入力：すべての問題のid
        期待：重複なし
        根拠：設計書 §4（id は重複しない）
        """
        ids = [q["id"] for _, q in all_questions()]
        self.assertEqual(len(ids), len(set(ids)), "idが重複しています")

    def test_04_level_range(self):
        """TC-DAT-04 | データ品質 | 難易度（level）が1〜5の整数

        入力：すべての問題のlevel
        期待：1〜5の整数
        根拠：設計書 §4
        """
        for where, q in all_questions():
            self.assertIn(q["level"], [1, 2, 3, 4, 5], f"{where} の {q['id']}")

    def test_05_known_type(self):
        """TC-DAT-05 | データ品質 | 形式（type）が choice か blank

        入力：すべての問題のtype
        期待：choice または blank
        根拠：設計書 §4
        """
        for where, q in all_questions():
            self.assertIn(q["type"], ["choice", "blank"], f"{where} の {q['id']}")

    def test_06_choice_answer_in_choices(self):
        """TC-DAT-06 | データ品質 | 選択式の正解が、選択肢の中にあり、選択肢に重複がない

        入力：type が choice のすべての問題
        期待：choices があり、answer が choices に含まれ、choices に同じ文字が2つない
        根拠：設計書 §9（--check の確認項目）
        """
        for where, q in all_questions():
            if q["type"] != "choice":
                continue
            self.assertIn("choices", q, f"{where} の {q['id']} に choices がありません")
            self.assertIn(q["answer"], q["choices"], f"{where} の {q['id']}")
            self.assertEqual(len(q["choices"]), len(set(q["choices"])), f"{where} の {q['id']}")

    def test_07_answers_are_text(self):
        """TC-DAT-07 | データ品質 | 正解（answer）が文字列（または文字列のリスト）で書かれている

        入力：すべての問題のanswer
        期待：文字列、または文字列だけのリスト（引用符なしの数値・NULL・yes/no は不可）
        根拠：YAMLは引用符なしの 1 や NULL を、数値や None として読むため
        不具合：D-07
        """
        for where, q in all_questions():
            answers = q["answer"] if isinstance(q["answer"], list) else [q["answer"]]
            for a in answers:
                self.assertIsInstance(a, str, f"{where} の {q['id']}：answer を引用符で囲んでください")

    def test_08_blank_marker(self):
        """TC-DAT-08 | データ品質 | 問題のコードに、空欄の印（___）がある

        入力：すべての問題のcode
        期待：「___」を含む
        根拠：設計書 §4（空欄を埋める形式）
        """
        for where, q in all_questions():
            self.assertIn("___", q["code"], f"{where} の {q['id']}")

    def test_09_answer_not_given_away(self):
        """TC-DAT-09 | データ品質 | 正解が、問題文やコードにそのまま書かれていない

        入力：正解が3文字以上のすべての問題
        期待：問題文・コードに、正解の文字列が含まれない
        根拠：出題の品質ルール（答えを問題文に出さない。設計書 §9）
        """
        for where, q in all_questions():
            answers = q["answer"] if isinstance(q["answer"], list) else [q["answer"]]
            for a in answers:
                if len(str(a)) >= 3:
                    self.assertNotIn(str(a), q["question"] + q["code"], f"{where} の {q['id']}")

    def test_10_explanation_not_empty(self):
        """TC-DAT-10 | データ品質 | 解説が空でない

        入力：すべての問題のexplanation
        期待：空白以外の文字がある
        根拠：設計書 §4（解説は必須）
        """
        for where, q in all_questions():
            self.assertTrue(str(q["explanation"]).strip(), f"{where} の {q['id']}")


if __name__ == "__main__":
    unittest.main()
