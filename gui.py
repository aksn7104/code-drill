"""code-drill 段階6-4：ウィンドウの画面（tkinter）

使い方：
    python gui.py                       # ウィンドウを開く（開始の画面から「今日の学習」か「練習」を選ぶ）
    python gui.py --date 2026-10-14     # 「今日」の日付を指定する（試験や確認用）
    python gui.py --help                # 指定できる項目を表示する（ウィンドウは開かない）

学習の流れ（今日の計画・採点・記録・難易度の提案）は session.py に任せていて、
このファイルが受け持つのは、ウィンドウに「見せる」ことと、ボタンや入力を受けることだけ。
文字の画面（drill.py）と同じ部品を呼ぶので、同じ動きになる。
"""

import argparse
import sys
from collections import namedtuple
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:  # tkinter が入っていない Python
    tk = None
    ttk = None

from config import ConfigError, load_config
from drill import DEFAULT_CONFIG, DEFAULT_LOG, DEFAULT_PROGRESS, QUESTIONS_DIR, parse_date
from loader import QuestionFileError
from progress import ProgressError, load_progress
from recorder import LogFileError, check_log, check_writable, read_log
from session import (
    LEGEND,
    Session,
    SessionError,
    apply_level_up,
    companion,
    farewell,
    level_down_now,
    level_up_offer,
    plan_extra,
    plan_file,
    plan_scheduled,
    rest_language,
    summary_lines,
    unit_done_notice,
)
from timetable import ScheduleError, find_languages, unit_files

# ウィンドウの設定。today は「今日」の日付（試験や確認用に指定できる）
Options = namedtuple("Options", "questions_dir log config progress today")

# 使い手に伝えるべき問題（drill.py が「エラー：…」にしているもの）。ウィンドウでは、エラーの画面にする
HANDLED_ERRORS = (ConfigError, QuestionFileError, LogFileError, ScheduleError, ProgressError, SessionError)

WRAP = 660  # 文章を折り返す幅（ピクセル）

# キャラのイラスト（PNG）の置き場所
ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "characters"


