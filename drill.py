"""code-drill 段階6-3：文字の画面（表示と入力）。学習の流れは session.py に任せる

使い方：
    python drill.py                                   # 今日の言語を決めて、2問（日曜は休み）
    python drill.py questions/python/batting_01_variables.yaml   # 問題集を指定して練習する
    python drill.py --log 記録の場所.csv               # 記録するCSVの場所を変える
    python drill.py --config 設定の場所.yaml           # 設定ファイルの場所を変える
    python drill.py --date 2026-10-14                 # 「今日」の日付を指定する（試験や確認用）
    python drill.py --progress 進み具合の場所.json     # 進み具合を保存するJSONの場所を変える
    python drill.py --level-up                        # 問題を解かずに、難易度を1つ上げる（言語が複数なら --level-up python）
    python drill.py --level-down                      # 問題を解かずに、難易度を1つ下げる
    python drill.py --check                           # questions/ の問題集の誤りを、まとめて表示する
    python drill.py --check questions/sql             # 指定したファイルやフォルダだけを検査する

ファイルの役割：
    drill.py     文字の画面（表示と入力）。コマンドの指定を読んで、session.py を呼ぶ
    gui.py       ウィンドウの画面（tkinter。python gui.py で開く）。同じく session.py を呼ぶ
    session.py   学習の流れ（今日の計画・採点・記録・難易度の提案）。画面を使わない部品
    loader.py    問題集と言語の設定を読む
    grading.py   採点
    picker.py    出題する問題を選ぶ
    history.py   記録からの集計（出題済み・直近の正誤・全問正解の連続）
    progress.py  進み具合（単元・難易度・周回・未回答）の読み書き
    timetable.py 学習する日と、今日の言語・問題集を決める
    config.py    設定（config.yaml）を読む
    checker.py   問題集の形式を検査する（--check と、出題前の検査）
    recorder.py  記録（log.csv）の読み書き
    tests/       テスト（python run_tests.py で実行し、結果の報告書も作る）
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from checker import check_paths, format_report
from config import ConfigError, load_config
from loader import QuestionFileError
from progress import ProgressError, load_progress
from recorder import LogFileError, check_log, check_writable, read_log
from session import (
    Session,
    SessionError,
    apply_level_up,
    available_languages,
    board_lines,
    companion,
    farewell,
    choose_level_up_language,
    level_down_now,
    level_up_now,
    level_up_offer,
    parse_yes,
    plan_extra,
    rest_language,
    plan_file,
    plan_scheduled,
    summary_lines,
    unit_done_notice,
)
from timetable import ScheduleError

# drill.py のあるフォルダ。ファイルの場所は、ここを基準にする
# （どのフォルダから起動しても、見つかるようにするため）
BASE_DIR = Path(__file__).resolve().parent

# 問題集を置くフォルダ（この下に、言語ごとのフォルダがある）
QUESTIONS_DIR = BASE_DIR / "questions"

# 何も指定しなかったときに読む設定ファイル（なければ既定値で動く）
DEFAULT_CONFIG = BASE_DIR / "config.yaml"

# 何も指定しなかったときに記録するファイル
DEFAULT_LOG = BASE_DIR / "data" / "log.csv"

# 何も指定しなかったときに、進み具合を保存するファイル
DEFAULT_PROGRESS = BASE_DIR / "data" / "progress.json"


def fail(message):
    """エラーの内容を1行で出して、終了コード1で終了する。"""
    print(f"エラー：{message}", file=sys.stderr)
    sys.exit(1)


def show_question(number, q):
    """1問分を画面に表示する。q は1問ぶんの辞書。"""
    print(f"--- 問{number}  [{q['id']}]  Lv{q['level']}  {q['unit']}")
    print(q["question"])
    print()
    print(q["code"].rstrip())
    # 選択肢は、type が choice の問題にだけある
    if q["type"] == "choice":
        print()
        for i, choice in enumerate(q["choices"], start=1):
            print(f"  {i}. {choice}")
    print()


def ask_question(session):
    """今の1問を出題し、答えを入力してもらい、採点して、結果を表示して、記録する。"""
    entry = session.current
    q = entry["q"]
    show_question(session.number, q)

    if q["type"] == "choice":
        prompt = "答え（番号）> "
    else:
        prompt = "答え> "
    outcome = session.answer(input(prompt))

    print()
    if outcome.correct:
        print("正解です！")
    else:
        print(f"不正解です。正解は「{outcome.shown_answer}」です。")
    print()
    print("【解説】")
    print(outcome.explanation)
    print()
    session.record()


def parse_args():
    """コマンドの後ろに書かれた指定を読み取る。"""
    parser = argparse.ArgumentParser(description="コード問題を2問出題して、採点し、結果を記録します。")
    parser.add_argument(
        "questions",
        nargs="?",  # 省略してもよい
        type=Path,
        default=None,
        help="問題集のYAMLファイル（省略すると、今日の言語を決めて、その問題集を使う）",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG,
        help="記録するCSVファイル（省略すると data/log.csv）",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="設定ファイル（省略すると config.yaml。なければ既定値）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="出題せずに、問題集の形式を検査する（ファイルやフォルダを指定。省略すると questions/ 全体）",
    )
    parser.add_argument(
        "--progress",
        type=Path,
        default=DEFAULT_PROGRESS,
        help="進み具合を保存するJSONファイル（省略すると data/progress.json）",
    )
    parser.add_argument(
        "--questions-dir",
        type=Path,
        default=QUESTIONS_DIR,
        help="言語ごとのフォルダが入った問題集のフォルダ（省略すると questions/。試験用）",
    )
    parser.add_argument(
        "--level-up",
        nargs="?",
        const="",
        default=None,
        metavar="言語",
        help="問題を解かずに、難易度を1つ上げる（言語が1つなら言語名は省略できる）",
    )
    parser.add_argument(
        "--level-down",
        nargs="?",
        const="",
        default=None,
        metavar="言語",
        help="問題を解かずに、難易度を1つ下げる（言語が1つなら言語名は省略できる）",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="「今日」の日付を YYYY-MM-DD で指定する（省略すると本当の今日）",
    )
    return parser.parse_args()


def parse_date(text):
    """--date の文字（YYYY-MM-DD）を日付にする。省略されたら、今日。"""
    if text is None:
        return date.today()
    try:
        return date.fromisoformat(text)
    except ValueError:
        fail(f"--date は YYYY-MM-DD の形で、正しい日付を指定してください: {text}")


def run_check(args):
    """--check：問題集を検査して、結果を表示する。誤りがあれば終了コード1で終わる。"""
    targets = [args.questions] if args.questions else [QUESTIONS_DIR]
    result = check_paths(targets)
    print("\n".join(format_report(result)))
    sys.exit(1 if result.problems else 0)


def run_level_up(args, config):
    """--level-up：問題を解かずに、難易度を1つ上げる。"""
    languages = available_languages(config, args.questions_dir)
    lang = choose_level_up_language(languages, args.level_up)
    progress = load_progress(args.progress)
    print(level_up_now(progress, args.progress, lang, parse_date(args.date)))


def run_level_down(args, config):
    """--level-down：問題を解かずに、難易度を1つ下げる。"""
    languages = available_languages(config, args.questions_dir)
    lang = choose_level_up_language(languages, args.level_down, option="--level-down")
    progress = load_progress(args.progress)
    print(level_down_now(progress, args.progress, lang, parse_date(args.date)))


def run_session(session):
    """出題のループ。正誤のリスト（True / False）を返す。中断したときは、終了コード1で終了する。"""
    try:
        while not session.finished:
            ask_question(session)
    except (EOFError, KeyboardInterrupt):
        # Ctrl+C や、入力の終わり（Ctrl+D）で途中でやめたとき
        print("\n中断しました。", file=sys.stderr)
        sys.exit(1)
    except (LogFileError, ProgressError) as error:
        fail(error)
    return session.results


def finish(results, log_path):
    print("\n".join(summary_lines(results, log_path)))


def offer_level_up(args, config, plan, today):
    """全問正解の学習日が続いていたら、難易度を上げるかを聞く。"""
    offer = level_up_offer(plan.progress, plan.lang, args.log, config["level_up_streak"])
    if offer is None:
        return
    print()
    try:
        answer = input(
            f"{offer.streak}日連続で全問正解でした。難易度を Lv{offer.from_level} から Lv{offer.to_level} に上げますか？ [y/N]: "
        )
    except (EOFError, KeyboardInterrupt):
        print()
        return  # 答えがなければ、何も変えない
    message = apply_level_up(plan.progress, args.progress, plan.lang, today, parse_yes(answer))
    if message:
        print(message)


def run_scheduled(args, config, today):
    """問題集を指定しないとき：未回答→今日の言語・単元・難易度で出題→難易度の提案。"""
    plan = plan_scheduled(config, args.questions_dir, args.log, args.progress, today)
    print("\n".join(plan.intro))
    if plan.kind == "rest":
        show_companion(args, config, today, rest_language(config, args.questions_dir, args.log, today))
        return
    session = Session(plan.entries, args.log, today, plan.progress, args.progress)
    finish(run_session(session), args.log)
    lang = plan.lang or plan.entries[-1]["lang"]
    show_farewell(args, config, today, lang)
    if plan.kind == "today":
        offer_level_up(args, config, plan, today)
    run_extras(args, config, today, lang, plan.entries)


def show_farewell(args, config, today, lang):
    """キャラのひとことと、今日もらった称号を出す。そのあとに、キャラの今の様子と、すごろくを出す。"""
    lines = farewell(config, lang, args.questions_dir, args.log, args.progress, today)
    if lines:
        print()
        print("\n".join(lines))
    show_companion(args, config, today, lang)


def show_companion(args, config, today, lang):
    """キャラの今の様子（Lv・すがた）と、すごろくの盤面を出す。"""
    c = companion(config, lang, args.questions_dir, args.log, args.progress, today)
    lines = []
    if c["name"]:
        lines.append(f"{c['avatar']} {c['name']}　Lv{c['level']}　すがた：{c['form']}　次のすがた：{c['next_form']}")
    lines += board_lines(config, args.questions_dir, args.log, args.progress, today)
    if lines:
        print()
        print("\n".join(lines))


def run_extras(args, config, today, lang, entries):
    """終わったあと：単元の終わりの Git の案内と、「もう1問」（何回でも）。"""
    notice = unit_done_notice(entries, read_log(args.log))
    if notice:
        print()
        print("\n".join(notice))
    while True:
        print()
        try:
            answer = input("もう1問 解きますか？ [y/N]: ")
        except (EOFError, KeyboardInterrupt):
            print()
            return  # 答えがなければ、何も変えない
        if not parse_yes(answer):
            return
        plan = plan_extra(config, args.questions_dir, args.log, args.progress, today, lang)
        print("\n".join(plan.intro))
        session = Session(plan.entries, args.log, today)
        results = run_session(session)
        print(f"結果を記録しました（追加の{len(results)}問）: {args.log}")
        show_farewell(args, config, today, lang)
        notice = unit_done_notice(plan.entries, read_log(args.log))
        if notice:
            print("\n".join(notice))


def run_file(args):
    """問題集のファイルを指定したとき：進み具合は使わず、ランダムに選ぶ（お試し・練習用）。"""
    today = parse_date(args.date)
    plan = plan_file(args.questions, load_config(args.config))
    print("\n".join(plan.intro))
    finish(run_session(Session(plan.entries, args.log, today)), args.log)


def main():
    args = parse_args()
    if args.check:
        run_check(args)  # 検査だけを行う。記録や設定は使わない
    today = parse_date(args.date)

    # 読めないとき・形が正しくないときは、原因を1行で伝えて終了する
    try:
        config = load_config(args.config)
        check_log(args.log)
        check_writable(args.log)  # 答えたあとで記録できないと困るので、始める前に確かめる
        if args.level_up is not None:
            run_level_up(args, config)
        elif args.level_down is not None:
            run_level_down(args, config)
        elif args.questions is not None:
            run_file(args)
        else:
            run_scheduled(args, config, today)
    except (ConfigError, QuestionFileError, LogFileError, ScheduleError, ProgressError, SessionError) as error:
        fail(error)


if __name__ == "__main__":
    main()
