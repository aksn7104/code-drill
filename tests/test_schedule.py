"""学習の日程と言語の切り替え（schedule.py）の単体テスト

説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
日付は外から渡す作りなので、「水曜」「学習日の3日目」を毎回同じ条件で試せる。
"""

import tempfile
import unittest
from datetime import date
from pathlib import Path

import timetable as sch

DEFAULT_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat"]
MONDAY = date(2026, 10, 12)  # 2026-10-12 は月曜日


def at(offset):
    """月曜日から offset 日あとの日付。"""
    return date.fromordinal(MONDAY.toordinal() + offset)


def log_rows(*dates):
    """試験用の記録（日付だけを持つ辞書のリスト）。"""
    return [{"date": d} for d in dates]


class IsStudyDayTest(unittest.TestCase):
    def test_01_weekdays_and_saturday(self):
        """TC-SCH-01 | 正常系 | 月曜〜土曜は学習する日になる

        入力：2026-10-12（月）〜 10-17（土）、days は既定（月〜土）
        期待：6日とも True
        根拠：設計書 §5-2（日曜は休み）
        """
        for offset in range(6):
            self.assertTrue(sch.is_study_day(at(offset), DEFAULT_DAYS), at(offset))

    def test_02_sunday_is_rest(self):
        """TC-SCH-02 | 正常系 | 日曜は休みの日になる

        入力：2026-10-18（日）、days は既定（月〜土）
        期待：False
        根拠：設計書 §5-2
        """
        self.assertFalse(sch.is_study_day(at(6), DEFAULT_DAYS))

    def test_03_custom_days(self):
        """TC-SCH-03 | 正常系 | 設定した曜日だけが学習する日になる

        入力：days=[sun]（日曜だけ）
        期待：日曜は True、月曜は False
        根拠：設計書 §7（days は設定で変えられる）
        """
        self.assertTrue(sch.is_study_day(at(6), ["sun"]))
        self.assertFalse(sch.is_study_day(at(0), ["sun"]))

    def test_04_empty_days(self):
        """TC-SCH-04 | 境界値 | 曜日のリストが空なら、どの日も学習しない

        入力：days=[]
        期待：7日とも False（エラーにはならない）
        根拠：すべて休みにしたい場合
        """
        for offset in range(7):
            self.assertFalse(sch.is_study_day(at(offset), []))


class StudyDayNumberTest(unittest.TestCase):
    def test_05_empty_log(self):
        """TC-SCH-05 | 境界値 | 記録がなければ、今日は学習日の1日目

        入力：記録が空、今日は 10-12
        期待：1
        根拠：初回の実行
        """
        self.assertEqual(sch.study_day_number([], at(0)), 1)

    def test_06_counts_distinct_dates(self):
        """TC-SCH-06 | 正常系 | 記録のある日の数に1を足す（同じ日の複数行は1日と数える）

        入力：10-12 に2行、10-13 に1行の記録、今日は 10-14
        期待：3（過去2日 ＋ 今日）
        根拠：言語の切り替えは「学習した日の数」で決める（設計書 §5-4）
        """
        rows = log_rows("2026-10-12", "2026-10-12", "2026-10-13")
        self.assertEqual(sch.study_day_number(rows, at(2)), 3)

    def test_07_today_already_recorded(self):
        """TC-SCH-07 | 境界値 | 今日の分が記録済みでも、数が変わらない（同じ日に2回実行しても同じ言語）

        入力：10-12 の記録と、今日（10-13）の記録、今日は 10-13
        期待：2（今日を二重に数えない）
        根拠：同じ日にもう一度実行したとき、別の言語にならないように
        """
        rows = log_rows("2026-10-12", "2026-10-13")
        self.assertEqual(sch.study_day_number(rows, at(1)), 2)

    def test_08_future_dates_ignored(self):
        """TC-SCH-08 | 異常系 | 今日より先の日付の記録は、数えない

        入力：10-12 と、未来の 10-20 の記録、今日は 10-13
        期待：2
        根拠：PCの日付を変えた場合や、記録の書き間違いで、数がずれないように
        """
        rows = log_rows("2026-10-12", "2026-10-20")
        self.assertEqual(sch.study_day_number(rows, at(1)), 2)


