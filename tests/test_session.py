"""学習の流れ（session.py）の単体テスト

session.py は、画面（input / print）を使わない部品。drill.py（文字の画面）・gui.py・web.py が
同じ部品を使えるように、「今日は何を出すか」「採点して記録する」「難易度の提案」を受け持つ。
ここでは画面なしで、その動きを確かめる。
説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import config
import loader
import progress as progress_mod
import recorder
import session
from checker import Problem
from progress import ProgressError
from recorder import LogFileError

WEDNESDAY = date(2026, 10, 14)  # 水曜日（学習する日）
SUNDAY = date(2026, 10, 18)  # 日曜日（休みの日）
RULES = {"case_sensitive": True, "ignore_spaces": True, "name": "Python"}


def unit_yaml(*qids, level=1):
    """答えがどれも「a」の問題集（YAML）を作る。"""
    return "".join(
        f"""- id: {qid}
  unit: 単元
  level: {level}
  type: blank
  question: 問題{qid}
  code: x = ___
  answer: a
  explanation: 解説{qid}
"""
        for qid in qids
    )


class SessionTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.log_path = self.folder / "data" / "log.csv"
        self.progress_path = self.folder / "data" / "progress.json"
        self.qdir = self.folder / "questions"
        self.cfg = config.load_config(self.folder / "none.yaml")  # 既定値
        self.cfg["languages"] = ["python"]

    def write_unit(self, name, *qids, lang="python"):
        folder = self.qdir / lang
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_text(unit_yaml(*qids), encoding="utf-8")
        return path

    def make_units(self):
        self.write_unit("u01.yaml", "p-1", "p-2")
        self.write_unit("u02.yaml", "p-3", "p-4")

    def plan(self, today=WEDNESDAY):
        return session.plan_scheduled(self.cfg, self.qdir, self.log_path, self.progress_path, today)

    def saved_progress(self):
        return json.loads(self.progress_path.read_text(encoding="utf-8"))

    def entry(self, qid="p-1", path=None):
        path = path or self.write_unit("u01.yaml", "p-1", "p-2")
        q = next(q for q in loader.load_questions(path) if q["id"] == qid)
        return {"lang": "python", "path": path, "q": q, "round": 1}


class JudgeTest(SessionTestCase):
    def test_01_correct(self):
        """TC-SES-01 | 正常系 | 正解を入力すると、正解と判定され、解説が付く

        入力：答えが「a」の問題に「a」
        期待：correct が True。解説は問題の解説。表示する正解は「a」
        根拠：決定事項 段階6-3（採点を画面から切り離す）
        """
        q = self.entry()["q"]
        out = session.judge("a", q, RULES)
        self.assertTrue(out.correct)
        self.assertEqual(out.shown_answer, "a")
        self.assertEqual(out.explanation, "解説p-1")

    def test_02_wrong(self):
        """TC-SES-02 | 正常系 | 間違いを入力すると、不正解と判定される

        入力：答えが「a」の問題に「z」
        期待：correct が False。表示する正解は「a」
        根拠：設計書 §5-7
        """
        out = session.judge("z", self.entry()["q"], RULES)
        self.assertFalse(out.correct)
        self.assertEqual(out.shown_answer, "a")

    def test_03_multiple_answers_shows_first(self):
        """TC-SES-03 | 境界値 | 正解が複数の書き方（リスト）のとき、表示する正解は先頭の書き方

        入力：答えが ["f", "F"] の問題に「F」と「g」
        期待：「F」は正解、「g」は不正解。どちらも表示する正解は「f」
        根拠：drill.py のこれまでの動き（先頭の書き方を見せる）を変えない
        """
        q = {"id": "m", "type": "blank", "answer": ["f", "F"], "explanation": "e"}
        self.assertTrue(session.judge("F", q, RULES).correct)
        out = session.judge("g", q, RULES)
        self.assertFalse(out.correct)
        self.assertEqual(out.shown_answer, "f")

    def test_04_choice_number_and_fullwidth(self):
        """TC-SES-04 | 環境差 | 選択式は番号で答えられ、全角で入力しても同じに採点される

        入力：選択肢 [+, -, *, /]・答え「/」の問題に「4」と全角の「４」と「1」
        期待：「4」と「４」は正解、「1」は不正解
        根拠：不具合 D-01・D-02 の再発防止（採点の部品が変わっていないこと）
        """
        q = {"id": "c", "type": "choice", "choices": ["+", "-", "*", "/"], "answer": "/", "explanation": "e"}
        self.assertTrue(session.judge("4", q, RULES).correct)
        self.assertTrue(session.judge("４", q, RULES).correct)
        self.assertFalse(session.judge("1", q, RULES).correct)


class SessionFlowTest(SessionTestCase):
    def open(self, entries, with_progress=False):
        if with_progress:
            prog = progress_mod.load_progress(self.progress_path)
            return session.Session(entries, self.log_path, WEDNESDAY, prog, self.progress_path), prog
        return session.Session(entries, self.log_path, WEDNESDAY), None

    def test_05_answer_then_record(self):
        """TC-SES-05 | 正常系 | 答えて記録すると、記録に1行増え、次の問題に進む

        入力：2問のセッションで、1問目に「a」と答えて record
        期待：記録が1行（qid=p-1、correct=1、日付は渡した日）。現在の問題が2問目になる
        根拠：設計書 §5-8（1問答えるたびに記録する）
        """
        e1, e2 = self.entry("p-1"), self.entry("p-2")
        s, _ = self.open([e1, e2])
        self.assertEqual(s.number, 1)
        out = s.answer("a")
        self.assertTrue(out.correct)
        s.record()
        rows = recorder.read_log(self.log_path)
        self.assertEqual([(r["qid"], r["correct"], r["date"]) for r in rows], [("p-1", "1", "2026-10-14")])
        self.assertEqual(s.number, 2)
        self.assertEqual(s.current["q"]["id"], "p-2")

    def test_06_answer_alone_does_not_record(self):
        """TC-SES-06 | 境界値 | answer だけでは記録されない（画面に結果を出してから record する順番を守れる）

        入力：answer だけを呼ぶ
        期待：記録ファイルはまだ作られない。現在の問題も進まない
        根拠：これまでの drill.py は「結果を表示 → 記録」の順。記録に失敗したとき、表示済みの結果が変わらないようにする
        """
        s, _ = self.open([self.entry("p-1")])
        s.answer("a")
        self.assertFalse(self.log_path.exists())
        self.assertEqual(s.number, 1)
        self.assertEqual(s.results, [])

    def test_07_finished_and_results(self):
        """TC-SES-07 | 正常系 | 全部答えると終了になり、正誤の一覧が残る

        入力：2問に「a」（正解）と「z」（不正解）
        期待：finished が True。results は [True, False]。current は None
        根拠：設計書 §5-7（最後に正解数を出す）
        """
        s, _ = self.open([self.entry("p-1"), self.entry("p-2")])
        for raw in ("a", "z"):
            s.answer(raw)
            s.record()
        self.assertTrue(s.finished)
        self.assertEqual(s.results, [True, False])
        self.assertIsNone(s.current)
        self.assertEqual(s.total, 2)

    def test_08_wrong_order_raises(self):
        """TC-SES-08 | 異常系 | 順番を間違えた呼び出し（record だけ、終了後の answer）は SessionError にする

        入力：answer の前に record。全問終えたあとに answer
        期待：どちらも SessionError（黙って壊れた記録を作らない）
        根拠：画面側（GUI など）の呼び間違いに気づけるように
        """
        s, _ = self.open([self.entry("p-1")])
        with self.assertRaises(session.SessionError):
            s.record()
        s.answer("a")
        s.record()
        with self.assertRaises(session.SessionError):
            s.answer("a")

    def test_09_progress_pending_removed_and_saved(self):
        """TC-SES-09 | 正常系 | 進み具合を渡したときは、1問答えるたびに未回答から外して保存する

        入力：未回答に p-1・p-2 がある状態で、1問目だけ答えて record
        期待：保存された progress.json の pending は p-2 だけ
        根拠：決定事項 判断1（中断しても、答えていない問題だけが残る）
        """
        e1, e2 = self.entry("p-1"), self.entry("p-2")
        s, prog = self.open([e1, e2], with_progress=True)
        progress_mod.add_pending(
            prog, [{"lang": "python", "file": "u01.yaml", "qid": q} for q in ("p-1", "p-2")]
        )
        s.answer("a")
        s.record()
        self.assertEqual([i["qid"] for i in self.saved_progress()["pending"]], ["p-2"])

    def test_10_no_progress_no_file(self):
        """TC-SES-10 | 正常系 | 進み具合を渡さなければ、進み具合のファイルを作らない

        入力：進み具合なしで1問答える
        期待：progress.json は作られない
        根拠：問題集を指定した練習は、進み具合を変えない（TC-CLI-52 と同じ方針）
        """
        s, _ = self.open([self.entry("p-1")])
        s.answer("a")
        s.record()
        self.assertFalse(self.progress_path.exists())

    def test_11_log_failure(self):
        """TC-SES-11 | 異常系 | 記録に失敗したときは LogFileError になり、次の問題には進まない

        入力：記録先がフォルダ
        期待：LogFileError。number は 1 のまま、results は空
        根拠：記録できなかった問題を「答えた」ことにしないため
        """
        s = session.Session([self.entry("p-1")], self.folder, WEDNESDAY)
        s.answer("a")
        with self.assertRaises(LogFileError):
            s.record()
        self.assertEqual(s.number, 1)
        self.assertEqual(s.results, [])

    def test_12_summary_lines(self):
        """TC-SES-12 | 正常系 | 最後の2行（正解数と記録先）の文章を作る

        入力：[True, False]、記録先 data/log.csv
        期待：「今日は 2 問中 1 問正解でした。」と「結果を記録しました: <記録先>」
        根拠：drill.py のこれまでの表示を変えない
        """
        lines = session.summary_lines([True, False], self.log_path)
        self.assertEqual(
            lines, ["今日は 2 問中 1 問正解でした。", f"結果を記録しました: {self.log_path}"]
        )


class PlanScheduledTest(SessionTestCase):
    def test_13_rest_day(self):
        """TC-SES-13 | 正常系 | 休みの日は、休みの案内だけで、問題も記録も進み具合の変更もない

        入力：日曜（days は月〜土）
        期待：kind が rest。entries は空。案内の文章に「休み」。記録ファイルも作られない
        根拠：設計書 §5-2
        """
        self.make_units()
        plan = self.plan(SUNDAY)
        self.assertEqual(plan.kind, "rest")
        self.assertEqual(plan.entries, [])
        self.assertIn("休み", "\n".join(plan.intro))
        self.assertFalse(self.log_path.exists())

    def test_14_first_day(self):
        """TC-SES-14 | 正常系 | 初日は、先頭の単元から1日の問題数だけ選び、未回答として進み具合に保存する

        入力：python に u01（2問）・u02（2問）、記録なし、水曜
        期待：kind が today。lang が python。2問すべて u01 の問題。案内に「今日の言語：Python」と「単元：u01」と「Lv1」と「周回：1」。保存された pending は2件、unit は u01.yaml
        根拠：決定事項 判断1・3
        """
        self.make_units()
        plan = self.plan()
        self.assertEqual(plan.kind, "today")
        self.assertEqual(plan.lang, "python")
        self.assertEqual({e["q"]["id"] for e in plan.entries}, {"p-1", "p-2"})
        text = "\n".join(plan.intro)
        for word in ("今日の言語：", "単元：u01", "Lv1", "周回：1"):
            self.assertIn(word, text)
        saved = self.saved_progress()
        self.assertEqual(len(saved["pending"]), 2)
        self.assertEqual(saved["langs"]["python"]["unit"], "u01.yaml")

    def test_15_pending_first(self):
        """TC-SES-15 | 正常系 | 未回答が残っていれば、その問題だけを出す（新しい問題は選ばない）

        入力：1日目の計画を作り、1問も答えずに翌日の計画を作る
        期待：kind が pending。案内に「前回の未回答の問題を出します（2問）。」。entries は1日目と同じ2問
        根拠：決定事項 判断1
        """
        self.make_units()
        first = {e["q"]["id"] for e in self.plan().entries}
        plan = self.plan(date(2026, 10, 15))
        self.assertEqual(plan.kind, "pending")
        self.assertIn("前回の未回答の問題を出します（2問）。", plan.intro)
        self.assertEqual({e["q"]["id"] for e in plan.entries}, first)

    def test_16_missing_pending_dropped(self):
        """TC-SES-16 | 異常系 | 未回答の問題が問題集から無くなっていたら、お知らせを付けて通常の計画に進む

        入力：pending に存在しない問題 gone を書いた進み具合
        期待：kind が today。案内の先頭に「gone」「見つかりません」を含む行。保存された pending に gone は残らない
        根拠：TC-CLI-51 と同じ。問題集を編集して問題を消した場合に止まらないため
        """
        self.make_units()
        self.progress_path.parent.mkdir(parents=True)
        self.progress_path.write_text(
            json.dumps({"langs": {}, "pending": [{"lang": "python", "file": "u01.yaml", "qid": "gone"}]}),
            encoding="utf-8",
        )
        plan = self.plan()
        self.assertEqual(plan.kind, "today")
        self.assertIn("gone", plan.intro[0])
        self.assertIn("見つかりません", plan.intro[0])
        self.assertNotIn("gone", [i["qid"] for i in self.saved_progress()["pending"]])

    def test_17_empty_unit(self):
        """TC-SES-17 | 異常系 | 問題が0問の問題集のときは、SessionError にする

        入力：中身が空の u01.yaml
        期待：SessionError（「問題がありません」を含む）
        根拠：TC-CLI-08 と同じ。画面側が1行のエラーにできるように
        """
        folder = self.qdir / "python"
        folder.mkdir(parents=True)
        (folder / "u01.yaml").write_text("", encoding="utf-8")
        with self.assertRaises(session.SessionError) as cm:
            self.plan()
        self.assertIn("問題がありません", str(cm.exception))

    def test_18_problems_stop_before_asking(self):
        """TC-SES-18 | 異常系 | 問題集に誤りがあれば、出題の計画を作らず SessionError にする

        入力：level が 9 の問題を含む問題集
        期待：SessionError（「--check」を含む）。進み具合は保存されない
        根拠：不具合 D-07・D-08 の対応（出題の前の検査）
        """
        folder = self.qdir / "python"
        folder.mkdir(parents=True)
        (folder / "u01.yaml").write_text(unit_yaml("p-1").replace("level: 1", "level: 9"), encoding="utf-8")
        with self.assertRaises(session.SessionError) as cm:
            self.plan()
        self.assertIn("--check", str(cm.exception))
        self.assertFalse(self.progress_path.exists())

    def test_19_broken_progress(self):
        """TC-SES-19 | 異常系 | 進み具合のファイルが壊れていたら ProgressError にし、ファイルは上書きしない

        入力：壊れた progress.json
        期待：ProgressError。ファイルの中身は元のまま
        根拠：TC-CLI-50 と同じ。壊れたまま黙って初期化しないため
        """
        self.make_units()
        self.progress_path.parent.mkdir(parents=True)
        self.progress_path.write_text("{こわれた", encoding="utf-8")
        with self.assertRaises(ProgressError):
            self.plan()
        self.assertEqual(self.progress_path.read_text(encoding="utf-8"), "{こわれた")

    def test_20_questions_per_day(self):
        """TC-SES-20 | 境界値 | 設定の questions_per_day の数だけ選ぶ

        入力：questions_per_day が 1
        期待：entries は1問
        根拠：設計書 §7
        """
        self.make_units()
        self.cfg["questions_per_day"] = 1
        self.assertEqual(len(self.plan().entries), 1)

    def test_21_explain_problems_limited(self):
        """TC-SES-21 | 境界値 | 誤りの説明は先頭3件だけで、残りの件数と --check の案内を付ける

        入力：誤り5件
        期待：全体で「5件」。3件の行と「ほか 2件」と「--check」を含む
        根拠：TC-CLI-36（起動時のエラー表示は長くなりすぎない）
        """
        problems = [Problem(None, f"q-{i}", f"誤り{i}") for i in range(5)]
        text = session.explain_problems(problems, Path("x.yaml"))
        self.assertIn("5件", text)
        self.assertIn("[q-2]", text)
        self.assertNotIn("[q-3]", text)
        self.assertIn("ほか 2件", text)
        self.assertIn("--check", text)


class PlanFileTest(SessionTestCase):
    def test_22_plan_file(self):
        """TC-SES-22 | 正常系 | 問題集を指定したときは、そのファイルからランダムに選び、進み具合は使わない

        入力：u01.yaml（2問）、questions_per_day が 2
        期待：kind が file。entries は2問で round は 1（既定）。lang はフォルダ名（python）。進み具合は None。案内に「今日の言語：」
        根拠：設計方針（ファイル指定は、お試し・単発の用途）
        """
        path = self.write_unit("u01.yaml", "p-1", "p-2")
        plan = session.plan_file(path, self.cfg)
        self.assertEqual(plan.kind, "file")
        self.assertEqual(len(plan.entries), 2)
        self.assertEqual({e["round"] for e in plan.entries}, {recorder.DEFAULT_ROUND})
        self.assertEqual({e["lang"] for e in plan.entries}, {"python"})
        self.assertIsNone(plan.progress)
        self.assertTrue(plan.intro[0].startswith("今日の言語："))

    def test_23_plan_file_errors(self):
        """TC-SES-23 | 異常系 | 問題が0問・誤りありの問題集は SessionError にする

        入力：空のファイル、level が 9 のファイル
        期待：どちらも SessionError（前者は「問題がありません」、後者は「--check」）
        根拠：TC-CLI-08・11 と同じ
        """
        folder = self.qdir / "python"
        folder.mkdir(parents=True)
        empty = folder / "e.yaml"
        empty.write_text("", encoding="utf-8")
        bad = folder / "b.yaml"
        bad.write_text(unit_yaml("p-1").replace("level: 1", "level: 9"), encoding="utf-8")
        with self.assertRaises(session.SessionError) as cm:
            session.plan_file(empty, self.cfg)
        self.assertIn("問題がありません", str(cm.exception))
        with self.assertRaises(session.SessionError) as cm:
            session.plan_file(bad, self.cfg)
        self.assertIn("--check", str(cm.exception))


class LevelUpTest(SessionTestCase):
    def perfect_days(self, *days):
        rows = [
            recorder.make_row({"id": f"x{d}", "unit": "u", "level": 1}, True, "python", date.fromisoformat(d))
            for d in days
        ]
        recorder.append_log(self.log_path, rows)

    def prog(self):
        return progress_mod.load_progress(self.progress_path)

    def test_24_no_offer_before_streak(self):
        """TC-SES-24 | 正常系 | 全問正解の連続が足りなければ、提案は出ない

        入力：全問正解の日が1日だけ（level_up_streak は 2）
        期待：提案は None
        根拠：決定事項 判断4
        """
        self.perfect_days("2026-10-13")
        self.assertIsNone(session.level_up_offer(self.prog(), "python", self.log_path, 2))

    def test_25_offer_when_streak(self):
        """TC-SES-25 | 正常系 | 全問正解が続いていれば、日数と上げる前後の難易度つきで提案が出る

        入力：全問正解の日が2日続いている
        期待：提案の streak が 2、from_level が 1、to_level が 2
        根拠：決定事項 判断4
        """
        self.perfect_days("2026-10-13", "2026-10-14")
        offer = session.level_up_offer(self.prog(), "python", self.log_path, 2)
        self.assertEqual((offer.streak, offer.from_level, offer.to_level), (2, 1, 2))

    def test_26_no_offer_at_max(self):
        """TC-SES-26 | 境界値 | すでに最高の難易度なら、連続していても提案は出ない

        入力：Lv5 の言語で、全問正解が2日続いている
        期待：提案は None
        根拠：難易度は 1〜5
        """
        self.perfect_days("2026-10-13", "2026-10-14")
        prog = self.prog()
        progress_mod.lang_state(prog, "python")["level"] = progress_mod.MAX_LEVEL
        self.assertIsNone(session.level_up_offer(prog, "python", self.log_path, 2))

    def test_27_accept(self):
        """TC-SES-27 | 正常系 | 提案を受けると、難易度が1つ上がって保存され、知らせの文章が返る

        入力：Lv1 で accept=True
        期待：level が 2。保存された progress.json も 2。since は今日。文章は「難易度を Lv2 に上げました。」
        根拠：決定事項 判断4
        """
        prog = self.prog()
        message = session.apply_level_up(prog, self.progress_path, "python", WEDNESDAY, True)
        self.assertEqual(message, "難易度を Lv2 に上げました。")
        saved = self.saved_progress()["langs"]["python"]
        self.assertEqual((saved["level"], saved["since"]), (2, "2026-10-14"))

    def test_28_decline(self):
        """TC-SES-28 | 正常系 | 提案を断ると、難易度は変わらず、連続の数え直しになる

        入力：Lv1 で accept=False
        期待：文章は空。level は 1 のまま。since が今日になり、保存される
        根拠：決定事項 判断4（上げない選択のあと、毎日は聞かない）
        """
        prog = self.prog()
        message = session.apply_level_up(prog, self.progress_path, "python", WEDNESDAY, False)
        self.assertEqual(message, "")
        saved = self.saved_progress()["langs"]["python"]
        self.assertEqual((saved["level"], saved["since"]), (1, "2026-10-14"))

    def test_29_parse_yes(self):
        """TC-SES-29 | 境界値 | 「y」「yes」は、大文字・前後の空白があっても「上げる」と読む。それ以外は読まない

        入力：y、Y、yes、" YES "、n、空、はい、yy
        期待：最初の4つが True、残りは False
        根拠：これまでの提案への答え方（[y/N]）を変えない
        """
        for text in ("y", "Y", "yes", " YES "):
            self.assertTrue(session.parse_yes(text), text)
        for text in ("n", "", "はい", "yy"):
            self.assertFalse(session.parse_yes(text), text)

    def test_30_choose_language(self):
        """TC-SES-30 | 正常系 | --level-up の言語を決める：1つなら省略できる。複数なら指定が必要。ないものはエラー

        入力：言語 [python]・指定なし／[python, sql]・指定なし／[python, sql]・ruby／[python, sql]・sql
        期待：python／SessionError／SessionError／sql
        根拠：TC-CLI-47・48 と同じ
        """
        self.assertEqual(session.choose_level_up_language(["python"], ""), "python")
        with self.assertRaises(session.SessionError):
            session.choose_level_up_language(["python", "sql"], "")
        with self.assertRaises(session.SessionError) as cm:
            session.choose_level_up_language(["python", "sql"], "ruby")
        self.assertIn("ruby", str(cm.exception))
        self.assertEqual(session.choose_level_up_language(["python", "sql"], "sql"), "sql")

    def test_31_level_up_now(self):
        """TC-SES-31 | 正常系 | 問題を解かずに難易度を上げる。すでに最高なら変えずに知らせる

        入力：Lv1 で実行→Lv5 で実行
        期待：前者は level が 2 になり「Lv1 から Lv2 に上げました」。後者は「すでに最高」で、level は 5 のまま
        根拠：TC-CLI-47・49 と同じ
        """
        prog = self.prog()
        msg = session.level_up_now(prog, self.progress_path, "python", WEDNESDAY)
        self.assertIn("Lv1 から Lv2 に上げました", msg)
        self.assertEqual(self.saved_progress()["langs"]["python"]["level"], 2)
        progress_mod.lang_state(prog, "python")["level"] = progress_mod.MAX_LEVEL
        msg = session.level_up_now(prog, self.progress_path, "python", WEDNESDAY)
        self.assertIn("すでに最高", msg)
        self.assertEqual(progress_mod.lang_state(prog, "python")["level"], progress_mod.MAX_LEVEL)


class NoScreenTest(SessionTestCase):
    def test_32_no_input_no_print(self):
        """TC-SES-32 | 構造 | 学習の流れ全体が、input も print も使わずに動く

        入力：input と print を「呼ばれたら失敗」にして、計画→2問に答える→記録→提案を実行
        期待：最後まで動き、失敗しない
        根拠：段階6-3の目的（GUI やブラウザからも同じ部品を使えるようにする）
        """
        self.make_units()
        boom = AssertionError("画面を使ってはいけません")
        with mock.patch("builtins.input", side_effect=boom), mock.patch("builtins.print", side_effect=boom):
            plan = self.plan()
            s = session.Session(plan.entries, self.log_path, WEDNESDAY, plan.progress, self.progress_path)
            while not s.finished:
                s.answer("a")
                s.record()
            session.summary_lines(s.results, self.log_path)
            session.level_up_offer(plan.progress, plan.lang, self.log_path, 2)
        self.assertEqual(s.results, [True, True])


if __name__ == "__main__":
    unittest.main()
