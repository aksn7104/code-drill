"""もう1問・難易度を下げる・単元の終わりのGit案内・長めの読解の日（段階9-2）の試験

Claude 版で毎日使っている決まり（出題の指示書 §4-9・§3・§5-7）を、汎用版に入れたかを確かめる。
説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checker  # noqa: E402
import recorder  # noqa: E402
import session  # noqa: E402
from config import ConfigError, load_config  # noqa: E402
from progress import lang_state, load_progress, lower_level, raise_level  # noqa: E402
from tests.test_cli import CliTestCase, WEDNESDAY, unit_yaml  # noqa: E402

SATURDAY = "2026-10-17"
SAT = date(2026, 10, 17)
WED = date(2026, 10, 14)


def long_yaml(*qids):
    """長めの読解の問題（long: true）。答えはどれも「a」。"""
    return "".join(
        f"""- id: {qid}
  unit: 長めの読解
  level: 2
  type: blank
  question: 長い表を読む問題{qid}
  code: x = ___
  answer: a
  explanation: 解説{qid}
  long: true
"""
        for qid in qids
    )


class NoteTest(unittest.TestCase):
    def test_01_row_has_a_note_when_given(self):
        """TC-EXT-01 | 正常系 | 記録の1行に、note（メモ）を付けられる。付けなければ空

        入力：make_row を note なし／note="追加" で呼ぶ
        期待：note は、空の文字／「追加」
        根拠：Claude 版の決まり（追加の1問は「（追加）」を付けて記録する）。既存の記録の形（8列）は変えない
        """
        q = {"id": "a", "unit": "u", "level": 1}
        self.assertEqual(recorder.make_row(q, True, "python", WED)["note"], "")
        self.assertEqual(recorder.make_row(q, True, "python", WED, note="追加")["note"], "追加")


class ExtraPlanTest(CliTestCase):
    def setUp(self):
        super().setUp()
        self.qdir = self.folder / "qdir"
        self.write_questions(unit_yaml("p-1", "p-2", "p-3", "p-4"), "u01.yaml", self.qdir / "python")
        self.write_questions(unit_yaml("p-5", "p-6"), "u02.yaml", self.qdir / "python")
        (self.folder / "config.yaml").write_text("languages: [python]\nquestions_per_day: 2\n", encoding="utf-8")

    def day(self, day, stdin, extra=()):
        return self.run_drill(["--date", day, *extra], stdin, qdir=self.qdir)

    def progress(self):
        return json.loads(self.progress_path.read_text(encoding="utf-8"))

    def test_02_extra_plan_gives_one_question_without_pending(self):
        """TC-EXT-02 | 正常系 | 追加の1問の計画は、同じ言語の問題を1問だけ選び、未回答には入れない

        入力：1日目の2問を答えたあとに plan_extra を呼ぶ
        期待：kind は extra、問題は1問（同じ単元の、まだ出していない問題）。progress の pending は空のまま
        根拠：Claude 版の決まり9・10（追加は1問ずつ。追加分は未回答の再出題の対象に含めない）
        """
        self.day(WEDNESDAY, "a\na\n")
        config = load_config(self.folder / "config.yaml")
        plan = session.plan_extra(config, self.qdir, self.log_path, self.progress_path, WED, "python")
        self.assertEqual(plan.kind, "extra")
        self.assertEqual(len(plan.entries), 1)
        asked = {r["qid"] for r in recorder.read_log(self.log_path)}
        self.assertNotIn(plan.entries[0]["q"]["id"], asked)
        self.assertEqual(load_progress(self.progress_path)["pending"], [])

    def test_03_extra_goes_on_to_next_unit_when_unit_is_finished(self):
        """TC-EXT-03 | 境界値 | 単元を出し終えていたら、追加の1問は次の単元の続きから出る（単元の順番を崩さない）

        入力：u01（4問）を2日分で出し終えたあとに plan_extra
        期待：選ばれた問題は u02（p-5, p-6）のもの
        根拠：Claude 版の決まり9（単元の順番は崩さず、続きから進める）
        """
        self.day(WEDNESDAY, "a\na\n")
        self.day("2026-10-15", "a\na\n")
        config = load_config(self.folder / "config.yaml")
        plan = session.plan_extra(config, self.qdir, self.log_path, self.progress_path, date(2026, 10, 15), "python")
        self.assertIn(plan.entries[0]["q"]["id"], {"p-5", "p-6"})

    def test_04_extra_for_unknown_language_is_an_error(self):
        """TC-EXT-04 | 異常系 | 問題集のない言語で追加を頼むと、SessionError になる

        入力：plan_extra に、存在しない言語「nothing」
        期待：SessionError
        根拠：落ちずに、分かる文章で止める（設計書 §5 エラーの扱い）
        """
        config = load_config(self.folder / "config.yaml")
        with self.assertRaises(session.SessionError):
            session.plan_extra(config, self.qdir, self.log_path, self.progress_path, WED, "nothing")

    def test_05_cli_asks_for_one_more_and_records_it(self):
        """TC-EXT-05 | 正常系 | 2問のあと「もう1問」と聞き、y なら1問出して、「追加」のメモ付きで記録する。n で終わる

        入力：python drill.py で、「a」「a」、もう1問は「y」、「a」、もう1問は「n」
        期待：終了コード0。「もう1問」の案内が出る。記録は3行で、3行目の note が「追加」。progress の pending は空
        根拠：Claude 版の決まり9（「もう1問」で続けられる。何回でも）と決まり7（追加も記録する）
        """
        code, out, err = self.day(WEDNESDAY, "a\na\ny\na\nn\n")
        self.assertEqual(code, 0, err)
        self.assertIn("もう1問", out)
        rows = recorder.read_log(self.log_path)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2]["note"], "追加")
        self.assertEqual(rows[0]["note"], "")
        self.assertEqual(self.progress()["pending"], [])

    def test_06_no_answer_to_the_extra_question_ends_quietly(self):
        """TC-EXT-06 | 異常系 | 「もう1問」の答えがなくても（入力の終わり）、エラーにせず正常終了する。記録は増えない

        入力：「a」「a」だけを入力して終える
        期待：終了コード0。Traceback なし。記録は2行
        根拠：Claude 版のボタンで「今日は終わり」と同じ。何も答えなければ、何も変えない（難易度の提案と同じ扱い）
        """
        code, out, err = self.day(WEDNESDAY, "a\na\n")
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(len(recorder.read_log(self.log_path)), 2)

    def test_07_extra_not_offered_on_rest_day_or_for_a_file(self):
        """TC-EXT-07 | 境界値 | 休みの日と、問題集を指定した練習では、「もう1問」を聞かない

        入力：日曜に起動／問題集のファイルを指定して起動
        期待：どちらも「もう1問」が出ない
        根拠：休みの日は出題しない（設計書 §5-2）。練習は進み具合を使わない（設計書 §5）
        """
        code, out, err = self.day("2026-10-18", "")
        self.assertEqual(code, 0, err)
        self.assertNotIn("もう1問", out)
        path = self.qdir / "python" / "u01.yaml"
        code, out, err = self.run_drill([path, "--date", WEDNESDAY], "a\na\n", qdir=self.qdir)
        self.assertEqual(code, 0, err)
        self.assertNotIn("もう1問", out)

    def test_08_unit_done_notice_after_the_last_questions(self):
        """TC-EXT-08 | 正常系 | 単元の最後の問題を解き終えたら、Git に保存するコマンドの案内が出る。途中では出ない

        入力：u01（4問）を、1日目（2問）と2日目（2問）で解く
        期待：1日目の画面には案内がない。2日目の画面には「単元」「u01」「git commit」がある
        根拠：Claude 版の解説のルール7（単元の最後の問題を解き終えたら、Git に保存・公開するかを聞く）。設計書 §5-12
        """
        code, out1, err = self.day(WEDNESDAY, "a\na\n")
        self.assertNotIn("git commit", out1)
        code, out2, err = self.day("2026-10-15", "a\na\n")
        self.assertIn("u01", out2)
        self.assertIn("git commit", out2)

    def test_09_unit_done_notice_function(self):
        """TC-EXT-09 | 単体 | unit_done_notice は、出し終えた単元だけを案内する

        入力：u01 の4問のうち2問だけ記録した状態／4問とも記録した状態
        期待：前者は空、後者は u01 を含む案内
        根拠：同上
        """
        entries = [{"lang": "python", "path": self.qdir / "python" / "u01.yaml", "q": None, "round": 1}]
        rows = [{"lang": "python", "qid": q, "round": "1"} for q in ("p-1", "p-2")]
        self.assertEqual(session.unit_done_notice(entries, rows), [])
        rows += [{"lang": "python", "qid": q, "round": "1"} for q in ("p-3", "p-4")]
        text = "\n".join(session.unit_done_notice(entries, rows))
        self.assertIn("u01", text)


class LevelDownTest(CliTestCase):
    def setUp(self):
        super().setUp()
        self.qdir = self.folder / "qdir"
        self.write_questions(unit_yaml("p-1", "p-2"), "u01.yaml", self.qdir / "python")
        (self.folder / "config.yaml").write_text("languages: [python]\n", encoding="utf-8")

    def test_10_lower_level_goes_down_by_one_and_stops_at_one(self):
        """TC-EXT-10 | 境界値 | 難易度を1つ下げ、下げた日を記録する。Lv1 からは下がらない

        入力：Lv3 で lower_level／Lv1 で lower_level
        期待：Lv2 になり since が今日／Lv1 のまま
        根拠：Claude 版の決まり3（毎日の難易度の選択：同じ／少し難しく／やさしく）。難易度は 1〜5
        """
        progress = {"langs": {}, "pending": []}
        raise_level(progress, "python", WED)
        raise_level(progress, "python", WED)
        self.assertEqual(lang_state(progress, "python")["level"], 3)
        lower_level(progress, "python", SAT)
        state = lang_state(progress, "python")
        self.assertEqual((state["level"], state["since"]), (2, SAT.isoformat()))
        lower_level(progress, "python", SAT)
        lower_level(progress, "python", SAT)
        self.assertEqual(lang_state(progress, "python")["level"], 1)

    def test_11_cli_level_down(self):
        """TC-EXT-11 | 正常系 | python drill.py --level-down で、問題を解かずに難易度を1つ下げられる

        入力：--level-up python のあとに --level-down python。続けて、すでに Lv1 で --level-down
        期待：「Lv2 から Lv1 に下げました」。progress の level は 1。もう一度では「すでに最低」
        根拠：Claude 版の決まり3（やさしくの選択）。--level-up と対になる
        """
        args = ["--date", WEDNESDAY]
        self.run_drill(["--level-up", "python", *args], qdir=self.qdir)
        code, out, err = self.run_drill(["--level-down", "python", *args], qdir=self.qdir)
        self.assertEqual(code, 0, err)
        self.assertIn("Lv2 から Lv1", out)
        code, out, err = self.run_drill(["--level-down", "python", *args], qdir=self.qdir)
        self.assertIn("すでに最低", out)
        state = json.loads(self.progress_path.read_text(encoding="utf-8"))["langs"]["python"]
        self.assertEqual(state["level"], 1)

    def test_12_cli_level_down_unknown_language(self):
        """TC-EXT-12 | 異常系 | 存在しない言語で --level-down すると、Traceback なしのエラーで終了コード1

        入力：--level-down nothing
        期待：終了コード1。標準エラーに「エラー」と言語名。Traceback なし
        根拠：設計書 §5 エラーの扱い（--level-up と同じ）
        """
        code, out, err = self.run_drill(["--level-down", "nothing"], qdir=self.qdir)
        self.assertEqual(code, 1)
        self.assertIn("エラー", err)
        self.assertIn("nothing", err)
        self.assertNotIn("Traceback", err)


class LongDayTest(CliTestCase):
    def setUp(self):
        super().setUp()
        self.qdir = self.folder / "qdir"
        self.write_questions(unit_yaml("p-1", "p-2", "p-3", "p-4"), "u01.yaml", self.qdir / "python")
        self.write_questions(long_yaml("L-1", "L-2"), "u90_long.yaml", self.qdir / "python")
        self.config = self.folder / "config.yaml"
        self.config.write_text("languages: [python]\nquestions_per_day: 2\n", encoding="utf-8")

    def qids(self):
        return [r["qid"] for r in recorder.read_log(self.log_path)]

    def test_13_saturday_adds_one_long_question(self):
        """TC-EXT-13 | 正常系 | 土曜は、日常の2問に加えて、長めの読解の問題を1問出す

        入力：土曜（2026-10-17）に起動して、「a」を4回
        期待：記録は3行。そのうち1問が長めの読解（L-1 か L-2）。「長めの読解」の案内が出る
        根拠：Claude 版の長めのデータを読み解く問題（週1回「長めの日」。土曜に1問）
        """
        code, out, err = self.run_drill(["--date", SATURDAY], "a\na\na\nn\n", qdir=self.qdir)
        self.assertEqual(code, 0, err)
        ids = self.qids()
        self.assertEqual(len(ids), 3)
        self.assertEqual(len([i for i in ids if i.startswith("L-")]), 1)
        self.assertIn("長めの読解", out)

    def test_14_weekdays_never_pick_long_questions(self):
        """TC-EXT-14 | 正常系 | 土曜以外では、長めの読解の問題は出ない（日常の問題の選び方・単元の完了の数え方にも入らない）

        入力：水曜に2回（別の日として）起動
        期待：記録のどれにも L- が入らない。u01 の4問が出し終わる（長めの問題が残っていても、単元は完了する）
        根拠：長めの日は週1回だけ。日常の2問に混ぜない
        """
        self.run_drill(["--date", WEDNESDAY], "a\na\nn\n", qdir=self.qdir)
        self.run_drill(["--date", "2026-10-15"], "a\na\nn\n", qdir=self.qdir)
        ids = self.qids()
        self.assertEqual(sorted(ids), ["p-1", "p-2", "p-3", "p-4"])

    def test_15_long_day_can_be_changed_or_turned_off(self):
        """TC-EXT-15 | 正常系 | 設定 long_day で、長めの日の曜日を変えられ、none で無効にできる

        入力：long_day: none で土曜に起動／long_day: wed で水曜に起動
        期待：none の土曜は2行で L- なし。wed の水曜は3行で L- が1つ
        根拠：本人が曜日を変えられるように（README の設定の説明）
        """
        self.config.write_text("languages: [python]\nlong_day: none\n", encoding="utf-8")
        self.run_drill(["--date", SATURDAY], "a\na\nn\n", qdir=self.qdir)
        self.assertEqual(len(self.qids()), 2)
        self.assertFalse([i for i in self.qids() if i.startswith("L-")])
        self.log_path.unlink()
        self.progress_path.unlink()
        self.config.write_text("languages: [python]\nlong_day: wed\n", encoding="utf-8")
        self.run_drill(["--date", WEDNESDAY], "a\na\na\nn\n", qdir=self.qdir)
        self.assertEqual(len([i for i in self.qids() if i.startswith("L-")]), 1)

    def test_16_long_day_setting_is_validated(self):
        """TC-EXT-16 | 異常系 | long_day に曜日以外を書くと、分かるエラーになる。既定は sat

        入力：long_day: friday（曜日の名前ではない）／long_day を書かない設定
        期待：ConfigError（long_day を含む）／既定値は "sat"
        根拠：設計書 §7（設定は書き間違いを分かる文章で知らせる）
        """
        self.config.write_text("long_day: friday\n", encoding="utf-8")
        with self.assertRaises(ConfigError) as ctx:
            load_config(self.config)
        self.assertIn("long_day", str(ctx.exception))
        self.assertEqual(load_config(self.folder / "none.yaml")["long_day"], "sat")

    def test_17_long_question_left_pending_is_asked_again(self):
        """TC-EXT-17 | 異常系 | 長めの問題を答えずにやめたら、翌日、未回答として出し直される

        入力：土曜に2問だけ答えて中断（長めの問題は未回答）→月曜に起動
        期待：月曜は、未回答の1問だけ（長めの問題）が出る
        根拠：決定事項 判断1（途中でやめた問題は未回答として残る）。長めの問題も同じ扱い
        """
        self.run_drill(["--date", SATURDAY], "a\na\n", qdir=self.qdir)
        pending = json.loads(self.progress_path.read_text(encoding="utf-8"))["pending"]
        self.assertEqual(len(pending), 1)
        code, out, err = self.run_drill(["--date", "2026-10-19"], "a\nn\n", qdir=self.qdir)
        self.assertEqual(code, 0, err)
        self.assertIn("未回答", out)
        self.assertTrue(self.qids()[-1] == pending[0]["qid"])


class LongUnitTest(CliTestCase):
    def test_19_long_questions_do_not_block_the_unit_from_finishing(self):
        """TC-EXT-19 | 境界値 | 長めの読解の問題が残っていても、日常の問題を出し終えた単元は完了とみなし、次の単元に進む

        入力：u01（p-1, p-2）・長めの問題（L-1）・u02（p-3, p-4）。水曜、木曜の順に起動
        期待：水曜は p-1・p-2、木曜は p-3・p-4（L-1 が残っていても、u01 に留まらない）
        根拠：長めの問題は週1回だけ。単元の完了の数え方に入れると、単元が終わらなくなる
        """
        qdir = self.folder / "qdir"
        self.write_questions(unit_yaml("p-1", "p-2"), "u01.yaml", qdir / "python")
        self.write_questions(long_yaml("L-1"), "u05_long.yaml", qdir / "python")
        self.write_questions(unit_yaml("p-3", "p-4"), "u10.yaml", qdir / "python")
        (self.folder / "config.yaml").write_text("languages: [python]\n", encoding="utf-8")
        self.run_drill(["--date", WEDNESDAY], "a\na\nn\n", qdir=qdir)
        self.run_drill(["--date", "2026-10-15"], "a\na\nn\n", qdir=qdir)
        ids = [r["qid"] for r in recorder.read_log(self.log_path)]
        self.assertEqual(sorted(ids[:2]), ["p-1", "p-2"])
        self.assertEqual(sorted(ids[2:]), ["p-3", "p-4"])


    def test_20_long_question_in_the_same_file_does_not_block_either(self):
        """TC-EXT-20 | 境界値 | 長めの読解の問題が、日常の問題と同じファイルにあっても、そのファイルの単元は日常の問題だけで完了する

        入力：u01（p-1, p-2 と、長めの L-1 を同じファイルに）・u02（p-3, p-4）。水曜、木曜の順に起動
        期待：水曜は p-1・p-2、木曜は p-3・p-4
        根拠：単元の完了は日常の問題で数える（TC-EXT-19 は別ファイルの場合）
        """
        qdir = self.folder / "qdir"
        self.write_questions(unit_yaml("p-1", "p-2") + long_yaml("L-1"), "u01.yaml", qdir / "python")
        self.write_questions(unit_yaml("p-3", "p-4"), "u02.yaml", qdir / "python")
        (self.folder / "config.yaml").write_text("languages: [python]\n", encoding="utf-8")
        self.run_drill(["--date", WEDNESDAY], "a\na\nn\n", qdir=qdir)
        self.run_drill(["--date", "2026-10-15"], "a\na\nn\n", qdir=qdir)
        ids = [r["qid"] for r in recorder.read_log(self.log_path)]
        self.assertEqual(sorted(ids[2:]), ["p-3", "p-4"])


class LongCheckerTest(unittest.TestCase):
    def test_18_checker_accepts_long_flag_only_as_boolean(self):
        """TC-EXT-18 | 異常系 | 問題の long は true か false だけを認める。文字や数値は誤り

        入力：long: true／long: "yes"／long: 1 の問題
        期待：true は誤りなし。ほかは long を含む誤り
        根拠：設計書 §4（YAMLは型を取り違えやすい。引用符なしの値の検査と同じ考え）
        """
        base = {"id": "a", "unit": "u", "level": 1, "type": "blank", "question": "q",
                "code": "x = ___", "answer": "z", "explanation": "e"}
        ok = checker.check_questions([dict(base, long=True)])
        self.assertEqual([str(p) for p in ok], [])
        for bad in ("yes", 1):
            problems = checker.check_questions([dict(base, long=bad)])
            self.assertTrue(any("long" in str(p) for p in problems), bad)