class PickLanguageTest(unittest.TestCase):
    def test_09_single_language(self):
        """TC-SCH-09 | 境界値 | 言語が1つだけなら、毎日その言語

        入力：languages=[python]、学習日の1〜5日目
        期待：いつも python
        根拠：設計書 §7（言語が1つなら、毎日その言語）
        """
        for n in range(1, 6):
            self.assertEqual(sch.pick_language(n, ["python"], {"python": 2}), "python")

    def test_10_rotation_every_two_days(self):
        """TC-SCH-10 | 正常系 | sql: 2 なら、学習日の2日に1度が SQL、ほかは先頭の言語

        入力：languages=[python, sql]、rotation={sql: 2}、1〜6日目
        期待：python, sql, python, sql, python, sql
        根拠：設計書 §7（Claude 版の「2日に1度は SQL」）
        """
        got = [sch.pick_language(n, ["python", "sql"], {"sql": 2}) for n in range(1, 7)]
        self.assertEqual(got, ["python", "sql", "python", "sql", "python", "sql"])

    def test_11_rotation_every_three_days(self):
        """TC-SCH-11 | 境界値 | sql: 3 なら、3日に1度が SQL

        入力：rotation={sql: 3}、1〜6日目
        期待：python, python, sql, python, python, sql
        根拠：割合を変えられること
        """
        got = [sch.pick_language(n, ["python", "sql"], {"sql": 3}) for n in range(1, 7)]
        self.assertEqual(got, ["python", "python", "sql", "python", "python", "sql"])

    def test_12_rotation_every_day(self):
        """TC-SCH-12 | 境界値 | sql: 1 なら、毎日 SQL

        入力：rotation={sql: 1}、1〜3日目
        期待：いつも sql
        根拠：k=1 は「毎回」。0 や負の値とは別に扱う
        """
        for n in range(1, 4):
            self.assertEqual(sch.pick_language(n, ["python", "sql"], {"sql": 1}), "sql")

    def test_13_no_rotation_round_robin(self):
        """TC-SCH-13 | 正常系 | 切り替えの設定がなければ、リストの順に1日ずつ回す

        入力：languages=[python, sql, js]、rotation=None、1〜6日目
        期待：python, sql, js, python, sql, js
        根拠：設定なしでも、言語フォルダを足すだけで使える（設計書 §4）
        """
        got = [sch.pick_language(n, ["python", "sql", "js"], None) for n in range(1, 7)]
        self.assertEqual(got, ["python", "sql", "js", "python", "sql", "js"])

    def test_14_two_rotations_first_wins(self):
        """TC-SCH-14 | 境界値 | 2つの言語の日が重なったら、リストで先に書いた言語を優先する

        入力：languages=[python, sql, js]、rotation={sql: 2, js: 4}、4日目（どちらも当たる日）
        期待：sql（rotation に先に書かれた言語）
        根拠：重なった日の扱いを決めておく
        """
        self.assertEqual(
            sch.pick_language(4, ["python", "sql", "js"], {"sql": 2, "js": 4}), "sql"
        )

    def test_15_unknown_language_in_rotation(self):
        """TC-SCH-15 | 異常系 | rotation に、languages にない言語があるとエラーにする

        入力：languages=[python]、rotation={sql: 2}
        期待：ScheduleError
        根拠：書き間違い（言語名の打ち間違い）に気づけるように
        """
        with self.assertRaises(sch.ScheduleError):
            sch.pick_language(2, ["python"], {"sql": 2})

    def test_16_no_languages(self):
        """TC-SCH-16 | 異常系 | 使える言語が1つもないとエラーにする

        入力：languages=[]
        期待：ScheduleError
        根拠：questions/ の下に言語フォルダがない場合
        """
        with self.assertRaises(sch.ScheduleError):
            sch.pick_language(1, [], None)


class FolderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def make(self, relative, text="- id: x\n"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_17_find_languages(self):
        """TC-SCH-17 | 正常系 | questions/ の下の、問題集を持つフォルダが言語として見つかる（名前順）

        入力：sql/・python/（どちらも問題集あり）、empty/（問題集なし）、メモ.txt（ファイル）
        期待：["python", "sql"]（empty と ファイルは言語に含めない）
        根拠：設計書 §4（フォルダを足せば言語が増える）
        """
        self.make("sql/a.yaml")
        self.make("python/b.yaml")
        (self.root / "empty").mkdir()
        self.make("メモ.txt", "x")
        self.assertEqual(sch.find_languages(self.root), ["python", "sql"])

    def test_18_underscore_files_are_not_questions(self):
        """TC-SCH-18 | 境界値 | _language.yaml だけのフォルダは、言語として数えない

        入力：python/ に _language.yaml だけがある
        期待：言語なし（空のリスト）
        根拠：_language.yaml は設定で、問題集ではないため
        """
        self.make("python/_language.yaml", "name: Python\n")
        self.assertEqual(sch.find_languages(self.root), [])

    def test_19_missing_questions_dir(self):
        """TC-SCH-19 | 異常系 | questions/ フォルダがないときは、空のリストを返す

        入力：存在しないフォルダ
        期待：空のリスト
        根拠：呼び出し側が「言語がありません」と伝えられるように
        """
        self.assertEqual(sch.find_languages(self.root / "none"), [])

    def test_20_first_question_file(self):
        """TC-SCH-20 | 正常系 | 言語フォルダの問題集のうち、ファイル名の最初のものを使う

        入力：python/ に batting_02.yaml・batting_01.yaml・_language.yaml
        期待：batting_01.yaml
        根拠：設計書 §4（単元の並び順はファイル名の番号。進捗が入る段階6-2までの仮の決め）
        """
        self.make("python/batting_02.yaml")
        self.make("python/batting_01.yaml")
        self.make("python/_language.yaml", "name: Python\n")
        self.assertEqual(
            sch.first_question_file(self.root, "python").name, "batting_01.yaml"
        )

    def test_21_language_without_files(self):
        """TC-SCH-21 | 異常系 | 問題集がない言語を指定したらエラーにする

        入力：存在しない言語フォルダ
        期待：ScheduleError
        根拠：設定に書いた言語のフォルダを作り忘れた場合
        """
        with self.assertRaises(sch.ScheduleError):
            sch.first_question_file(self.root, "ruby")

    def test_22_unit_files_sorted(self):
        """TC-SCH-22 | 正常系 | 言語フォルダの問題集（単元）を、ファイル名の順で返す

        入力：u02.yaml、u01.yaml、_language.yaml を置いたフォルダ
        期待：u01.yaml、u02.yaml の順（_ で始まる設定ファイルは含まない）
        根拠：決定事項 判断3（単元を順に進める）
        """
        lang = self.root / "python"
        lang.mkdir(parents=True, exist_ok=True)
        for name in ("u02.yaml", "u01.yaml", "_language.yaml"):
            (lang / name).write_text("[]", encoding="utf-8")
        self.assertEqual([p.name for p in sch.unit_files(self.root, "python")], ["u01.yaml", "u02.yaml"])

    def test_23_unit_files_missing(self):
        """TC-SCH-23 | 異常系 | 問題集がない言語は ScheduleError にする

        入力：存在しない言語フォルダ
        期待：ScheduleError
        根拠：設定に書いた言語のフォルダを作り忘れた場合
        """
        with self.assertRaises(sch.ScheduleError):
            sch.unit_files(self.root, "ruby")


if __name__ == "__main__":
    unittest.main()
