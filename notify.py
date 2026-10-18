"""code-drill 段階7：通知を出す入り口（Windows のタスク スケジューラなどから決まった時刻に実行する）

使い方：
    python notify.py --when start       # 学習の時間の合図を出す（学習する日だけ）
    python notify.py --when remind      # 今日の記録がないときだけ、リマインドを出す（学習する日だけ）
    python notify.py --when start --date 2026-10-14   # 「今日」の日付を指定する（試験や確認用）
    python notify.py --help             # 指定できる項目を表示する（何も送らない）

どの部品で知らせるかは、config.yaml の notifier（none / windows / email / ntfy）で決める。
PCの外に出る部品（email・ntfy）は、config.yaml に「privacy: standard」と書いたときだけ使える（既定の strict では断る）。
送る文章は、このファイルの build_message が作る決まった一文だけ（記録の中身は含めない）。
メール・ntfy の設定は .env に書く（書き方は notifier.py の冒頭を参照）。
記録（log.csv）は読むだけで、書き換えない。出題はしない（出題は drill.py・gui.py・web.py）。

Windows のタスク スケジューラに登録する例（毎日 17:30 に合図、21:30 にリマインド。このコマンドは、自分で実行したときだけ登録される）：
    schtasks /Create /SC DAILY /ST 17:30 /TN "code-drill 合図" /TR "python C:\\code-drill\\notify.py --when start"
    schtasks /Create /SC DAILY /ST 21:30 /TN "code-drill リマインド" /TR "python C:\\code-drill\\notify.py --when remind"
（休みの日は、このプログラムが何も送らないので、毎日の登録でよい）
"""

import argparse
import sys
from pathlib import Path

from config import ConfigError, load_config
from drill import BASE_DIR, DEFAULT_CONFIG, DEFAULT_LOG, fail, parse_date
from notifier import NotifyError, check_env_location, check_privacy, load_env, make_notifier
from recorder import LogFileError, check_log, read_log
from timetable import is_study_day

DEFAULT_ENV = BASE_DIR / ".env"

KINDS = ("start", "remind")


def build_message(kind, config, rows, today):
    """知らせる文章を返す。知らせなくてよいときは None。

    start：学習する日に、学習の時間だと伝える（記録は見ない）。
    remind：学習する日で、今日の記録がまだないときだけ、学習がまだだと伝える。
    """
    if kind not in KINDS:
        raise ValueError(f"kind は {KINDS} のどちらかです: {kind!r}")
    if not is_study_day(today, config["days"]):
        return None
    n = config["questions_per_day"]
    if kind == "start":
        return f"今日の学習の時間です（{n}問）。python drill.py で始めましょう。"
    if any(row["date"] == today.isoformat() for row in rows):
        return None
    return f"今日の学習がまだです（{n}問）。python drill.py で始めましょう。"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="code-drill の通知を出します。タスク スケジューラなどから、決まった時刻に実行します。")
    parser.add_argument("--when", required=True, choices=KINDS, help="start＝学習の時間の合図／remind＝今日の記録がないときだけのリマインド")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="設定ファイル（省略すると config.yaml）")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="記録のCSVファイル（省略すると data/log.csv。読むだけ）")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV, help="通知の設定を書いた .env（省略すると .env）")
    parser.add_argument("--date", default=None, help="「今日」の日付を YYYY-MM-DD で指定する（省略すると本当の今日）")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    today = parse_date(args.date)
    try:
        config = load_config(args.config)
        name = config["notifier"]
        if name == "none":
            print("notifier が none のため、何も送りません（config.yaml の notifier で windows か email を選ぶと通知されます）。")
            return
        check_privacy(name, config["privacy"])  # PCの外に出さない設定なら、.env（パスワード）を読む前に止める
        check_env_location(args.env)  # .env が Git に上がってしまう状態なら、使う前に止める
        send = make_notifier(name, load_env(args.env))  # 設定の誤りは、休みの日でも気づけるよう、先に確かめる
        rows = []
        if args.when == "remind":
            check_log(args.log)
            rows = read_log(args.log)
        message = build_message(args.when, config, rows, today)
        if message is None:
            if not is_study_day(today, config["days"]):
                print("今日は休みの日なので、通知しません。")
            else:
                print("今日の記録があるので、通知しません。")
            return
        send(message)
        print(f"通知しました（{name}）：{message}")
    except (ConfigError, NotifyError, LogFileError) as error:
        fail(error)


if __name__ == "__main__":
    main()
