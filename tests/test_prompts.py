"""AI に問題集を作らせる指示文（prompts/）の試験（段階9-1）

Claude 版で毎日使っている「出題の指示書」の決まりが、汎用版の指示文に入っているかを確かめる。
説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checker  # noqa: E402

PROMPTS = ROOT / "prompts"


def paste_part(name):
    text = (PROMPTS / name).read_text(encoding="utf-8")
    match = re.search(r"````text\n(.*?)\n````", text, flags=re.S)
    return text, (match.group(1) if match else "")


class QuestionPromptTest(unittest.TestCase):
    def setUp(self):
        self.text, self.paste = paste_part("generate_questions.md")

    def test_01_prompt_has_the_rules_of_the_claude_version(self):
        """TC-PRM-01 | データ品質 | 指示文に、Claude 版の出題の決まり（難易度の下限・計算問題にしない・5行以内・紛らわしい選択肢・見出しに文法名を書かない・送る前の見直し）が入っている

        入力：prompts/generate_questions.md の、貼り付ける部分
        期待：決まりごとの言葉がそれぞれ入っている
        根拠：Claude 版の「出題の指示書」§4（13〜17）。AI に作らせても、同じ質の問題になるように
        """
        for word in ("下限", "計算問題", "5行", "紛らわしい", "文法の名前", "見直し"):
            self.assertIn(word, self.paste, word)

    def test_02_prompt_uses_what_the_learner_already_knows(self):
        """TC-PRM-02 | 正常系 | 指示文に「既習の内容」の差し込み場所があり、基礎的すぎる問題にしない・すでに出した問題と重ねない決まりがある

        入力：貼り付ける部分
        期待：{既習の内容} がある。「すでに学んだ」「同じ内容・同じ型」の言葉がある
        根拠：Claude 版の出題の決まり18（これまでの学習を踏まえて作る）
        """
        self.assertIn("{既習の内容}", self.paste)
        self.assertIn("すでに学んだ", self.paste)
        self.assertIn("同じ内容・同じ型", self.paste)

    def test_03_prompt_explains_each_placeholder(self):
        """TC-PRM-03 | データ品質 | 貼り付ける部分の差し込み場所は、すべて説明の表に書かれている

        入力：貼り付ける部分の { } と、説明の表
        期待：貼り付ける部分にある差し込み場所が、どれも表に書かれている
        根拠：書き換え忘れ・意味の分からない差し込み場所を防ぐ
        """
        placeholders = set(re.findall(r"\{[^{}\n]+\}", self.paste))
        placeholders -= {"{ }"}
        self.assertGreaterEqual(len(placeholders), 5)
        table = self.text.split("````text")[0]
        for name in placeholders:
            self.assertIn(name, table, name)

    def test_04_prompt_explains_how_to_add_questions(self):
        """TC-PRM-04 | 正常系 | 作った問題を問題集に入れる手順（保存場所・検査・言語の追加・動かし方）が書かれている

        入力：prompts/generate_questions.md の本文
        期待：questions/、--check、config.yaml、languages、run_tests の言葉がある
        根拠：本人の希望（問題を作る質問のしかたと、それを問題集に入れる方法の説明）
        """
        for word in ("questions/", "--check", "config.yaml", "languages", "run_tests", "ファイル名"):
            self.assertIn(word, self.text, word)

    def test_05_sample_follows_its_own_rules(self):
        """TC-PRM-05 | データ品質 | 指示文の中の YAML の見本が、指示文の決まり（コード5行以内・難易度の下限）を守っている

        入力：指示文の YAML の見本
        期待：どの問題も、コードが5行以内。見本の中で、2問目以降の level が 2 以上
        根拠：自分で決めた決まりを、見本が破っていると、AI が見本のほうをまねるため
        """
        blocks = re.findall(r"```yaml\n(.*?)```", self.text, flags=re.S)
        questions = yaml.safe_load(blocks[0])
        for q in questions:
            self.assertLessEqual(len(q["code"].strip().splitlines()), 5, q["id"])
        for q in questions[1:]:
            self.assertGreaterEqual(q["level"], 2, q["id"])


class LanguagePromptTest(unittest.TestCase):
    def setUp(self):
        self.path = PROMPTS / "generate_language.md"

    def test_06_language_prompt_exists_and_asks_for_the_three_keys(self):
        """TC-PRM-06 | 正常系 | 言語の設定（_language.yaml）を AI に作らせる指示文があり、3つの項目を頼んでいる

        入力：prompts/generate_language.md
        期待：ファイルがある。貼り付ける部分に {言語}、name、case_sensitive、ignore_spaces がある
        根拠：Claude 版にない、汎用版だけの機能（言語を足せる）。設計書 §9（_language.yaml も AI に作らせられる）
        """
        self.assertTrue(self.path.exists())
        text, paste = paste_part("generate_language.md")
        for word in ("{言語}", "name", "case_sensitive", "ignore_spaces", "true", "false"):
            self.assertIn(word, paste, word)

    def test_07_language_sample_passes_the_checker(self):
        """TC-PRM-07 | 結合 | 言語の設定の見本が、形式検査（--check と同じ）に通る

        入力：指示文の ```yaml の見本を _language.yaml として置いて検査
        期待：誤りが 0 件
        根拠：見本どおりに作らせた設定が、検査で弾かれる矛盾を防ぐ
        """
        text = self.path.read_text(encoding="utf-8")
        blocks = re.findall(r"```yaml\n(.*?)```", text, flags=re.S)
        self.assertTrue(blocks)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "sample"
            folder.mkdir()
            (folder / "_language.yaml").write_text(blocks[0], encoding="utf-8")
            (folder / "u01.yaml").write_text(
                "- id: a-1\n  unit: u\n  level: 1\n  type: blank\n  question: q\n  code: 'x = ___'\n"
                "  answer: '1'\n  explanation: e\n",
                encoding="utf-8",
            )
            result = checker.check_paths([folder])
        self.assertEqual([str(p) for p in result.problems], [])
