"""ウィンドウの画面（gui.py）の試験

実際にウィンドウを開き（作業環境では仮想の画面）、ボタンを押す・文字を入れる操作をプログラムで行って、
画面に出た文字・記録のファイルを確かめる。見た目（色・配置の美しさ）は確かめられないため、
利用者のPCで開いて確かめる（試験の対象外）。
tkinter が使えない環境や、画面が開けない環境では、このファイルの試験はスキップされる。
説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:  # tkinter が入っていない Python
    tk = None

import recorder
from tests.editions import paid_only

ROOT = Path(__file__).resolve().parent.parent
WEDNESDAY = date(2026, 10, 14)
THURSDAY = date(2026, 10, 15)
SUNDAY = date(2026, 10, 18)


def setUpModule():
    if tk is None:
        raise unittest.SkipTest("tkinter が使えません")
    try:
        root = tk.Tk()
        root.destroy()
    except tk.TclError as error:
        raise unittest.SkipTest(f"画面を開けません: {error}")
    sys.path.insert(0, str(ROOT))


def unit_yaml(*qids, kind="blank"):
    """答えがどれも「a」の問題集。kind が choice のときは選択式（正解は1番の「a」）。"""
    out = ""
    for qid in qids:
        out += f"- id: {qid}\n  unit: 単元\n  level: 1\n  type: {kind}\n  question: 問題{qid}\n  code: x = ___\n"
        if kind == "choice":
            out += "  choices: [a, b, c]\n"
        out += f"  answer: a\n  explanation: 解説{qid}\n"
    return out


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def all_text(root):
    """画面に出ている文字を、すべてつなげて返す。"""
    parts = []
    for w in walk(root):
        if not w.winfo_ismapped() and w is not root:
            continue
        if isinstance(w, tk.Text):
            parts.append(w.get("1.0", "end"))
        elif isinstance(w, (tk.Label, ttk.Label, tk.Button, ttk.Button, tk.Radiobutton, ttk.Radiobutton)):
            parts.append(str(w.cget("text")))
    return "\n".join(parts)


def buttons(root, text):
    return [
        w
        for w in walk(root)
        if isinstance(w, (tk.Button, ttk.Button)) and str(w.cget("text")) == text and w.winfo_ismapped()
    ]


def press(root, text):
    found = buttons(root, text)
    assert found, f"ボタン「{text}」が見つかりません。画面の文字:\n{all_text(root)}"
    found[0].invoke()
    root.update()


def entries(root):
    return [w for w in walk(root) if isinstance(w, (tk.Entry, ttk.Entry)) and w.winfo_ismapped()]


def radios(root):
    return [w for w in walk(root) if isinstance(w, (tk.Radiobutton, ttk.Radiobutton)) and w.winfo_ismapped()]


class GuiTestCase(unittest.TestCase):
    def setUp(self):
        import gui

        self.gui = gui
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.log_path = self.folder / "data" / "log.csv"
        self.progress_path = self.folder / "data" / "progress.json"
        self.config_path = self.folder / "config.yaml"
        self.qdir = self.folder / "questions"
        self.config_path.write_text("languages: [python]\nquestions_per_day: 2\n", encoding="utf-8")
        self.write_unit("python", "u01.yaml", "p-1", "p-2")
        self.write_unit("python", "u02.yaml", "p-3", "p-4")
        self._roots = []
        self.addCleanup(self._close_all)

    def _close_all(self):
        for root in self._roots:
            try:
                root.destroy()
            except tk.TclError:
                pass

    def write_unit(self, lang, name, *qids, kind="blank"):
        folder = self.qdir / lang
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(unit_yaml(*qids, kind=kind), encoding="utf-8")

    def open_app(self, today=WEDNESDAY, **changes):
        options = dict(
            questions_dir=self.qdir,
            log=self.log_path,
            config=self.config_path,
            progress=self.progress_path,
            today=today,
        )
        options.update(changes)
        root = tk.Tk()
        self._roots.append(root)
        app = self.gui.DrillApp(root, self.gui.Options(**options))
        root.update()
        return root, app

    def answer(self, root, text):
        """空欄式の問題に、文字を入れて「答える」を押す。"""
        box = entries(root)[0]
        box.delete(0, "end")
        box.insert(0, text)
        press(root, "答える")

    def qids(self):
        return [r["qid"] for r in recorder.read_log(self.log_path)]

    def saved_progress(self):
        return json.loads(self.progress_path.read_text(encoding="utf-8"))


class StartScreenTest(GuiTestCase):
    def test_01_start_screen(self):
        """TC-GUI-01 | 正常系 | 起動すると、開始の画面に「今日の学習」と「練習」の入り口と、使える言語が出る

        入力：python と sql の言語フォルダがある状態で起動
        期待：state が start。「今日の学習を始める」「練習を始める」のボタンがある。言語の選択欄に python と sql が並ぶ
        根拠：本人の希望（利用者が簡単に選べるように）。決定事項 GUIの決定
        """
        self.write_unit("sql", "s01.yaml", "s-1", "s-2")
        root, app = self.open_app()
        self.assertEqual(app.state, "start")
        self.assertTrue(buttons(root, "今日の学習を始める"))
        self.assertTrue(buttons(root, "練習を始める"))
        self.assertEqual(list(app.lang_box.cget("values")), ["python", "sql"])

    def test_02_language_changes_units(self):
        """TC-GUI-02 | 正常系 | 言語を選ぶと、単元の選択欄がその言語の問題集に切り替わる

        入力：言語欄で sql を選ぶ（sql は s01・s02、python は u01・u02）
        期待：単元欄が s01・s02 になる。python に戻すと u01・u02
        根拠：フォルダを足せば言語が増える設計（設計書 §4）
        """
        self.write_unit("sql", "s01.yaml", "s-1", "s-2")
        self.write_unit("sql", "s02.yaml", "s-3", "s-4")
        root, app = self.open_app()
        app.lang_box.set("sql")
        app.on_language_selected()
        self.assertEqual(list(app.unit_box.cget("values")), ["s01", "s02"])
        app.lang_box.set("python")
        app.on_language_selected()
        self.assertEqual(list(app.unit_box.cget("values")), ["u01", "u02"])

    def test_03_no_languages(self):
        """TC-GUI-03 | 異常系 | 問題集が1つもないときは、エラーの画面を出し、ウィンドウは落ちない

        入力：空の questions フォルダ
        期待：state が error。エラーの文章が画面に出る。例外は出ない
        根拠：フォルダの指定間違い・問題集の置き忘れ
        """
        for p in (self.qdir / "python").iterdir():
            p.unlink()
        root, app = self.open_app()
        self.assertEqual(app.state, "error")
        self.assertIn("言語", all_text(root))


class TodayFlowTest(GuiTestCase):
    def test_04_first_question_shown(self):
        """TC-GUI-04 | 正常系 | 「今日の学習を始める」で、今日の言語・単元と、1問目の問題文・コードが出る

        入力：初日（水曜）に「今日の学習を始める」
        期待：state が question。「単元：u01」「Lv1」と、問題文・コード「x = ___」が出る。空欄式なので入力欄が1つ
        根拠：drill.py と同じ内容を、ウィンドウで見せる
        """
        root, app = self.open_app()
        press(root, "今日の学習を始める")
        self.assertEqual(app.state, "question")
        text = all_text(root)
        for word in ("今日の言語：", "単元：u01", "Lv1", "x = ___", "問1"):
            self.assertIn(word, text)
        self.assertEqual(len(entries(root)), 1)

    def test_05_correct_answer(self):
        """TC-GUI-05 | 正常系 | 正解を入れて「答える」を押すと、「正解です！」と解説が出て、記録が1行増える

        入力：答えが「a」の問題に「a」
        期待：state が result。「正解です！」と「解説」が出る。記録に1行（correct=1）。「次の問題へ」のボタンが出る
        根拠：設計書 §5-7〜8
        """
        root, app = self.open_app()
        press(root, "今日の学習を始める")
        self.answer(root, "a")
        self.assertEqual(app.state, "result")
        text = all_text(root)
        self.assertIn("正解です！", text)
        self.assertIn("解説", text)
        self.assertTrue(buttons(root, "次の問題へ"))
        rows = recorder.read_log(self.log_path)
        self.assertEqual([r["correct"] for r in rows], ["1"])

    def test_06_wrong_answer(self):
        """TC-GUI-06 | 正常系 | 間違いを入れると、正解を見せ、記録は不正解になる

        入力：答えが「a」の問題に「z」
        期待：「不正解です。正解は「a」です。」が出る。記録の correct は 0
        根拠：drill.py と同じ表示
        """
        root, app = self.open_app()
        press(root, "今日の学習を始める")
        self.answer(root, "z")
        self.assertIn("不正解です。正解は「a」です。", all_text(root))
        self.assertEqual([r["correct"] for r in recorder.read_log(self.log_path)], ["0"])

    def test_07_fullwidth_and_empty(self):
        """TC-GUI-07 | 環境差 | 全角で答えても正解になる。何も入れずに「答える」を押すと不正解になる

        入力：1問目に全角の「ａ」、2問目に空
        期待：1問目は正解、2問目は不正解（drill.py と同じ採点）
        根拠：不具合 D-01 の再発防止。採点は session.py の部品なので画面でも同じ
        """
        root, app = self.open_app()
        press(root, "今日の学習を始める")
        self.answer(root, "ａ")
        press(root, "次の問題へ")
        press(root, "答える")
        self.assertEqual([r["correct"] for r in recorder.read_log(self.log_path)], ["1", "0"])

    def test_08_choice_question(self):
        """TC-GUI-08 | 正常系 | 選択式の問題は選択肢が並び、選んで「答える」を押すと採点される

        入力：選択肢 a・b・c（正解は a）の問題で、1番目を選ぶ／別の問題で2番目を選ぶ
        期待：選択肢のボタンが3つ。1番目は正解、2番目は不正解
        根拠：設計書 §4（選択式は番号で選ぶ。画面では選択肢を選ぶ）
        """
        self.write_unit("python", "u01.yaml", "c-1", "c-2", kind="choice")
        root, app = self.open_app()
        press(root, "今日の学習を始める")
        self.assertEqual(len(radios(root)), 3)
        radios(root)[0].invoke()
        press(root, "答える")
        self.assertIn("正解です！", all_text(root))
        press(root, "次の問題へ")
        radios(root)[1].invoke()
        press(root, "答える")
        self.assertIn("不正解です", all_text(root))

    def test_09_full_day_summary(self):
        """TC-GUI-09 | 正常系 | 2問とも答えると、最後に「2 問中 2 問正解でした。」と記録先が出る

        入力：2問に「a」「a」
        期待：state が finished。「今日は 2 問中 2 問正解でした。」と「結果を記録しました」。最後の問題の次のボタンは「結果を見る」
        根拠：設計書 §5-7
        """
        root, app = self.open_app()
        press(root, "今日の学習を始める")
        self.answer(root, "a")
        press(root, "次の問題へ")
        self.answer(root, "a")
        self.assertTrue(buttons(root, "結果を見る"))
        press(root, "結果を見る")
        self.assertEqual(app.state, "finished")
        text = all_text(root)
        self.assertIn("今日は 2 問中 2 問正解でした。", text)
        self.assertIn("結果を記録しました", text)

    def test_10_double_press_records_once(self):
        """TC-GUI-10 | 境界値 | 「答える」を続けて押しても、1問につき1回しか記録されない

        入力：「答える」を2回押す
        期待：記録は1行。2回目のボタンは押せない（または何も起きない）
        根拠：ダブルクリックで二重に記録されないため
        """
        root, app = self.open_app()
        press(root, "今日の学習を始める")
        box = entries(root)[0]
        box.insert(0, "a")
        button = buttons(root, "答える")[0]
        button.invoke()
        root.update()
        try:
            button.invoke()
        except tk.TclError:
            pass
        root.update()
        self.assertEqual(len(recorder.read_log(self.log_path)), 1)

    def test_11_rest_day(self):
        """TC-GUI-11 | 正常系 | 休みの日は、休みの案内だけが出て、問題は出ない

        入力：日曜に「今日の学習を始める」
        期待：state が rest。「休み」が出る。問題の入力欄はない。記録ファイルは作られない
        根拠：設計書 §5-2
        """
        root, app = self.open_app(today=SUNDAY)
        press(root, "今日の学習を始める")
        self.assertEqual(app.state, "rest")
        self.assertIn("休み", all_text(root))
        self.assertEqual(entries(root), [])
        self.assertFalse(self.log_path.exists())

    def test_12_close_midway_leaves_pending(self):
        """TC-GUI-12 | 異常系 | 途中でウィンドウを閉じると、答えていない問題が未回答として残り、翌日はそれだけが出る

        入力：1問だけ答えてウィンドウを閉じる→翌日に新しく開いて「今日の学習を始める」
        期待：未回答が1件。翌日は「前回の未回答の問題を出します（1問）。」が出て、問題は1問だけ
        根拠：決定事項 判断1（文字の画面と同じ動き。TC-CLI-38・39）
        """
        root, app = self.open_app()
        press(root, "今日の学習を始める")
        self.answer(root, "a")
        root.destroy()
        self.assertEqual(len(self.saved_progress()["pending"]), 1)
        root2, app2 = self.open_app(today=THURSDAY)
        press(root2, "今日の学習を始める")
        self.assertIn("前回の未回答の問題を出します（1問）。", all_text(root2))
        self.answer(root2, "a")
        self.assertEqual(len(self.saved_progress()["pending"]), 0)
        self.assertEqual(len(set(self.qids())), 2)


class LevelUpTest(GuiTestCase):
    def play_day(self, day, then=None):
        root, app = self.open_app(today=day)
        press(root, "今日の学習を始める")
        self.answer(root, "a")
        press(root, "次の問題へ")
        self.answer(root, "a")
        press(root, "結果を見る")
        return root, app

    def test_13_level_up_offer_accept(self):
        """TC-GUI-13 | 正常系 | 2日連続で全問正解だと、最後に難易度の提案が出て、「上げる」で1つ上がる

        入力：1日目 全問正解（提案なし）→2日目 全問正解→「上げる」
        期待：1日目は「に上げますか」が出ない。2日目に出る。押すと progress.json の level が 2
        根拠：決定事項 判断4（文字の画面と同じ動き。TC-CLI-43）
        """
        root1, _ = self.play_day(WEDNESDAY)
        self.assertNotIn("に上げますか", all_text(root1))
        root1.destroy()
        root2, app2 = self.play_day(THURSDAY)
        self.assertIn("に上げますか", all_text(root2))
        press(root2, "上げる")
        self.assertEqual(self.saved_progress()["langs"]["python"]["level"], 2)
        self.assertIn("Lv2", all_text(root2))

    def test_14_level_up_offer_decline(self):
        """TC-GUI-14 | 正常系 | 「上げない」を押すと難易度は変わらず、連続の数え直しになる

        入力：提案に「上げない」
        期待：level は 1 のまま。since が今日（2026-10-15）になる
        根拠：決定事項 判断4（TC-CLI-44）
        """
        root1, _ = self.play_day(WEDNESDAY)
        root1.destroy()
        root2, _ = self.play_day(THURSDAY)
        press(root2, "上げない")
        langs = self.saved_progress()["langs"]["python"]
        self.assertEqual((langs["level"], langs["since"]), (1, "2026-10-15"))


class PracticeTest(GuiTestCase):
    def test_15_practice(self):
        """TC-GUI-15 | 正常系 | 言語と単元を選んで練習すると、その単元の問題が出て、進み具合は作られない

        入力：言語 python・単元 u02 を選んで「練習を始める」。2問に「a」「a」
        期待：出る問題は p-3・p-4（u02）。記録の lang は python。progress.json は作られない
        根拠：問題集を指定した起動と同じ扱い（TC-CLI-52）
        """
        root, app = self.open_app()
        app.lang_box.set("python")
        app.on_language_selected()
        app.unit_box.set("u02")
        press(root, "練習を始める")
        self.assertEqual(app.state, "question")
        self.answer(root, "a")
        press(root, "次の問題へ")
        self.answer(root, "a")
        self.assertEqual(set(self.qids()), {"p-3", "p-4"})
        self.assertFalse(self.progress_path.exists())

    def test_16_practice_on_sunday(self):
        """TC-GUI-16 | 境界値 | 練習は日曜でも出題される

        入力：日曜に練習を始める
        期待：問題が出る（休みにならない）
        根拠：問題集を指定した起動は日程を見ない（TC-CLI-23）
        """
        root, app = self.open_app(today=SUNDAY)
        app.lang_box.set("python")
        app.on_language_selected()
        app.unit_box.set("u01")
        press(root, "練習を始める")
        self.assertEqual(app.state, "question")


class ErrorTest(GuiTestCase):
    def test_17_broken_config(self):
        """TC-GUI-17 | 異常系 | 設定ファイルが正しくないときは、エラーの画面を出す（ウィンドウは落ちない）

        入力：days に正しくない曜日名を書いた設定
        期待：state が error。画面に「days」を含むエラー。問題は出ない
        根拠：TC-CLI-27。Traceback にしない
        """
        self.config_path.write_text("days: [mon, funday]\n", encoding="utf-8")
        root, app = self.open_app()
        self.assertEqual(app.state, "error")
        self.assertIn("days", all_text(root))

    def test_18_broken_question_file(self):
        """TC-GUI-18 | 異常系 | 問題集に誤りがあるときは、出題せずにエラーの画面を出す

        入力：level が 9 の問題を含む単元
        期待：今日の学習を始めると state が error。「--check」の案内が出る。入力欄はない
        根拠：不具合 D-08 の対応（出題の前の検査）。TC-CLI-11・36
        """
        (self.qdir / "python" / "u01.yaml").write_text(
            unit_yaml("p-1").replace("level: 1", "level: 9"), encoding="utf-8"
        )
        root, app = self.open_app()
        press(root, "今日の学習を始める")
        self.assertEqual(app.state, "error")
        self.assertIn("--check", all_text(root))
        self.assertEqual(entries(root), [])

    def test_19_log_not_writable(self):
        """TC-GUI-19 | 環境差 | 記録先に書き込めないときは、問題を出す前にエラーの画面を出す

        入力：記録先がフォルダ
        期待：今日の学習を始めると state が error。問題は出ない
        根拠：答えたあとで記録できないと入力が無駄になるため（TC-CLI-16・17・30）
        """
        root, app = self.open_app(log=self.folder)
        press(root, "今日の学習を始める")
        self.assertEqual(app.state, "error")
        self.assertEqual(entries(root), [])
        self.assertIn("記録", all_text(root))

    def test_22_log_locked_by_other_software(self):
        """TC-GUI-22 | 環境差 | 記録ファイルを別のソフト（Excel など）が開いていて書けないときは、問題を出す前に「閉じて」と案内するエラーの画面を出す

        入力：記録ファイルの書き込み確認が、閉じるよう伝える LogFileError になる状態（Windows の「開いているファイル」を、作り出して再現）
        期待：「今日の学習を始める」で state が error。「閉じて」が画面に出る。問題は出ない
        根拠：Linux では再現できないため、書き込みの失敗を作り出して確かめる（単体は TC-REC-16・17、画面側のつなぎ込みの確認）
        """
        from unittest import mock

        from recorder import LogFileError

        root, app = self.open_app()
        error = LogFileError("記録ファイルに書き込めません。Excel などで開いている場合は、閉じてから、もう一度実行してください。")
        with mock.patch("gui.check_writable", side_effect=error):
            press(root, "今日の学習を始める")
        self.assertEqual(app.state, "error")
        self.assertIn("閉じて", all_text(root))
        self.assertEqual(entries(root), [])

    def test_20_error_has_back_button(self):
        """TC-GUI-20 | 正常系 | エラーの画面から「最初に戻る」で、開始の画面に戻れる

        入力：エラーの画面で「最初に戻る」
        期待：state が start
        根拠：設定を直したあと、ウィンドウを開き直さなくてよいように
        """
        (self.qdir / "python" / "u01.yaml").write_text("", encoding="utf-8")
        root, app = self.open_app()
        press(root, "今日の学習を始める")
        self.assertEqual(app.state, "error")
        press(root, "最初に戻る")
        self.assertEqual(app.state, "start")


class LaunchTest(unittest.TestCase):
    def test_21_help_without_window(self):
        """TC-GUI-21 | 環境差 | `python gui.py --help` は、ウィンドウを開かずに使い方を表示して終了する

        入力：python gui.py --help
        期待：終了コード0。「--log」などの指定が書かれている
        根拠：画面のない環境（ssh など）でも、使い方を確かめられるように
        """
        p = subprocess.run(
            [sys.executable, str(ROOT / "gui.py"), "--help"], capture_output=True, text=True, timeout=30
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("--log", p.stdout)


if __name__ == "__main__":
    unittest.main()


class ExtrasTest(GuiTestCase):
    """もう1問・難易度を下げる・Git案内（段階9-2）。"""

    def play(self, day):
        root, app = self.open_app(today=day)
        press(root, "今日の学習を始める")
        self.answer(root, "a")
        press(root, "次の問題へ")
        self.answer(root, "a")
        press(root, "結果を見る")
        return root, app

    def test_23_one_more_question(self):
        """TC-GUI-23 | 正常系 | 結果の画面に「もう1問」があり、押すと1問出て、「追加」のメモ付きで記録される。何回でも続けられる

        入力：2問に答えたあと「もう1問」→答える→結果の画面でもう一度「もう1問」→答える
        期待：記録が3行→4行。3行目以降の note が「追加」。結果の画面に「追加の 1 問を記録しました」。進み具合の pending は空
        根拠：Claude 版の決まり9（「もう1問」で続けられる。何回でも）。文字の画面と同じ動き（TC-EXT-05）
        """
        root, app = self.play(WEDNESDAY)
        press(root, "もう1問")
        self.assertEqual(app.state, "question")
        self.answer(root, "a")
        press(root, "結果を見る")
        self.assertIn("追加の 1 問を記録しました", all_text(root))
        press(root, "もう1問")
        self.answer(root, "a")
        press(root, "結果を見る")
        rows = recorder.read_log(self.log_path)
        self.assertEqual(len(rows), 4)
        self.assertEqual([r["note"] for r in rows], ["", "", "追加", "追加"])
        self.assertEqual(self.saved_progress()["pending"], [])

    def test_24_extra_button_on_rest_day_and_practice(self):
        """TC-GUI-24 | 境界値 | 休みの日と、練習のあとでも、「もう1問」のボタンを出す（2026-10-18に変更。以前は出さなかった）

        入力：日曜に「今日の学習を始める」／練習で2問に答える
        期待：どちらの画面にも「もう1問」がある
        根拠：本人の指摘（日曜や練習で試して、ボタンが出ないと思った）。文字の画面は、入力待ちで通知からの起動を止めないよう、これまでどおり聞かない（TC-EXT-07）
        """
        root, app = self.open_app(today=SUNDAY)
        press(root, "今日の学習を始める")
        self.assertTrue(buttons(root, "もう1問"))
        root.destroy()
        root, app = self.open_app()
        press(root, "練習を始める")
        self.answer(root, "a")
        press(root, "次の問題へ")
        self.answer(root, "a")
        press(root, "結果を見る")
        self.assertTrue(buttons(root, "もう1問"))

    def test_25_git_notice_when_unit_is_finished(self):
        """TC-GUI-25 | 正常系 | 単元を出し終えた日の結果の画面に、Git に保存する案内が出る。途中では出ない

        入力：u01（p-1, p-2）を1日で解き終える
        期待：結果の画面に「git commit」と「u01」がある
        根拠：Claude 版の解説のルール7。文字の画面と同じ（TC-EXT-08）
        """
        root, app = self.play(WEDNESDAY)
        text = all_text(root)
        self.assertIn("git commit", text)
        self.assertIn("u01", text)

    def test_26_level_down_button(self):
        """TC-GUI-26 | 正常系 | 「難易度を下げる」で、難易度が1つ下がる。Lv1 では「すでに最低」と出る

        入力：2日続けて全問正解→「上げる」で Lv2→「難易度を下げる」→もう一度「難易度を下げる」
        期待：level が 1 になり「Lv2 から Lv1」と出る。もう一度では「すでに最低」
        根拠：Claude 版の決まり3（難易度の選択：やさしく）。TC-EXT-10・11
        """
        root1, _ = self.play(WEDNESDAY)
        root1.destroy()
        root2, _ = self.play(THURSDAY)
        press(root2, "上げる")
        self.assertEqual(self.saved_progress()["langs"]["python"]["level"], 2)
        press(root2, "難易度を下げる")
        self.assertEqual(self.saved_progress()["langs"]["python"]["level"], 1)
        self.assertIn("Lv2 から Lv1", all_text(root2))
        press(root2, "難易度を下げる")
        self.assertIn("すでに最低", all_text(root2))

    @paid_only
    def test_27_character_lines(self):
        """TC-GUI-27 | 正常系 | 出題の冒頭と結果の画面に、キャラのひとことと、今日もらった称号が出る

        入力：初日に2問に答える
        期待：結果の画面に「くりまんじゅう後輩：」と「はじめの一歩」。characters を空にすると出ない
        根拠：文字の画面と同じ（TC-FUN-19・20）
        """
        root, app = self.play(WEDNESDAY)
        text = all_text(root)
        self.assertIn("くりまんじゅう後輩：", text)
        self.assertIn("はじめの一歩", text)
        root.destroy()
        self.log_path.unlink()
        self.progress_path.unlink()
        self.config_path.write_text("languages: [python]\ncharacters: {}\n", encoding="utf-8")
        root, app = self.play(WEDNESDAY)
        self.assertNotIn("くりまんじゅう後輩", all_text(root))


class CompanionScreenTest(GuiTestCase):
    """キャラとすごろくを各画面に出す・休みの日と練習のあとでも「もう1問」「難易度」（段階10）。"""

    def set_level(self, level):
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        self.progress_path.write_text(
            json.dumps({"langs": {"python": {"level": level, "unit": "u01.yaml", "round": 1}}, "pending": []}),
            encoding="utf-8",
        )

    @paid_only
    def test_28_board_and_character_on_every_screen(self):
        """TC-GUI-28 | 正常系 | 開始・出題・結果の各画面に、キャラ（名前・Lv・すがた）とすごろくの盤面が出る

        入力：起動／「今日の学習を始める」／2問に答えて結果の画面
        期待：どの画面にも「くりまんじゅう後輩」と「📍 u01」。出題の画面に「Lv1」「いつものすがた」。結果の画面に「✅ u01」
        根拠：本人の指摘（すごろくもキャラも出ない）。TC-CMP-04・07・08（ブラウザ版）と同じ
        """
        root, app = self.open_app()
        text = all_text(root)
        self.assertIn("くりまんじゅう後輩", text)
        self.assertIn("📍 u01", text)
        press(root, "今日の学習を始める")
        text = all_text(root)
        for part in ("くりまんじゅう後輩", "Lv1", "いつものすがた", "📍 u01"):
            self.assertIn(part, text)
        self.answer(root, "a")
        press(root, "次の問題へ")
        self.answer(root, "a")
        press(root, "結果を見る")
        text = all_text(root)
        self.assertIn("くりまんじゅう後輩", text)
        self.assertIn("✅ u01", text)

    @paid_only
    def test_29_rest_day_screen(self):
        """TC-GUI-29 | 正常系 | 休みの日の画面に、キャラとすごろくと「もう1問」が出る。押すと問題が出て、「追加」のメモ付きで記録される。「難易度を下げる」も使える

        入力：難易度2で日曜に「今日の学習を始める」→「難易度を下げる」→「もう1問」→答える
        期待：休みの画面に「休み」「くりまんじゅう後輩」「📍 u01」「もう1問」「難易度を下げる」。level が 1 になる。答えると記録は1行で note は「追加」
        根拠：本人の指摘（日曜に試して、何も出なかった）。TC-CMP-11・15（ブラウザ版）と同じ
        """
        self.set_level(2)
        root, app = self.open_app(today=SUNDAY)
        press(root, "今日の学習を始める")
        text = all_text(root)
        for part in ("休み", "くりまんじゅう後輩", "📍 u01", "もう1問", "難易度を下げる"):
            self.assertIn(part, text)
        press(root, "難易度を下げる")
        self.assertEqual(self.saved_progress()["langs"]["python"]["level"], 1)
        self.assertIn("Lv2 から Lv1", all_text(root))
        press(root, "もう1問")
        self.answer(root, "a")
        press(root, "結果を見る")
        self.assertEqual([r["note"] for r in recorder.read_log(self.log_path)], ["追加"])

    @paid_only
    def test_30_after_practice(self):
        """TC-GUI-30 | 正常系 | 練習のあとの結果の画面にも、キャラ・すごろく・「もう1問」・「難易度を下げる」が出る

        入力：練習で u01 を2問解く
        期待：結果の画面に「くりまんじゅう後輩」「📍」「もう1問」「難易度を下げる」
        根拠：本人の指摘（練習で試して、何も出なかった）。TC-CMP-13（ブラウザ版）と同じ
        """
        self.set_level(2)
        root, app = self.open_app()
        app.lang_box.set("python")
        app.on_language_selected()
        app.unit_box.set("u01")
        press(root, "練習を始める")
        self.answer(root, "a")
        press(root, "次の問題へ")
        self.answer(root, "a")
        press(root, "結果を見る")
        text = all_text(root)
        for part in ("くりまんじゅう後輩", "📍", "もう1問", "難易度を下げる"):
            self.assertIn(part, text)

    @paid_only
    def test_31_portrait_in_window(self):
        """TC-GUI-31 | 正常系 | 出題・休み・結果の各画面に、くりまんじゅう後輩のイラスト（画像）が出る。くりまんじゅう後輩以外のキャラは絵文字のまま

        入力：出題の画面／日曜の休みの画面／2問解いた結果の画面。キャラを「ことりくん」にした設定
        期待：どの画面にも、画像つきの部品（Label）が1つある。ことりくんのときは、画像つきの部品がなく、絵文字が出る
        根拠：本人の希望（絵文字ではなく、ちゃんと描いて）。ブラウザ版（TC-ART-08・09）と同じ。画像は tkinter の標準の部品（PhotoImage）で読める PNG
        """

        def pictures(root):
            return [w for w in walk(root) if isinstance(w, (tk.Label, ttk.Label)) and str(w.cget("image")) and w.winfo_ismapped()]

        root, app = self.open_app()
        press(root, "今日の学習を始める")
        self.assertEqual(len(pictures(root)), 1)
        self.answer(root, "a")
        press(root, "次の問題へ")
        self.answer(root, "a")
        press(root, "結果を見る")
        self.assertEqual(len(pictures(root)), 1)
        root.destroy()
        root, app = self.open_app(today=SUNDAY)
        press(root, "今日の学習を始める")
        self.assertEqual(len(pictures(root)), 1)
        root.destroy()
        self.config_path.write_text("languages: [python]\ncharacters: {python: ことりくん}\n", encoding="utf-8")
        self.log_path.unlink(missing_ok=True)
        self.progress_path.unlink(missing_ok=True)
        root, app = self.open_app()
        press(root, "今日の学習を始める")
        self.assertEqual(len(pictures(root)), 0)
        self.assertIn("ことりくん", all_text(root))

    def test_32_nothing_is_cut_off(self):
        """TC-GUI-32 | 境界値 | イラストが入っても、どの画面でも、ボタンがウィンドウの下にはみ出さない

        入力：出題の画面／2問解いた結果の画面（Git の案内・称号・すごろくも出る）／日曜の休みの画面
        期待：すべてのボタンが、ウィンドウの中に収まる（下の端がウィンドウの下の端より上）
        根拠：イラストを足すと画面が縦に長くなり、ボタンが見えなくなる恐れがあるため（作業中に実際に起きた：TC-GUI-26 が検出）
        """

        def inside(root):
            root.update()
            bottom = root.winfo_rooty() + root.winfo_height()
            found = [w for w in walk(root) if isinstance(w, (tk.Button, ttk.Button)) and w.winfo_ismapped()]
            self.assertTrue(found)
            for w in found:
                self.assertLessEqual(w.winfo_rooty() + w.winfo_height(), bottom, str(w.cget("text")))

        root, app = self.open_app()
        press(root, "今日の学習を始める")
        inside(root)
        self.answer(root, "a")
        press(root, "次の問題へ")
        self.answer(root, "a")
        press(root, "結果を見る")
        inside(root)
        root.destroy()
        root, app = self.open_app(today=SUNDAY)
        press(root, "今日の学習を始める")
        inside(root)
