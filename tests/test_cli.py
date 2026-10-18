"""画面と全体の流れ（drill.py）の結合テスト

drill.py を実際のコマンドとして起動し、キーボード入力の代わりに入力文字を渡して、
画面の出力・終了コード・記録のファイルを確かめる。
記録は、本物の data/log.csv を汚さないよう、いつも一時フォルダに書く。
説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import recorder

ROOT = Path(__file__).resolve().parent.parent

# 2026-10-14 は水曜日（学習する日）、10-18 は日曜日（休みの日）
WEDNESDAY = "2026-10-14"
SUNDAY = "2026-10-18"

# 答えがどちらも「a」の2問。出題の順番がランダムでも、入力が同じで済む
TWO_QUESTIONS = """\
- id: t-1
  unit: テスト
  level: 1
  type: blank
  question: 問題1
  code: x = ___
  answer: a
  explanation: 解説1
- id: t-2
  unit: テスト
  level: 1
  type: blank
  question: 問題2
  code: y = ___
  answer: a
  explanation: 解説2
"""


def run_drill(args=(), stdin="", cwd=ROOT):
    """drill.py を起動して、(終了コード, 標準出力, エラー出力) を返す。"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run(
        [sys.executable, str(ROOT / "drill.py"), *map(str, args)],
        input=stdin.encode("utf-8"),
        capture_output=True,
        cwd=str(cwd),
        env=env,
        timeout=30,
    )
    return p.returncode, p.stdout.decode("utf-8"), p.stderr.decode("utf-8")


