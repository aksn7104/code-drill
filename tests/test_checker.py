"""問題集の検査（checker.py）の単体テスト

説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
検査の内容は、設計書 §9（drill.py --check の確認項目）と、tests/test_data.py の項目が土台。
"""

import tempfile
import unittest
from pathlib import Path

import checker

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_KEYS = ["id", "unit", "level", "type", "question", "code", "answer", "explanation"]


def blank(**changes):
    """検査を通る、空欄式の問題を1つ作る。changes で項目を書き換える。"""
    q = {
        "id": "t-1",
        "unit": "足し算",
        "level": 1,
        "type": "blank",
        "question": "空欄に入る記号を答えてください。",
        "code": "x = 1 ___ 2",
        "answer": "+",
        "explanation": "足し算は + です。",
    }
    q.update(changes)
    return q


def choice(**changes):
    """検査を通る、選択式の問題を1つ作る。"""
    q = blank(
        id="t-2",
        type="choice",
        choices=["+", "-", "*", "/"],
        answer="/",
        code="y = 6 ___ 3",
    )
    q.update(changes)
    return q


def messages(problems):
    return [p.message for p in problems]


def mentions(problems, *words):
    """すべての言葉を含むメッセージが、1つでもあるか。"""
    return any(all(w in m for w in words) for m in messages(problems))