class DrillApp:
    """ウィンドウ全体。画面（state）は start → question → result → … → finished と進む。

    state：start（開始）/ question（出題中）/ result（採点後）/ rest（休み）/ finished（結果）/ error（エラー）
    """

    def __init__(self, root, options):
        self.root = root
        self.options = options
        self.config = None
        self.plan = None
        self.session = None
        self.state = ""
        self.frame = None
        self._photos = []
        self.lang_box = None
        self.unit_box = None
        self._answered = False
        self._units = {}
        root.title("code-drill")
        root.geometry("760x700")
        self.show_start()

    # ----- 画面の共通の部品 -----

    def _reset(self):
        """今の画面を消して、新しい画面の入れ物を作る。"""
        if self.frame is not None:
            self.frame.destroy()
        self.frame = ttk.Frame(self.root, padding=16)
        self.frame.pack(fill="both", expand=True)
        self._photos = []
        self.lang_box = self.unit_box = None
        return self.frame

    def _label(self, text, **options):
        label = ttk.Label(self.frame, text=text, wraplength=WRAP, justify="left", **options)
        label.pack(anchor="w", pady=(0, 8))
        return label

    def _button(self, text, command):
        button = ttk.Button(self.frame, text=text, command=command)
        button.pack(anchor="w", pady=4)
        return button

    def _lang(self):
        """今の言語。休みの日の計画には言語がないので、平日と同じ決め方で選ぶ。"""
        if self.plan.lang:
            return self.plan.lang
        if self.plan.entries:
            return self.plan.entries[-1]["lang"]
        return rest_language(self.config, self.options.questions_dir, self.options.log, self.options.today)

    def _companion(self, lang):
        return companion(
            self.config, lang, self.options.questions_dir, self.options.log, self.options.progress, self.options.today
        )

    def _photo(self, c, shrink=1):
        """キャラのイラスト（PhotoImage）。ないとき・読めないときは None（絵文字を使う）。shrink 分の1に小さくする。"""
        if not c["portrait_png"]:
            return None
        try:
            photo = tk.PhotoImage(file=str(ASSETS_DIR / c["portrait_png"]))
            if shrink > 1:
                photo = photo.subsample(shrink)
        except (tk.TclError, OSError):
            return None
        self._photos.append(photo)  # 参照を持っておかないと、画面から消えてしまう
        return photo

    def _character_line(self, c, say=False, art=True):
        """キャラの文字（名前・Lv・すがた・次のすがた。イラストがないときは先頭に絵文字）。キャラなしのときは空。"""
        if not c["name"]:
            return ""
        head = f"{c['avatar']} " if art else ""
        text = f"{head}{c['name']}　Lv{c['level']}　すがた：{c['form']}　次のすがた：{c['next_form']}"
        return f"{text}\n「{c['say']}」" if say and c["say"] else text

    def _show_character(self, c, say=False, color=None, shrink=1):
        """キャラを出す。イラストがあれば、イラストの横に文字を並べる（shrink 分の1の大きさ）。"""
        photo = self._photo(c, shrink=shrink)
        text = self._character_line(c, say=say, art=photo is None)
        if photo is None:
            if text:
                self._label(text, **({"foreground": color} if color else {}))
            return
        row = ttk.Frame(self.frame)
        row.pack(anchor="w", pady=(0, 8))
        ttk.Label(row, image=photo).pack(side="left", padx=(0, 12))
        options = {"foreground": color} if color else {}
        ttk.Label(row, text=text, wraplength=WRAP - 160 // shrink, justify="left", **options).pack(side="left", anchor="n")

    def _show_board(self, c):
        """すごろくの盤面を出す。"""
        if c["squares"]:
            self._label(c["board"], font=("TkDefaultFont", 11))
            self._label(LEGEND, foreground="#777777")

    # ----- 開始の画面 -----

    def show_start(self):
        """開始の画面：今日の学習／言語と単元を選んで練習。"""
        self._reset()
        self.state = "start"
        try:
            self.config = load_config(self.options.config)
            languages = find_languages(self.options.questions_dir)
            if not languages:
                raise SessionError(f"問題集のある言語フォルダが見つかりません: {self.options.questions_dir}")
        except HANDLED_ERRORS as error:
            self.show_error(error)
            return
        self._label("code-drill　コード学習", font=("TkDefaultFont", 16, "bold"))
        self._button("今日の学習を始める", self.start_today)
        shown = False
        for name in languages:
            try:
                c = self._companion(name)
            except HANDLED_ERRORS:
                continue  # 飾りの部分。記録や設定の誤りは、学習を始めるときに知らせる
            if c["name"] or c["squares"]:
                photo = self._photo(c, shrink=2)
                who = self._character_line(c, art=photo is None) if c["name"] else ""
                text = f"{name}　{who}".rstrip() + "\n" + c["board"]
                if photo is None:
                    self._label(text)
                else:
                    row = ttk.Frame(self.frame)
                    row.pack(anchor="w", pady=(0, 8))
                    ttk.Label(row, image=photo).pack(side="left", padx=(0, 12))
                    ttk.Label(row, text=text, wraplength=WRAP - 90, justify="left").pack(side="left", anchor="n")
                shown = True
        if shown:
            self._label(LEGEND, foreground="#777777")
        ttk.Separator(self.frame).pack(fill="x", pady=12)
        self._label("練習（言語と単元を選ぶ。進み具合は変わりません）")
        self.lang_box = ttk.Combobox(self.frame, state="readonly", values=languages, width=30)
        self.lang_box.pack(anchor="w", pady=4)
        self.lang_box.bind("<<ComboboxSelected>>", lambda event: self.on_language_selected())
        self.unit_box = ttk.Combobox(self.frame, state="readonly", values=[], width=30)
        self.unit_box.pack(anchor="w", pady=4)
        self._button("練習を始める", self.start_practice)
        self.lang_box.set(languages[0])
        self.on_language_selected()

    def on_language_selected(self):
        """言語を選んだら、その言語の単元（問題集）を単元の欄に並べる。"""
        try:
            files = unit_files(self.options.questions_dir, self.lang_box.get())
        except ScheduleError:
            files = []
        self._units = {f.stem: f for f in files}
        self.unit_box.configure(values=list(self._units))
        self.unit_box.set(next(iter(self._units), ""))

    # ----- 出題の始まり -----

    def _prepare(self):
        """始める前の確認（設定・記録ファイル）。読めないとき・書けないときは、エラーの画面にして False を返す。"""
        try:
            self.config = load_config(self.options.config)
            check_log(self.options.log)
            check_writable(self.options.log)  # 答えたあとで記録できないと困るので、始める前に確かめる
        except HANDLED_ERRORS as error:
            self.show_error(error)
            return False
        return True

    def start_today(self):
        """今日の学習：休み／未回答／今日の分を決めて、出題を始める。"""
        if not self._prepare():
            return
        try:
            plan = plan_scheduled(
                self.config, self.options.questions_dir, self.options.log, self.options.progress, self.options.today
            )
        except HANDLED_ERRORS as error:
            self.show_error(error)
            return
        self.plan = plan
        if plan.kind == "rest":
            self.show_rest()
            return
        self._open_session()

    def show_rest(self, notice=None):
        """休みの画面。キャラとすごろくを出し、やりたい日は1問できる（もう1問）。難易度も下げられる。"""
        self._reset()
        self.state = "rest"
        self._label("\n".join(self.plan.intro))
        if notice:
            self._label(notice)
        try:
            c = self._companion(self._lang())
        except HANDLED_ERRORS as error:
            self.show_error(error)
            return
        self._show_character(c, shrink=2)
        self._show_board(c)
        self._label("やりたい日は、1問だけ解けます。")
        self._button("もう1問", self.start_extra)
        self._button("難易度を下げる", self.answer_level_down)
        self._button("最初に戻る", self.show_start)

    def start_practice(self):
        """練習：選んだ単元の問題集から、ランダムに選んで出題する（進み具合は使わない）。"""
        path = self._units.get(self.unit_box.get())
        if path is None:
            self.show_error("練習する単元を選んでください")
            return
        if not self._prepare():
            return
        try:
            self.plan = plan_file(path, self.config)
        except HANDLED_ERRORS as error:
            self.show_error(error)
            return
        self._open_session()

    def _open_session(self):
        plan = self.plan
        self.session = Session(plan.entries, self.options.log, self.options.today, plan.progress, self.options.progress)
        self.show_question()

    # ----- 出題と採点 -----

    def show_question(self):
        session = self.session
        entry = session.current
        q = entry["q"]
        self._reset()
        self.state = "question"
        self._answered = False
        intro = "\n".join(self.plan.intro).strip()
        if intro:
            self._label(intro, foreground="#555555")
        try:
            c = self._companion(entry["lang"])
        except HANDLED_ERRORS as error:
            self.show_error(error)
            return
        self._show_character(c, say=True, color="#2f6b4f")
        self._label(
            f"問{session.number} / {session.total}　[{q['id']}]　Lv{q['level']}　{q['unit']}",
            font=("TkDefaultFont", 12, "bold"),
        )
        self._label(q["question"])
        code = ttk.Label(self.frame, text=q["code"].rstrip(), font="TkFixedFont", justify="left")
        code.pack(anchor="w", pady=(0, 8))
        self.choice_var = tk.StringVar(value="")
        self.entry = None
        self.choices = []
        if q["type"] == "choice":
            for number, text in enumerate(q["choices"], start=1):
                radio = ttk.Radiobutton(self.frame, text=text, value=str(number), variable=self.choice_var)
                radio.pack(anchor="w")
                self.choices.append(radio)
        else:
            self.entry = ttk.Entry(self.frame, width=40)
            self.entry.pack(anchor="w", pady=4)
            self.entry.bind("<Return>", lambda event: self.submit())
            self.entry.focus_set()
        self.answer_button = self._button("答える", self.submit)
        self._show_board(c)

    def submit(self):
        """「答える」：採点して、結果と解説を見せ、記録する。"""
        if self._answered or self.state != "question":
            return
        self._answered = True
        raw = self.entry.get() if self.entry is not None else self.choice_var.get()
        self.answer_button.state(["disabled"])
        if self.entry is not None:
            self.entry.state(["disabled"])
        for radio in self.choices:
            radio.state(["disabled"])
        try:
            outcome = self.session.answer(raw)
        except HANDLED_ERRORS as error:
            self.show_error(error)
            return
        if outcome.correct:
            self._label("正解です！", font=("TkDefaultFont", 12, "bold"), foreground="#1b7a3a")
        else:
            self._label(f"不正解です。正解は「{outcome.shown_answer}」です。", font=("TkDefaultFont", 12, "bold"), foreground="#b3261e")
        self._label("【解説】\n" + outcome.explanation)
        try:
            self.session.record()  # 1問答えるたびに記録する。途中でやめても、答えた分は残る
        except HANDLED_ERRORS as error:
            self.show_error(error)
            return
        self.state = "result"
        self._button("結果を見る" if self.session.finished else "次の問題へ", self.next_question)

    def next_question(self):
        if self.session.finished:
            self.show_finished()
        else:
            self.show_question()

    # ----- 結果と難易度の提案 -----

    def show_finished(self, notice=None):
        """結果の画面。全問正解が続いていれば、難易度を上げるかを聞く（notice は反映後の知らせ）。"""
        self._reset()
        self.state = "finished"
        if self.plan.kind == "extra":
            self._label(f"追加の {len(self.session.results)} 問を記録しました。")
        else:
            for line in summary_lines(self.session.results, self.options.log):
                self._label(line)
        if self.plan.kind in ("today", "pending", "extra"):
            try:
                git_lines = unit_done_notice(self.plan.entries, read_log(self.options.log))
            except HANDLED_ERRORS as error:
                self.show_error(error)
                return
            if git_lines:
                self._label("\n".join(git_lines))
            try:
                fun_lines = farewell(
                    self.config,
                    self._lang(),
                    self.options.questions_dir,
                    self.options.log,
                    self.options.progress,
                    self.options.today,
                )
            except HANDLED_ERRORS as error:
                self.show_error(error)
                return
            if fun_lines:
                self._label("\n".join(fun_lines))
        if notice:
            self._label(notice)
        elif notice is None and self.plan.kind == "today":
            try:
                offer = level_up_offer(self.plan.progress, self.plan.lang, self.options.log, self.config["level_up_streak"])
            except HANDLED_ERRORS as error:
                self.show_error(error)
                return
            if offer:
                self._label(
                    f"{offer.streak}日連続で全問正解でした。"
                    f"難易度を Lv{offer.from_level} から Lv{offer.to_level} に上げますか？"
                )
                self._button("上げる", lambda: self.answer_level_up(True))
                self._button("上げない", lambda: self.answer_level_up(False))
        try:
            c = self._companion(self._lang())
        except HANDLED_ERRORS as error:
            self.show_error(error)
            return
        self._show_character(c, shrink=2)
        self._show_board(c)
        self._button("もう1問", self.start_extra)
        self._button("難易度を下げる", self.answer_level_down)
        self._button("最初に戻る", self.show_start)
        self._button("閉じる", self.root.destroy)

    def start_extra(self):
        """「もう1問」：同じ言語の、続きの問題を1問出す（何回でも）。"""
        try:
            lang = self._lang()
            self.plan = plan_extra(
                self.config, self.options.questions_dir, self.options.log, self.options.progress, self.options.today, lang
            )
        except HANDLED_ERRORS as error:
            self.show_error(error)
            return
        self._open_session()

    def answer_level_down(self):
        try:
            message = level_down_now(
                load_progress(self.options.progress), self.options.progress, self._lang(), self.options.today
            )
        except HANDLED_ERRORS as error:
            self.show_error(error)
            return
        if self.state == "rest":
            self.show_rest(notice=message)
        else:
            self.show_finished(notice=message)

    def answer_level_up(self, accept):
        try:
            message = apply_level_up(
                self.plan.progress, self.options.progress, self.plan.lang, self.options.today, accept
            )
        except HANDLED_ERRORS as error:
            self.show_error(error)
            return
        self.show_finished(notice=message or "難易度はそのままにしました。")

    # ----- エラー -----

    def show_error(self, error):
        """エラーの画面。drill.py の「エラー：…」と同じ内容を、ウィンドウに出す。"""
        self._reset()
        self.state = "error"
        self._label("エラー", font=("TkDefaultFont", 14, "bold"), foreground="#b3261e")
        self._label(str(error))
        self._button("最初に戻る", self.show_start)
        self._button("閉じる", self.root.destroy)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="code-drill のウィンドウ版（tkinter）です。")
    parser.add_argument("--questions-dir", type=_path, default=QUESTIONS_DIR, help="問題集のフォルダ（省略すると questions/）")
    parser.add_argument("--log", type=_path, default=DEFAULT_LOG, help="記録するCSVファイル（省略すると data/log.csv）")
    parser.add_argument("--config", type=_path, default=DEFAULT_CONFIG, help="設定ファイル（省略すると config.yaml）")
    parser.add_argument("--progress", type=_path, default=DEFAULT_PROGRESS, help="進み具合のJSONファイル（省略すると data/progress.json）")
    parser.add_argument("--date", default=None, help="「今日」の日付を YYYY-MM-DD で指定する（試験や確認用）")
    return parser.parse_args(argv)


def _path(text):
    from pathlib import Path

    return Path(text)


def main(argv=None):
    args = parse_args(argv)
    if tk is None:
        print("エラー：tkinter が使えません（この Python には入っていません）。python.org の Python を入れ直すと使えます。", file=sys.stderr)
        sys.exit(1)
    options = Options(args.questions_dir, args.log, args.config, args.progress, parse_date(args.date))
    root = tk.Tk()
    DrillApp(root, options)
    root.mainloop()


if __name__ == "__main__":
    main()