class CliTestCase(unittest.TestCase):
    """結合試験の共通の準備（試験用の一時フォルダと、drill.py を起動する補助）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.log_path = self.folder / "data" / "log.csv"  # 記録先（試験用）
        self.progress_path = self.folder / "data" / "progress.json"  # 進み具合の保存先（試験用）

    def write_questions(self, text, name="q.yaml", folder=None):
        folder = folder or self.folder
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_text(text, encoding="utf-8")
        return path

    def run_drill(self, args=(), stdin="", cwd=ROOT, log=True, config=True, progress=True, qdir=None):
        """記録先と設定ファイルを試験用の場所にして、drill.py を起動する。

        設定ファイルを試験用の場所（まだ作られていない＝既定値）にするのは、
        code-drill の中に本物の config.yaml があっても、試験の結果が変わらないようにするため。
        """
        args = list(args)
        if progress is True:
            args += ["--progress", self.progress_path]
        elif progress:
            args += ["--progress", progress]
        if qdir:
            args += ["--questions-dir", qdir]
        if log is True:
            args += ["--log", self.log_path]
        elif log:
            args += ["--log", log]
        if config is True:
            args += ["--config", self.folder / "config.yaml"]
        elif config:
            args += ["--config", config]
        return run_drill(args, stdin, cwd)


class DrillCommandTest(CliTestCase):
    """問題集の読み込み・採点・記録の結合試験。"""

    def test_01_sample_default(self):
        """TC-CLI-01 | 正常系 | 引数なしで起動すると、見本の問題集から2問が出て、最後に結果が出る

        入力：python drill.py --date 2026-10-14（問題集の指定なし。水曜日に固定。記録先と設定は試験用）。「1」「1」を入力
        期待：終了コード0。「問1」「問2」が表示され、「今日は 2 問中 ◯ 問正解でした。」が出る
        根拠：設計書 §2（python drill.py で今日の2問が解ける）
        """
        code, out, err = self.run_drill(["--date", WEDNESDAY], stdin="1\n1\n")
        self.assertEqual(code, 0, err)
        self.assertIn("--- 問1", out)
        self.assertIn("--- 問2", out)
        self.assertRegex(out, r"今日は 2 問中 [0-2] 問正解でした。")

    def test_02_all_correct(self):
        """TC-CLI-02 | 正常系 | 2問とも正解すると「2 問中 2 問正解」になる

        入力：答えが「a」の2問に、「a」「a」
        期待：終了コード0。「正解です！」が2回出て、「今日は 2 問中 2 問正解でした。」
        根拠：設計書 §5-6〜7
        """
        path = self.write_questions(TWO_QUESTIONS)
        code, out, err = self.run_drill([path], "a\na\n")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count("正解です！"), 2)
        self.assertIn("今日は 2 問中 2 問正解でした。", out)

    def test_03_all_wrong(self):
        """TC-CLI-03 | 正常系 | 2問とも間違えると、正解と解説が出て「2 問中 0 問正解」になる

        入力：答えが「a」の2問に、「z」「z」
        期待：終了コード0。「不正解です。正解は「a」です。」が2回、解説が出て、「今日は 2 問中 0 問正解でした。」
        根拠：設計書 §5-7
        """
        path = self.write_questions(TWO_QUESTIONS)
        code, out, err = self.run_drill([path], "z\nz\n")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count("不正解です。正解は「a」です。"), 2)
        self.assertIn("【解説】", out)
        self.assertIn("今日は 2 問中 0 問正解でした。", out)

    def test_04_fullwidth_input(self):
        """TC-CLI-04 | 環境差 | 日本語入力のまま（全角の英字）答えても正解になる

        入力：答えが「a」の2問に、全角の「ａ」「ａ」
        期待：「今日は 2 問中 2 問正解でした。」
        根拠：日本語IMEをオンにしたまま入力する使い方を想定
        不具合：D-01
        """
        path = self.write_questions(TWO_QUESTIONS)
        code, out, err = self.run_drill([path], "ａ\nａ\n")
        self.assertEqual(code, 0, err)
        self.assertIn("今日は 2 問中 2 問正解でした。", out)

    def test_05_run_from_other_folder(self):
        """TC-CLI-05 | 環境差 | code-drill 以外のフォルダから起動しても、見本の問題集が出る

        入力：別のフォルダ（一時フォルダ）を現在地にして、drill.py をフルパスで起動。「1」「1」
        期待：終了コード0。「問1」が表示される
        根拠：README の手順どおりでない場所から起動する使い方を想定
        不具合：D-06
        """
        code, out, err = self.run_drill(["--date", WEDNESDAY], stdin="1\n1\n", cwd=self.folder)
        self.assertEqual(code, 0, err)
        self.assertIn("--- 問1", out)

    def test_06_missing_file(self):
        """TC-CLI-06 | 異常系 | 存在しない問題集を指定すると、分かるメッセージを出して終了する

        入力：存在しないファイル名
        期待：終了コード1。エラー出力に「見つかりません」を含み、Traceback は出ない
        根拠：誤ったパスの指定でも、原因が分かる表示にする
        不具合：D-04
        """
        code, out, err = self.run_drill([self.folder / "none.yaml"])
        self.assertEqual(code, 1)
        self.assertIn("見つかりません", err)
        self.assertNotIn("Traceback", err)

    def test_07_syntax_error(self):
        """TC-CLI-07 | 異常系 | YAMLの書き方に誤りがあると、分かるメッセージを出して終了する

        入力：引用符が閉じていないYAML
        期待：終了コード1。エラー出力に「YAML」を含み、Traceback は出ない
        根拠：AIが作ったYAMLの書き間違いを想定（設計書 §9）
        不具合：D-04
        """
        path = self.write_questions('- id: "t-1\n   unit: [テスト\n')
        code, out, err = self.run_drill([path])
        self.assertEqual(code, 1)
        self.assertIn("YAML", err)
        self.assertNotIn("Traceback", err)

    def test_08_empty_question_file(self):
        """TC-CLI-08 | 異常系 | 問題が0問の問題集を指定すると、分かるメッセージを出して終了する

        入力：0バイトのYAML
        期待：終了コード1。エラー出力に「問題がありません」を含み、Traceback は出ない
        根拠：設計書 §5-5
        不具合：D-03
        """
        path = self.write_questions("")
        code, out, err = self.run_drill([path])
        self.assertEqual(code, 1)
        self.assertIn("問題がありません", err)
        self.assertNotIn("Traceback", err)

    def test_09_not_a_list(self):
        """TC-CLI-09 | 異常系 | 問題のリストではない形式のYAMLだと、分かるメッセージを出して終了する

        入力：先頭が辞書のYAML
        期待：終了コード1。エラー出力に「リスト」を含み、Traceback は出ない
        根拠：設計書 §4（1ファイルは問題のリスト）
        不具合：D-03
        """
        path = self.write_questions("id: t-1\nunit: テスト\n")
        code, out, err = self.run_drill([path])
        self.assertEqual(code, 1)
        self.assertIn("リスト", err)
        self.assertNotIn("Traceback", err)

    def test_10_input_interrupted(self):
        """TC-CLI-10 | 異常系 | 入力の途中で終了しても（Ctrl+D や入力の終わり）、エラーの画面を出さずに終了する

        入力：見本の問題集に、何も入力しない（入力がすぐ終わる）
        期待：終了コード1。エラー出力に「中断しました」を含み、Traceback は出ない
        根拠：途中でやめたい日があることを想定
        不具合：D-05
        """
        code, out, err = self.run_drill(["--date", WEDNESDAY], stdin="")
        self.assertEqual(code, 1)
        self.assertIn("中断しました", err)
        self.assertNotIn("Traceback", err)

    def test_12_single_question_file(self):
        """TC-CLI-12 | 境界値 | 問題が1問だけの問題集でも、動く

        入力：1問だけの問題集に「a」
        期待：終了コード0。「今日は 1 問中 1 問正解でした。」
        根拠：設計書 §5-5
        """
        one = TWO_QUESTIONS.split("- id: t-2")[0]
        path = self.write_questions(one)
        code, out, err = self.run_drill([path], "a\n")
        self.assertEqual(code, 0, err)
        self.assertIn("今日は 1 問中 1 問正解でした。", out)

    def test_11_missing_required_key(self):
        """TC-CLI-11 | 異常系 | 必須の項目（answer）が欠けた問題があるとき、問題を出す前に分かるメッセージを出して終了する

        入力：answer がない問題を含む問題集に「a」
        期待：終了コード1。問題は出ない。エラー出力に「answer」と「--check」を含み、Traceback は出ない
        根拠：AIが作った問題の書き漏れを想定（設計書 §9）。答えたあとで落ちると入力が無駄になるため
        不具合：D-08（段階6-1で対応。出題の前に、--check と同じ検査を行う）
        """
        broken = TWO_QUESTIONS.replace("  answer: a\n", "")
        path = self.write_questions(broken)
        code, out, err = self.run_drill([path], "a\na\n")
        self.assertEqual(code, 1)
        self.assertIn("answer", err)
        self.assertIn("--check", err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("--- 問1", out)

    def test_13_results_are_recorded(self):
        """TC-CLI-13 | 正常系 | 答えた結果が、記録のファイルに1問1行で書かれる

        入力：「sql」フォルダの中の、答えが「a」の2問に、「a」（正解）と「z」（不正解）
        期待：終了コード0。記録に2行。lang=sql、date=今日、unit=テスト（日本語が正しい）、correct が 1 と 0、qid が t-1 と t-2。画面に「結果を記録しました」
        根拠：設計書 §5-8（log.csv に1問1行で追記する）、§6
        """
        path = self.write_questions(TWO_QUESTIONS, folder=self.folder / "sql")
        code, out, err = self.run_drill([path], "a\nz\n")
        self.assertEqual(code, 0, err)
        self.assertIn("結果を記録しました", out)
        rows = recorder.read_log(self.log_path)
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["lang"] for r in rows}, {"sql"})
        self.assertEqual({r["date"] for r in rows}, {date.today().isoformat()})
        self.assertEqual({r["unit"] for r in rows}, {"テスト"})
        self.assertEqual(sorted(r["correct"] for r in rows), ["0", "1"])
        self.assertEqual({r["qid"] for r in rows}, {"t-1", "t-2"})

    def test_14_recorded_each_question(self):
        """TC-CLI-14 | 正常系 | 1問答えるたびに記録されるので、途中でやめても答えた分は残る

        入力：2問のうち、1問目にだけ「a」と答えて、入力が終わる
        期待：終了コード1（中断）。記録には、1問目の1行だけがある
        根拠：中断したときの記録の扱い（不具合票 D-05 の補足）
        """
        path = self.write_questions(TWO_QUESTIONS)
        code, out, err = self.run_drill([path], "a\n")
        self.assertEqual(code, 1)
        self.assertIn("中断しました", err)
        rows = recorder.read_log(self.log_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["correct"], "1")

    def test_15_run_twice(self):
        """TC-CLI-15 | 正常系 | 2回続けて実行すると、記録が追記され、見出しは1つのまま

        入力：同じ問題集を、同じ記録先で2回実行
        期待：記録は合計4行。見出しの行は1つ
        根拠：毎日使うと、記録が積み重なる（設計書 §5-8）
        """
        path = self.write_questions(TWO_QUESTIONS)
        for _ in range(2):
            code, out, err = self.run_drill([path], "a\na\n")
            self.assertEqual(code, 0, err)
        self.assertEqual(len(recorder.read_log(self.log_path)), 4)
        text = self.log_path.read_text(encoding="utf-8-sig")
        self.assertEqual(text.count("date,qid,lang"), 1)

    def test_16_log_header_mismatch(self):
        """TC-CLI-16 | 異常系 | 記録ファイルの形が違うときは、問題を出す前に分かるメッセージを出して終了する

        入力：見出しが「a,b,c」の記録ファイルを指定して起動
        期待：終了コード1。エラー出力に「記録」を含み、Traceback は出ない。問題は出ない。ファイルは変わらない
        根拠：答えたあとで記録できないと分かると、入力が無駄になるため
        """
        path = self.write_questions(TWO_QUESTIONS)
        self.log_path.parent.mkdir(parents=True)
        original = b"a,b,c\r\n1,2,3\r\n"
        self.log_path.write_bytes(original)
        code, out, err = self.run_drill([path], "a\na\n")
        self.assertEqual(code, 1)
        self.assertIn("記録", err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("--- 問1", out)
        self.assertEqual(self.log_path.read_bytes(), original)

    def test_17_log_path_is_folder(self):
        """TC-CLI-17 | 異常系 | 記録先がフォルダのときは、分かるメッセージを出して終了する

        入力：記録先にフォルダを指定して起動
        期待：終了コード1。エラー出力に「記録」を含み、Traceback は出ない
        根拠：誤った場所の指定でも、原因が分かる表示にする
        """
        path = self.write_questions(TWO_QUESTIONS)
        code, out, err = self.run_drill([path], "a\na\n", log=self.folder)
        self.assertEqual(code, 1)
        self.assertIn("記録", err)
        self.assertNotIn("Traceback", err)


class ScheduleCommandTest(CliTestCase):
    """曜日と言語の切り替え（問題集を指定せずに起動したとき）の結合試験。"""

    def write_log(self, *dates):
        """試験用に、指定した日付の記録を作る（学習した日を再現する）。"""
        rows = [
            recorder.make_row({"id": "x", "unit": "u", "level": 1}, True, "python", date.fromisoformat(d))
            for d in dates
        ]
        recorder.append_log(self.log_path, rows)

    def test_19_sunday_is_rest(self):
        """TC-CLI-19 | 正常系 | 日曜は「休みの日」と表示して、問題を出さずに正常終了する

        入力：python drill.py --date 2026-10-18（日曜）
        期待：終了コード0。「休み」を表示。問題は出ず、記録ファイルも作られない
        根拠：設計書 §5-2
        """
        code, out, err = self.run_drill(["--date", SUNDAY])
        self.assertEqual(code, 0, err)
        self.assertIn("休み", out)
        self.assertNotIn("--- 問1", out)
        self.assertFalse(self.log_path.exists())

    def test_20_first_day_is_first_language(self):
        """TC-CLI-20 | 正常系 | 初日は先頭の言語（python）が出て、記録の lang も python になる

        入力：記録なしで --date 2026-10-14、「1」「1」
        期待：終了コード0。「今日の言語」に Python を表示。記録の lang はすべて python
        根拠：設計書 §5-4
        """
        code, out, err = self.run_drill(["--date", WEDNESDAY], "1\n1\n")
        self.assertEqual(code, 0, err)
        self.assertIn("今日の言語：Python", out)
        rows = recorder.read_log(self.log_path)
        self.assertEqual({r["lang"] for r in rows}, {"python"})
        self.assertEqual({r["date"] for r in rows}, {WEDNESDAY})

    def test_21_second_day_is_second_language(self):
        """TC-CLI-21 | 正常系 | 2日目は2番目の言語（sql）が出る

        入力：前の日（10-13）の記録がある状態で --date 2026-10-14、「1」「1」
        期待：「今日の言語」に SQL を表示。今日の記録の lang はすべて sql
        根拠：切り替えは、記録にある学習日の数で決める（設計書 §5-4）
        """
        self.write_log("2026-10-13")
        code, out, err = self.run_drill(["--date", WEDNESDAY], "1\n1\n")
        self.assertEqual(code, 0, err)
        self.assertIn("今日の言語：SQL", out)
        today_rows = [r for r in recorder.read_log(self.log_path) if r["date"] == WEDNESDAY]
        self.assertEqual({r["lang"] for r in today_rows}, {"sql"})

    def test_22_same_day_twice_same_language(self):
        """TC-CLI-22 | 境界値 | 同じ日に2回実行しても、同じ言語が出る

        入力：同じ日付（--date 2026-10-14）で2回実行
        期待：2回とも「今日の言語：Python」
        根拠：2回目の実行で、言語が切り替わってしまわないように
        """
        for _ in range(2):
            code, out, err = self.run_drill(["--date", WEDNESDAY], "1\n1\n")
            self.assertEqual(code, 0, err)
            self.assertIn("今日の言語：Python", out)

    def test_23_explicit_file_ignores_schedule(self):
        """TC-CLI-23 | 境界値 | 問題集を指定して起動したときは、日曜でも出題される

        入力：問題集のファイルを指定、--date 2026-10-18（日曜）、「a」「a」
        期待：終了コード0。「今日は 2 問中 2 問正解でした。」
        根拠：これまでの使い方（問題集を指定して練習する）を変えない
        """
        path = self.write_questions(TWO_QUESTIONS)
        code, out, err = self.run_drill([path, "--date", SUNDAY], "a\na\n")
        self.assertEqual(code, 0, err)
        self.assertIn("今日は 2 問中 2 問正解でした。", out)

    def test_24_invalid_date(self):
        """TC-CLI-24 | 異常系 | --date の形が正しくないと、分かるメッセージを出して終了する

        入力：--date 2026/10/14、--date 2026-13-01
        期待：どちらも終了コード1。エラー出力に「--date」を含み、Traceback は出ない
        根拠：書き方の間違いに気づけるように
        """
        for bad in ("2026/10/14", "2026-13-01"):
            code, out, err = self.run_drill(["--date", bad])
            self.assertEqual(code, 1, bad)
            self.assertIn("--date", err)
            self.assertNotIn("Traceback", err)

    def test_25_config_language_without_folder(self):
        """TC-CLI-25 | 異常系 | 設定に書いた言語のフォルダがないと、分かるメッセージを出して終了する

        入力：languages: [ruby] の設定（questions/ に ruby がない）
        期待：終了コード1。エラー出力に「ruby」を含み、Traceback は出ない。問題は出ない
        根拠：言語名の書き間違い、フォルダの作り忘れ
        """
        cfg = self.folder / "c.yaml"
        cfg.write_text("languages: [ruby]\n", encoding="utf-8")
        code, out, err = self.run_drill(["--date", WEDNESDAY], config=cfg)
        self.assertEqual(code, 1)
        self.assertIn("ruby", err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("--- 問1", out)

    def test_26_questions_per_day_from_config(self):
        """TC-CLI-26 | 正常系 | 設定の questions_per_day の数だけ出題される

        入力：questions_per_day: 1 の設定、「1」だけを入力
        期待：終了コード0。「今日は 1 問中」と表示される
        根拠：設計書 §7
        """
        cfg = self.folder / "c.yaml"
        cfg.write_text("questions_per_day: 1\n", encoding="utf-8")
        code, out, err = self.run_drill(["--date", WEDNESDAY], "1\n", config=cfg)
        self.assertEqual(code, 0, err)
        self.assertIn("今日は 1 問中", out)

    def test_27_broken_config(self):
        """TC-CLI-27 | 異常系 | 設定ファイルが正しくないと、分かるメッセージを出して終了する

        入力：days に正しくない曜日名を書いた設定
        期待：終了コード1。エラー出力に「days」を含み、Traceback は出ない
        根拠：設計書 §5（エラーは1行で伝える）
        """
        cfg = self.folder / "c.yaml"
        cfg.write_text("days: [mon, funday]\n", encoding="utf-8")
        code, out, err = self.run_drill(["--date", WEDNESDAY], config=cfg)
        self.assertEqual(code, 1)
        self.assertIn("days", err)
        self.assertNotIn("Traceback", err)

    def test_28_custom_days_from_config(self):
        """TC-CLI-28 | 正常系 | 設定の days で、学習する曜日を変えられる

        入力：days: [sun] の設定、--date 2026-10-14（水曜）
        期待：水曜は休みの日になる（問題は出ない）
        根拠：設計書 §7
        """
        cfg = self.folder / "c.yaml"
        cfg.write_text("days: [sun]\n", encoding="utf-8")
        code, out, err = self.run_drill(["--date", WEDNESDAY], config=cfg)
        self.assertEqual(code, 0, err)
        self.assertIn("休み", out)
        self.assertNotIn("--- 問1", out)

    def test_29_rotation_from_config(self):
        """TC-CLI-29 | 正常系 | 設定の language_rotation で、切り替えの割合を変えられる

        入力：language_rotation: {sql: 3} の設定。学習日の3日目（過去2日の記録あり）
        期待：「今日の言語：SQL」
        根拠：設計書 §7
        """
        cfg = self.folder / "c.yaml"
        cfg.write_text("languages: [python, sql]\nlanguage_rotation:\n  sql: 3\n", encoding="utf-8")
        self.write_log("2026-10-12", "2026-10-13")
        code, out, err = self.run_drill(["--date", WEDNESDAY], "1\n1\n", config=cfg)
        self.assertEqual(code, 0, err)
        self.assertIn("今日の言語：SQL", out)

    def test_30_log_not_writable_message(self):
        """TC-CLI-30 | 環境差 | 記録ファイルが書き込めないときは、問題を出す前に止める（Excel対応）

        入力：書き込みを開くと PermissionError になる状態を、drill.py の中の確認で再現できないため、
              記録先に「フォルダ」を指定した場合と同じ経路（問題を出す前の確認）が働くことを確かめる
        期待：終了コード1。問題は出ない。Traceback は出ない
        根拠：答えたあとで記録できないと分かると、入力が無駄になるため（単体は TC-REC-16・17）
        """
        path = self.write_questions(TWO_QUESTIONS)
        code, out, err = self.run_drill([path], "a\na\n", log=self.folder)
        self.assertEqual(code, 1)
        self.assertNotIn("--- 問1", out)
        self.assertNotIn("Traceback", err)


class CheckCommandTest(CliTestCase):
    """問題集の検査（--check）と、出題前の検査の結合試験。"""

    def test_31_check_bundled_ok(self):
        """TC-CLI-31 | 正常系 | --check で、同梱の問題集に誤りがなければ、「誤りはありません」と表示して正常終了する

        入力：python drill.py --check（場所の指定なし。questions/ 全体）
        期待：終了コード0。「誤りはありません」と、検査した問題数（8問）を表示
        根拠：設計書 §5（補助コマンド --check）
        """
        code, out, err = self.run_drill(["--check"], log=False, config=False)
        self.assertEqual(code, 0, err)
        self.assertIn("誤りはありません", out)
        self.assertIn("8問", out)

    def test_32_check_shows_all_problems(self):
        """TC-CLI-32 | 正常系 | --check で、誤りをまとめて表示し、終了コード1になる

        入力：answer が引用符なしの NULL の問題と、level が 9 の問題がある問題集
        期待：終了コード1。標準出力に、両方の問題の id と「引用符」と「level」が出る。件数も出る
        根拠：直す人が、何度も実行し直さなくて済むように。不具合 D-07
        不具合：D-07
        """
        text = (
            "- id: n-1\n  unit: u\n  level: 1\n  type: blank\n  question: q\n"
            "  code: x = ___\n  answer: NULL\n  explanation: e\n"
            "- id: n-2\n  unit: u\n  level: 9\n  type: blank\n  question: q\n"
            '  code: x = ___\n  answer: "a"\n  explanation: e\n'
        )
        path = self.write_questions(text)
        code, out, err = self.run_drill(["--check", path], log=False, config=False)
        self.assertEqual(code, 1)
        for word in ("n-1", "n-2", "引用符", "level"):
            self.assertIn(word, out)
        self.assertIn("2件", out)
        self.assertNotIn("Traceback", err)

    def test_33_check_missing_path(self):
        """TC-CLI-33 | 異常系 | --check で存在しないパスを指定すると、分かるメッセージを出して終了コード1になる

        入力：python drill.py --check 存在しないファイル
        期待：終了コード1。「見つかりません」を表示。Traceback は出ない
        根拠：パスの打ち間違い
        """
        code, out, err = self.run_drill(["--check", self.folder / "none.yaml"], log=False, config=False)
        self.assertEqual(code, 1)
        self.assertIn("見つかりません", out + err)
        self.assertNotIn("Traceback", err)

    def test_34_check_writes_nothing(self):
        """TC-CLI-34 | 境界値 | --check は、記録ファイルを作らず、設定ファイルがなくても動く

        入力：記録先を指定し、設定ファイルが壊れている状態で --check
        期待：終了コード0。記録ファイルは作られない（検査だけを行うため、記録や設定を使わない）
        根拠：検査は、学習の記録とは関係なく、いつでも安全に実行できること
        """
        bad_config = self.folder / "bad.yaml"
        bad_config.write_text("days: [funday]\n", encoding="utf-8")
        path = self.write_questions(TWO_QUESTIONS)
        code, out, err = self.run_drill(["--check", path], config=bad_config)
        self.assertEqual(code, 0, err)
        self.assertFalse(self.log_path.exists())

    def test_35_run_stops_on_answer_null(self):
        """TC-CLI-35 | 異常系 | 引用符なしの NULL が answer にある問題集で起動すると、問題を出す前に直し方を知らせて終了する

        入力：answer: NULL の問題集に「NULL」
        期待：終了コード1。エラー出力に「引用符」を含み、Traceback は出ない。問題は出ない
        根拠：「NULL」と答えても不正解になる問題を、出題しないため
        不具合：D-07（段階6-1で対応。引用符なしの値を検出して知らせる）
        """
        text = TWO_QUESTIONS.replace("  answer: a\n", "  answer: NULL\n", 1)
        path = self.write_questions(text)
        code, out, err = self.run_drill([path], "NULL\nNULL\n")
        self.assertEqual(code, 1)
        self.assertIn("引用符", err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("--- 問1", out)

    def test_36_run_shows_limited_problems(self):
        """TC-CLI-36 | 境界値 | 誤りが多い問題集でも、起動時のエラー表示は長くなりすぎない

        入力：すべての問題の level が不正な問題集（問題が12問）
        期待：終了コード1。エラー出力は10行以内で、「--check」を案内している
        根拠：全部の誤りは --check で見られるため、起動時は先頭の数件だけでよい
        """
        one = (
            "- id: m-{n}\n  unit: u\n  level: 9\n  type: blank\n  question: q\n"
            '  code: x = ___\n  answer: "a"\n  explanation: e\n'
        )
        path = self.write_questions("".join(one.format(n=n) for n in range(12)))
        code, out, err = self.run_drill([path], "a\n")
        self.assertEqual(code, 1)
        self.assertLessEqual(len(err.strip().splitlines()), 10)
        self.assertIn("--check", err)

    def test_37_run_with_good_file_unchanged(self):
        """TC-CLI-37 | 正常系 | 誤りのない問題集は、検査を入れる前と同じように出題される

        入力：正しい2問の問題集に「a」「a」
        期待：終了コード0。「今日は 2 問中 2 問正解でした。」
        根拠：検査を入れたことで、正しい問題集の動きが変わらないこと
        """
        path = self.write_questions(TWO_QUESTIONS)
        code, out, err = self.run_drill([path], "a\na\n")
        self.assertEqual(code, 0, err)
        self.assertIn("今日は 2 問中 2 問正解でした。", out)


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


# 2026-10-14（水）の翌日以降。10-18 は日曜
THURSDAY = "2026-10-15"
FRIDAY = "2026-10-16"
MONDAY_NEXT = "2026-10-19"


class ProgressCommandTest(CliTestCase):
    """単元の進み方・未回答・周回・難易度（段階6-2）の結合試験。

    試験用の問題集：python に u01（p-1, p-2）と u02（p-3, p-4）。答えはすべて「a」。
    1日2問・月〜土が学習日・言語は python のみ。
    """

    def setUp(self):
        super().setUp()
        self.qdir = self.folder / "qdir"
        self.write_questions(unit_yaml("p-1", "p-2"), "u01.yaml", self.qdir / "python")
        self.write_questions(unit_yaml("p-3", "p-4"), "u02.yaml", self.qdir / "python")
        self.write_config()

    def write_config(self, streak=2):
        (self.folder / "config.yaml").write_text(
            f"languages: [python]\nquestions_per_day: 2\nlevel_up_streak: {streak}\n", encoding="utf-8"
        )

    def day(self, day, stdin, extra=()):
        return self.run_drill(["--date", day, *extra], stdin, qdir=self.qdir)

    def progress(self):
        import json

        return json.loads(self.progress_path.read_text(encoding="utf-8"))

    def qids(self):
        return [r["qid"] for r in recorder.read_log(self.log_path)]

    def test_38_interrupt_leaves_pending(self):
        """TC-CLI-38 | 異常系 | 途中でやめると、答えていない問題が「未回答」として残る

        入力：1日目に1問だけ答えて入力を終える（2問のうち1問が未回答）
        期待：終了コード1。progress.json の pending が1件。記録は答えた1問だけ
        根拠：決定事項 判断1
        """
        code, out, err = self.day(WEDNESDAY, "a\n")
        self.assertEqual(code, 1)
        self.assertEqual(len(self.progress()["pending"]), 1)
        self.assertEqual(len(self.qids()), 1)

    def test_39_pending_asked_first_next_day(self):
        """TC-CLI-39 | 正常系 | 翌日は、未回答の問題だけを出す（新しい問題は出さない）

        入力：1日目に1問だけ答えて中断→翌日に「a」
        期待：「前回の未回答」の案内。出題は1問だけで、1日目に答えなかった問題。pending は空になる
        根拠：決定事項 判断1（日をまたいでも未回答を先に出す）
        """
        self.day(WEDNESDAY, "a\n")
        pending_qid = self.progress()["pending"][0]["qid"]
        code, out, err = self.day(THURSDAY, "a\n")
        self.assertEqual(code, 0, err)
        self.assertIn("前回の未回答の問題を出します（1問）", out)
        self.assertIn("今日は 1 問中 1 問正解でした。", out)
        self.assertEqual(self.qids()[-1], pending_qid)
        self.assertEqual(len(set(self.qids())), 2)
        self.assertEqual(self.progress()["pending"], [])

    def test_40_advance_to_next_unit(self):
        """TC-CLI-40 | 正常系 | 単元の問題を全部出し終えたら、次の日は次の単元に進む

        入力：1日目に u01 の2問を答える→2日目
        期待：2日目の問題は p-3・p-4（u02）
        根拠：決定事項 判断3
        """
        self.day(WEDNESDAY, "a\na\n")
        self.day(THURSDAY, "a\na\n")
        self.assertEqual(set(self.qids()[:2]), {"p-1", "p-2"})
        self.assertEqual(set(self.qids()[2:]), {"p-3", "p-4"})

    def test_41_next_round(self):
        """TC-CLI-41 | 境界値 | 最後の単元まで終えたら、周回が1増えて最初の単元に戻る

        入力：3日間（u01→u02→一周して u01）
        期待：3日目の記録の round は 2、問題は p-1・p-2
        根拠：決定事項 判断3
        """
        for d in (WEDNESDAY, THURSDAY, FRIDAY):
            self.day(d, "a\na\n")
        rows = recorder.read_log(self.log_path)
        self.assertEqual({r["round"] for r in rows[:4]}, {"1"})
        self.assertEqual({r["round"] for r in rows[4:]}, {"2"})
        self.assertEqual({r["qid"] for r in rows[4:]}, {"p-1", "p-2"})

    def test_42_status_line(self):
        """TC-CLI-42 | 正常系 | 出題の前に、単元・難易度・周回を表示する

        入力：初日
        期待：「単元：u01」「Lv1」「周回：1」が表示される
        根拠：決定事項（今どこまで進んだかを見えるようにする）
        """
        code, out, err = self.day(WEDNESDAY, "a\na\n")
        self.assertIn("u01", out)
        self.assertIn("Lv1", out)
        self.assertIn("周回：1", out)

    def test_43_level_up_yes(self):
        """TC-CLI-43 | 正常系 | 2日連続で全問正解なら難易度の提案が出て、「y」で1つ上がる

        入力：1日目 全問正解（提案なし）→2日目 全問正解、提案に「y」
        期待：2日目だけ「に上げますか」が出る。progress.json の level が 2
        根拠：決定事項 判断4
        """
        code, out1, err = self.day(WEDNESDAY, "a\na\n")
        self.assertNotIn("に上げますか", out1)
        code, out2, err = self.day(THURSDAY, "a\na\ny\n")
        self.assertEqual(code, 0, err)
        self.assertIn("に上げますか", out2)
        self.assertEqual(self.progress()["langs"]["python"]["level"], 2)

    def test_44_level_up_no_restarts_count(self):
        """TC-CLI-44 | 正常系 | 「n」なら上がらず、連続の数え直しになる（次の日にすぐは再提案しない）

        入力：2日目の提案に「n」→3日目に全問正解
        期待：level は 1 のまま。3日目に提案は出ない
        根拠：決定事項 判断4（上げない選択のあと、毎日聞かない）
        """
        self.day(WEDNESDAY, "a\na\n")
        self.day(THURSDAY, "a\na\nn\n")
        self.assertEqual(self.progress()["langs"]["python"]["level"], 1)
        code, out3, err = self.day(FRIDAY, "a\na\n")
        self.assertNotIn("に上げますか", out3)

    def test_45_level_up_eof(self):
        """TC-CLI-45 | 異常系 | 提案への答えがないまま入力が終わっても、エラーにならず難易度は変わらない

        入力：提案が出る日に、問題への答えだけで入力を終える
        期待：終了コード0。level は 1 のまま
        根拠：自動実行（通知など）で入力がない場合を想定
        """
        self.day(WEDNESDAY, "a\na\n")
        code, out, err = self.day(THURSDAY, "a\na\n")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.progress()["langs"]["python"]["level"], 1)

    def test_46_no_level_up_when_wrong(self):
        """TC-CLI-46 | 正常系 | 不正解が1問でもあれば、提案は出ない

        入力：1日目 全問正解→2日目 1問不正解
        期待：「に上げますか」は出ない
        根拠：決定事項 判断4（全問正解の連続）
        """
        self.day(WEDNESDAY, "a\na\n")
        code, out, err = self.day(THURSDAY, "a\nz\n")
        self.assertNotIn("に上げますか", out)

    def test_47_level_up_flag(self):
        """TC-CLI-47 | 正常系 | --level-up で、問題を解かずに難易度を1つ上げられる

        入力：python drill.py --level-up python
        期待：終了コード0。level が 2。問題は出ない
        根拠：決定事項 判断4（--level-up）
        """
        code, out, err = self.run_drill(["--level-up", "python", "--date", WEDNESDAY], qdir=self.qdir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.progress()["langs"]["python"]["level"], 2)
        self.assertNotIn("--- 問1", out)

    def test_48_level_up_flag_default_language(self):
        """TC-CLI-48 | 正常系 | --level-up に言語を付けなくても、言語が1つなら、その言語が上がる

        入力：python drill.py --level-up（languages は python だけ）
        期待：python の level が 2
        根拠：1言語だけの使い方でも簡単に使えるように
        """
        code, out, err = self.run_drill(["--level-up", "--date", WEDNESDAY], qdir=self.qdir)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.progress()["langs"]["python"]["level"], 2)

    def test_49_level_up_flag_at_max(self):
        """TC-CLI-49 | 境界値 | すでに Lv5 なら「すでに最高」と表示し、変更しない

        入力：Lv5 の状態で --level-up python
        期待：終了コード0。「すでに最高」を表示。level は 5
        根拠：難易度は 1〜5
        """
        self.progress_path.parent.mkdir(parents=True)
        self.progress_path.write_text(
            '{"langs": {"python": {"unit": null, "level": 5, "round": 1, "since": ""}}, "pending": []}',
            encoding="utf-8",
        )
        code, out, err = self.run_drill(["--level-up", "python"], qdir=self.qdir)
        self.assertEqual(code, 0, err)
        self.assertIn("すでに最高", out)
        self.assertEqual(self.progress()["langs"]["python"]["level"], 5)

    def test_50_broken_progress(self):
        """TC-CLI-50 | 異常系 | progress.json が壊れていたら、エラーを表示して止まり、ファイルは上書きしない

        入力：壊れた progress.json
        期待：終了コード1。標準エラーに「エラー」。問題は出ない。ファイルの中身は元のまま
        根拠：壊れたまま黙って初期化すると、進み具合が消えるため
        """
        self.progress_path.parent.mkdir(parents=True)
        self.progress_path.write_text("{こわれた", encoding="utf-8")
        code, out, err = self.day(WEDNESDAY, "a\na\n")
        self.assertEqual(code, 1)
        self.assertIn("エラー", err)
        self.assertNotIn("--- 問1", out)
        self.assertEqual(self.progress_path.read_text(encoding="utf-8"), "{こわれた")

    def test_51_missing_pending_dropped(self):
        """TC-CLI-51 | 異常系 | 未回答の問題が問題集から無くなっていたら、お知らせして、通常の出題に進む

        入力：pending に存在しない問題id を書いた progress.json
        期待：終了コード0。「見つかりません」のお知らせ。通常どおり2問が出る。pending は空
        根拠：問題集を編集して問題を消した場合に、止まらないように
        """
        self.progress_path.parent.mkdir(parents=True)
        self.progress_path.write_text(
            '{"langs": {}, "pending": [{"lang": "python", "file": "u01.yaml", "qid": "gone"}]}',
            encoding="utf-8",
        )
        code, out, err = self.day(WEDNESDAY, "a\na\n")
        self.assertEqual(code, 0, err)
        self.assertIn("見つかりません", out)
        self.assertIn("今日は 2 問中 2 問正解でした。", out)
        self.assertEqual(self.progress()["pending"], [])

    def test_52_explicit_file_leaves_progress(self):
        """TC-CLI-52 | 正常系 | 問題集を指定して起動したときは、進み具合を作らず、変えない

        入力：python drill.py u01.yaml（ファイル指定）
        期待：終了コード0。progress.json は作られない
        根拠：設計方針（ファイル指定は、お試し・単発の用途）
        """
        path = self.qdir / "python" / "u01.yaml"
        code, out, err = self.run_drill([path], "a\na\n")
        self.assertEqual(code, 0, err)
        self.assertFalse(self.progress_path.exists())

    def test_53_sunday_keeps_pending(self):
        """TC-CLI-53 | 正常系 | 休みの日は未回答に手を付けず、次の学習日に出す

        入力：水曜に中断→日曜（休み）→翌月曜
        期待：日曜は「休み」で pending が1件のまま。月曜に未回答の1問が出る
        根拠：決定事項 判断1
        """
        self.day(WEDNESDAY, "a\n")
        code, out, err = self.day(SUNDAY, "")
        self.assertIn("休み", out)
        self.assertEqual(len(self.progress()["pending"]), 1)
        code, out, err = self.day(MONDAY_NEXT, "a\n")
        self.assertIn("前回の未回答の問題を出します（1問）", out)


class DefaultLocationTest(unittest.TestCase):
    def test_18_default_log_location(self):
        """TC-CLI-18 | 環境差 | 記録先の既定は、どこから起動しても drill.py の隣の data/log.csv になる

        入力：drill.py の既定の記録先（DEFAULT_LOG）を確認
        期待：絶対パスで、code-drill/data/log.csv
        根拠：現在地が違うと記録が散らばらないようにするため（不具合票 D-06 と同じ原因を防ぐ）
        """
        import drill

        self.assertTrue(drill.DEFAULT_LOG.is_absolute())
        self.assertEqual(drill.DEFAULT_LOG, ROOT / "data" / "log.csv")


if __name__ == "__main__":
    unittest.main()