class CheckQuestionsTest(unittest.TestCase):
    def test_01_valid_questions(self):
        """TC-CHK-01 | 正常系 | 正しい形の問題（空欄式・選択式）は、誤りなしになる

        入力：空欄式1問、選択式1問（hint なし）
        期待：誤りが0件
        根拠：設計書 §4
        """
        self.assertEqual(checker.check_questions([blank(), choice()]), [])

    def test_02_optional_hint(self):
        """TC-CHK-02 | 境界値 | hint は、あってもなくてもよい（あるときは文字）

        入力：hint が文字の問題、hint が数値の問題
        期待：文字ならOK、数値なら誤り（hint を含むメッセージ）
        根拠：設計書 §4（hint は任意）
        """
        self.assertEqual(checker.check_questions([blank(hint="ヒントです")]), [])
        self.assertTrue(mentions(checker.check_questions([blank(hint=5)]), "hint"))

    def test_03_missing_required_key(self):
        """TC-CHK-03 | 異常系 | 必須の項目が欠けた問題は、どの項目が欠けているかを知らせる

        入力：必須の8項目を、1つずつ欠かした問題
        期待：どれも誤りが出て、メッセージに欠けた項目名が入る
        根拠：設計書 §4。不具合 D-08（欠けた問題が、回答後にエラー画面になる）の再発防止
        不具合：D-08
        """
        for key in REQUIRED_KEYS:
            q = blank()
            del q[key]
            problems = checker.check_questions([q])
            self.assertTrue(mentions(problems, key, "ありません"), key)

    def test_04_level_range(self):
        """TC-CHK-04 | 境界値 | level は 1〜5 の整数だけが正しい

        入力：1・5（正しい）、0・6・"2"（文字）・2.5・True・None
        期待：1・5 は誤りなし。ほかは level を含む誤り
        根拠：設計書 §4。True は YAML では真偽値で、整数とは別
        """
        for ok in (1, 5):
            self.assertEqual(checker.check_questions([blank(level=ok)]), [], ok)
        for bad in (0, 6, "2", 2.5, True, None):
            self.assertTrue(mentions(checker.check_questions([blank(level=bad)]), "level"), repr(bad))

    def test_05_unknown_type(self):
        """TC-CHK-05 | 異常系 | type が choice か blank 以外だと誤りになる

        入力：type: multi、type: Choice（大文字）
        期待：どちらも type を含む誤り
        根拠：設計書 §4
        """
        for bad in ("multi", "Choice", None):
            self.assertTrue(mentions(checker.check_questions([blank(type=bad)]), "type"), repr(bad))

    def test_06_bad_id(self):
        """TC-CHK-06 | 異常系 | id が空・数値・None だと誤りになる

        入力：id: ""、id: 123（引用符なし）、id: null
        期待：どれも id を含む誤り
        根拠：設計書 §4（id は問題を見分ける文字）
        """
        for bad in ("", "  ", 123, None):
            self.assertTrue(mentions(checker.check_questions([blank(id=bad)]), "id"), repr(bad))

    def test_07_duplicate_ids(self):
        """TC-CHK-07 | 異常系 | 同じ問題集に同じ id があると誤りになる

        入力：id が同じ2問
        期待：「重複」を含む誤りが出る
        根拠：設計書 §4（id は重複しない）。記録は id で問題を見分けるため
        """
        problems = checker.check_questions([blank(id="same"), blank(id="same")])
        self.assertTrue(mentions(problems, "重複", "same"))

    def test_08_answer_null(self):
        """TC-CHK-08 | 異常系 | 引用符なしの NULL（None として読まれる）を answer に書くと、直し方を知らせる

        入力：answer が None（YAML で「answer: NULL」と書いた場合）
        期待：answer と「引用符」を含む誤り
        根拠：YAML は引用符のない NULL を None として読むため、「NULL」と答えても不正解になる
        不具合：D-07
        """
        problems = checker.check_questions([blank(answer=None)])
        self.assertTrue(mentions(problems, "answer", "引用符"))

    def test_09_answer_not_text(self):
        """TC-CHK-09 | 異常系 | 引用符なしの yes/no（真偽値）・数字は、answer としては誤りになる

        入力：answer が True、False、1、1.5
        期待：どれも answer と「引用符」を含む誤り
        根拠：YAML は引用符のない yes を True、1 を数値として読む
        不具合：D-07
        """
        for bad in (True, False, 1, 1.5):
            self.assertTrue(
                mentions(checker.check_questions([blank(answer=bad)]), "answer", "引用符"), repr(bad)
            )

    def test_10_answer_list(self):
        """TC-CHK-10 | 境界値 | answer が文字のリストならOK。リストの中に文字以外があると誤り

        入力：["f", "F"]（正しい）、["f", None]、["f", 3]
        期待：最初は誤りなし。あとの2つは answer と「引用符」を含む誤り
        根拠：設計書 §4（複数の書き方を認めるときはリスト）
        """
        self.assertEqual(checker.check_questions([blank(answer=["f", "F"])]), [])
        for bad in (["f", None], ["f", 3]):
            self.assertTrue(
                mentions(checker.check_questions([blank(answer=bad)]), "answer", "引用符"), repr(bad)
            )

    def test_11_answer_empty(self):
        """TC-CHK-11 | 境界値 | answer が空の文字・空のリストだと誤りになる

        入力：answer: ""、answer: "  "、answer: []
        期待：どれも answer を含む誤り
        根拠：何を答えても不正解になる問題を防ぐ
        """
        for bad in ("", "  ", []):
            self.assertTrue(mentions(checker.check_questions([blank(answer=bad)]), "answer"), repr(bad))

    def test_12_choice_needs_choices(self):
        """TC-CHK-12 | 異常系 | 選択式で choices がない・リストでない・2つ未満・文字以外を含むと誤りになる

        入力：choices なし、choices が文字、choices が1つ、choices に数値が混じる
        期待：どれも choices を含む誤り
        根拠：設計書 §4、§9（--check の確認項目）
        """
        q = choice()
        del q["choices"]
        self.assertTrue(mentions(checker.check_questions([q]), "choices"))
        for bad in ("+,-", ["+"], ["+", 3, "-"]):
            self.assertTrue(
                mentions(checker.check_questions([choice(choices=bad, answer="+")]), "choices"), repr(bad)
            )

    def test_13_answer_in_choices(self):
        """TC-CHK-13 | 異常系 | 選択式の answer が choices の中にないと誤りになる

        入力：choices が ["+","-"] で、answer が "/"
        期待：answer と choices を含む誤り
        根拠：設計書 §9（answer が choices の中にあるか）
        """
        problems = checker.check_questions([choice(choices=["+", "-"], answer="/")])
        self.assertTrue(mentions(problems, "answer", "choices"))

    def test_14_duplicate_choices(self):
        """TC-CHK-14 | 異常系 | choices に同じ文字が2つあると誤りになる

        入力：choices: ["+", "+", "-"]
        期待：choices と「重複」を含む誤り
        根拠：番号で答えたときに、どちらの番号が正解か決まらないため
        """
        problems = checker.check_questions([choice(choices=["+", "+", "-"], answer="-")])
        self.assertTrue(mentions(problems, "choices", "重複"))

    def test_15_blank_ignores_choices(self):
        """TC-CHK-15 | 境界値 | 空欄式の問題に choices があっても、誤りにしない

        入力：type: blank で、choices も書いてある問題
        期待：誤りなし
        根拠：choices は選択式のための項目で、空欄式では使わないだけ
        """
        self.assertEqual(checker.check_questions([blank(choices=["+", "-"])]), [])

    def test_16_blank_marker(self):
        """TC-CHK-16 | データ品質 | code に空欄の印（___）がないと誤りになる

        入力：code が「x = 1 + 2」
        期待：code と「___」を含む誤り
        根拠：設計書 §4（空欄を埋める形式）
        """
        problems = checker.check_questions([blank(code="x = 1 + 2")])
        self.assertTrue(mentions(problems, "code", "___"))

    def test_17_answer_given_away(self):
        """TC-CHK-17 | データ品質 | 3文字以上の答えが、問題文やコードにそのまま書かれていると誤りになる

        入力：answer が "WHERE" で、問題文に「WHERE」と書いた問題。answer が "+"（1文字）で問題文に「+」がある問題
        期待：前者は「答え」を含む誤り。後者は誤りなし
        根拠：出題の品質ルール（答えを問題文に出さない。設計書 §9）。1〜2文字は、偶然の一致が多いので対象外
        """
        problems = checker.check_questions([blank(answer="WHERE", question="WHERE を入れます。")])
        self.assertTrue(mentions(problems, "答え"))
        self.assertEqual(checker.check_questions([blank(answer="+", question="+ を入れます。")]), [])

    def test_18_empty_text_fields(self):
        """TC-CHK-18 | 境界値 | unit・question・code・explanation が空白だけだと誤りになる

        入力：4つの項目を、それぞれ空白だけにした問題
        期待：どれも、その項目名を含む誤り
        根拠：設計書 §4（解説は必須）
        """
        for key in ("unit", "question", "code", "explanation"):
            problems = checker.check_questions([blank(**{key: "   "})])
            self.assertTrue(mentions(problems, key), key)

    def test_19_text_fields_must_be_text(self):
        """TC-CHK-19 | 異常系 | unit・question・code・explanation が文字でない（数値・リスト）と誤りになる

        入力：4つの項目を、それぞれ数値にした問題
        期待：どれも、その項目名を含む誤り
        根拠：画面に出す前に、書き方の誤りに気づけるように
        """
        for key in ("unit", "question", "code", "explanation"):
            problems = checker.check_questions([blank(**{key: 123})])
            self.assertTrue(mentions(problems, key), key)

    def test_20_reports_all_problems(self):
        """TC-CHK-20 | 正常系 | 1つの問題に誤りが複数あれば、すべて知らせる（最初の1つで止まらない）

        入力：answer が欠け、level が 9 で、type が不正な問題
        期待：3件以上の誤り
        根拠：直す人が、何度も実行し直さなくて済むように
        """
        q = blank(level=9, type="multi")
        del q["answer"]
        self.assertGreaterEqual(len(checker.check_questions([q])), 3)

    def test_21_problem_has_question_id(self):
        """TC-CHK-21 | 正常系 | 誤りには、どの問題の誤りかが分かる id が付く

        入力：id「t-9」の問題の level が不正
        期待：誤りの qid が「t-9」。文字にしたとき、id が含まれる
        根拠：問題集には何問もあり、探しやすくするため
        """
        problems = checker.check_questions([blank(id="t-9", level=0)])
        self.assertEqual(problems[0].qid, "t-9")
        self.assertIn("t-9", str(problems[0]))

    def test_22_question_without_id(self):
        """TC-CHK-22 | 境界値 | id がない問題は、何番目の問題かで知らせる

        入力：2問目の id が欠けた問題集
        期待：誤りの qid に「2番目」が入る
        根拠：id がなくても、場所が分かるように
        """
        second = blank()
        del second["id"]
        problems = checker.check_questions([blank(id="ok"), second])
        self.assertTrue(any("2番目" in (p.qid or "") for p in problems))


class FileCheckTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def make(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    GOOD = (
        "- id: a-1\n  unit: 足し算\n  level: 1\n  type: blank\n"
        "  question: 記号を答えてください。\n  code: x = 1 ___ 2\n"
        '  answer: "+"\n  explanation: 足し算です。\n'
    )

    def test_23_bundled_files_are_clean(self):
        """TC-CHK-23 | データ品質 | 同梱の問題集（questions/ の下のすべて）に誤りがない

        入力：questions/ フォルダ全体
        期待：誤りが0件。検査した問題が1問以上ある
        根拠：公開する見本に、誤りがあってはならない
        """
        result = checker.check_paths([ROOT / "questions"])
        self.assertEqual([str(p) for p in result.problems], [])
        self.assertGreaterEqual(result.question_count, 8)

    def test_24_yaml_syntax_error(self):
        """TC-CHK-24 | 異常系 | YAML の書き方が誤っているファイルは、誤りとして知らせる（例外にしない）

        入力：引用符が閉じていないYAML
        期待：1件の誤り（ファイル名と「YAML」を含む）。例外は出ない
        根拠：AIが作った問題集の書き間違いを想定（設計書 §9）
        """
        path = self.make("python/bad.yaml", '- id: "a-1\n   unit: [x\n')
        result = checker.check_paths([path])
        self.assertEqual(len(result.problems), 1)
        self.assertIn("YAML", result.problems[0].message)
        self.assertIn("bad.yaml", str(result.problems[0]))

    def test_25_missing_path(self):
        """TC-CHK-25 | 異常系 | 存在しないパスは、誤りとして知らせる

        入力：存在しないファイル
        期待：1件の誤り（「見つかりません」を含む）
        根拠：パスの打ち間違い
        """
        result = checker.check_paths([self.root / "none.yaml"])
        self.assertEqual(len(result.problems), 1)
        self.assertIn("見つかりません", result.problems[0].message)

    def test_26_empty_file(self):
        """TC-CHK-26 | 境界値 | 問題が0問のファイルは、誤りとして知らせる

        入力：0バイトのYAML
        期待：1件の誤り（「問題がありません」を含む）
        根拠：出題できない問題集は、使う前に気づけるように（TC-CLI-08 と同じ状況）
        """
        path = self.make("python/empty.yaml", "")
        result = checker.check_paths([path])
        self.assertEqual(len(result.problems), 1)
        self.assertIn("問題がありません", result.problems[0].message)

    def test_27_not_a_list(self):
        """TC-CHK-27 | 異常系 | 問題のリストの形でないファイルは、誤りとして知らせる

        入力：先頭が辞書のYAML
        期待：1件の誤り（「リスト」を含む）
        根拠：設計書 §4（1ファイルは問題のリスト）
        """
        path = self.make("python/dict.yaml", "id: a-1\nunit: x\n")
        result = checker.check_paths([path])
        self.assertEqual(len(result.problems), 1)
        self.assertIn("リスト", result.problems[0].message)

    def test_28_folder_is_searched(self):
        """TC-CHK-28 | 正常系 | フォルダを指定すると、中の問題集をすべて検査する（_ で始まる設定ファイルは問題集に数えない）

        入力：python/ に問題集2つと _language.yaml、sql/ に問題集1つを置いたフォルダ
        期待：検査した問題数が合計3問。誤りなし
        根拠：設計書 §4（言語はフォルダ、設定ファイルは _ で始まる）
        """
        self.make("python/a.yaml", self.GOOD)
        self.make("python/b.yaml", self.GOOD.replace("a-1", "b-1"))
        self.make("python/_language.yaml", "name: Python\n")
        self.make("sql/c.yaml", self.GOOD.replace("a-1", "c-1"))
        result = checker.check_paths([self.root])
        self.assertEqual(result.problems, [])
        self.assertEqual(result.question_count, 3)

    def test_29_duplicate_id_across_files(self):
        """TC-CHK-29 | 異常系 | 別のファイルに同じ id があると誤りになる

        入力：2つのファイルに、同じ id「a-1」の問題
        期待：「重複」と id を含む誤りが1件以上
        根拠：記録は id で問題を見分けるため、言語やファイルをまたいで重複してはならない（TC-DAT-03 と同じ）
        """
        self.make("python/a.yaml", self.GOOD)
        self.make("sql/b.yaml", self.GOOD)
        result = checker.check_paths([self.root])
        self.assertTrue(mentions(result.problems, "重複", "a-1"))

    def test_30_folder_without_questions(self):
        """TC-CHK-30 | 境界値 | 問題集のないフォルダを指定したら、誤りとして知らせる

        入力：空のフォルダ
        期待：1件の誤り（「問題集」を含む）
        根拠：フォルダの指定間違い
        """
        result = checker.check_paths([self.root])
        self.assertEqual(len(result.problems), 1)
        self.assertIn("問題集", result.problems[0].message)

    def test_31_language_file_ok(self):
        """TC-CHK-31 | 正常系 | 正しい _language.yaml は、誤りなしになる

        入力：name・case_sensitive・ignore_spaces が正しく書かれた設定
        期待：誤りなし
        根拠：設計書 §4
        """
        self.make("python/a.yaml", self.GOOD)
        self.make("python/_language.yaml", "name: Python\ncase_sensitive: true\nignore_spaces: true\n")
        self.assertEqual(checker.check_paths([self.root]).problems, [])

    def test_32_language_file_bad(self):
        """TC-CHK-32 | 異常系 | _language.yaml の項目の型が違うと誤りになる

        入力：case_sensitive: "はい"（文字）、name: 3（数値）、設定全体がリスト形式
        期待：どれも誤りが出る（項目名またはファイル名を含む）
        根拠：言語の設定の書き間違いに気づけるように（読み込み時のエラーは TC-LDR にある）
        """
        self.make("python/a.yaml", self.GOOD)
        cases = {
            'case_sensitive: "はい"\n': "case_sensitive",
            "name: 3\n": "name",
            "- a\n- b\n": "_language.yaml",
        }
        for text, word in cases.items():
            self.make("python/_language.yaml", text)
            result = checker.check_paths([self.root])
            self.assertTrue(
                any(word in str(p) for p in result.problems), f"{text!r}: {[str(p) for p in result.problems]}"
            )

    def test_33_single_file_checks_its_language_file(self):
        """TC-CHK-33 | 境界値 | ファイルを1つ指定したときも、同じフォルダの _language.yaml を検査する

        入力：問題集のファイルだけを指定。同じフォルダの _language.yaml は誤り
        期待：誤りが出る
        根拠：drill.py は問題集を読むとき、同じフォルダの _language.yaml も読むため
        """
        path = self.make("python/a.yaml", self.GOOD)
        self.make("python/_language.yaml", "ignore_spaces: 5\n")
        result = checker.check_paths([path])
        self.assertTrue(mentions(result.problems, "ignore_spaces"))


if __name__ == "__main__":
    unittest.main()
