"""学習の記録（log.csv）を読み書きする。画面への表示や入力は、ここでは行わない。

記録は1問1行。列は FIELDNAMES のとおり（設計書 §6）。
"""

import csv
from datetime import date
from pathlib import Path

# 記録の列（この順番で書く）
FIELDNAMES = ["date", "qid", "lang", "unit", "correct", "level", "round", "note"]

# Excel で開いても日本語が文字化けしないように、BOM付きの UTF-8 で保存する。
# 追記のときは、2回目以降に BOM が重ねて書かれることはない
ENCODING = "utf-8-sig"

# 周回は、段階6で進捗を持たせるまでは、いつも1にしておく
DEFAULT_ROUND = 1


# 書き込めないとき（Windows では、Excel などで開いているファイルに書き込めない）の案内
LOCKED_MESSAGE = (
    "記録ファイルに書き込めません: {path}\n"
    "Excel などのソフトで開いている場合は、閉じてから、もう一度実行してください"
)


class LogFileError(Exception):
    """記録のファイルが読めない・書けない・形が違うときの例外。

    メッセージは、そのまま画面に出して、使う人に伝えられる文章にする。
    """


def make_row(q, correct, lang, today=None, round_no=DEFAULT_ROUND, note=""):
    """1問ぶんの記録（辞書）を作る。

    q は問題、correct は正解なら True、lang は言語（問題集のフォルダ名）。
    today には日付（datetime.date）を渡せる。渡さなければ、今日になる。
    """
    today = today or date.today()
    return {
        "date": today.isoformat(),
        "qid": q["id"],
        "lang": lang,
        "unit": q["unit"],
        "correct": 1 if correct else 0,  # 正解は 1、不正解は 0
        "level": q["level"],
        "round": round_no,
        "note": note,  # メモ。追加の1問は「追加」。ふだんは空
    }


def check_log(path):
    """記録のファイルが、追記してよい状態かを確かめる。だめなら LogFileError にする。

    ファイルがない・中身が空なら、問題なし（新しく作る）。
    """
    path = Path(path)
    if not path.exists():
        return
    if path.is_dir():
        raise LogFileError(f"記録ファイルの場所がフォルダになっています: {path}")
    try:
        with open(path, encoding=ENCODING, newline="") as f:
            first_line = f.readline()
    except UnicodeDecodeError:
        raise LogFileError(f"記録ファイルの文字コードが UTF-8 ではありません: {path}") from None
    except OSError as e:
        raise LogFileError(f"記録ファイルを読めません: {path}（{e.strerror}）") from e
    if not first_line.strip():
        return
    header = next(csv.reader([first_line]))
    if header != FIELDNAMES:
        raise LogFileError(
            f"記録ファイルの1行目（見出し）が、決まった形と違います: {path}\n"
            f"このファイルを別の場所に移してから、もう一度実行してください"
        )


def check_writable(path):
    """記録のファイルに書き込めるかを、書き込まずに確かめる。だめなら LogFileError にする。

    問題を出す前に確かめるためのもの（答えたあとで書けないと分かると、入力が無駄になる）。
    ファイルがまだなければ、確かめられないので何もしない（ファイルやフォルダは作らない）。
    """
    path = Path(path)
    if not path.is_file():
        return
    try:
        with open(path, "a", encoding=ENCODING, newline=""):
            pass  # 追記の形で開けるかだけを確かめる。何も書かないので、中身は変わらない
    except PermissionError as e:
        raise LogFileError(LOCKED_MESSAGE.format(path=path)) from e
    except OSError as e:
        raise LogFileError(f"記録ファイルに書き込めません: {path}（{e.strerror}）") from e


def append_log(path, rows):
    """記録を、ファイルの末尾に追記する。ファイルやフォルダがなければ作る。

    rows は、make_row で作った記録（辞書）のリスト。
    """
    path = Path(path)
    check_log(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # 新しいファイル（または空のファイル）のときだけ、見出しの行を書く
        new_file = (not path.exists()) or path.stat().st_size == 0
        with open(path, "a", encoding=ENCODING, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if new_file:
                writer.writeheader()
            writer.writerows(rows)
    except PermissionError as e:
        raise LogFileError(LOCKED_MESSAGE.format(path=path)) from e
    except OSError as e:
        raise LogFileError(f"記録を書き込めません: {path}（{e.strerror}）") from e


def read_log(path):
    """記録を読み込み、1行ごとの辞書のリストで返す。ファイルがなければ空のリスト。

    値はすべて文字列で返る（correct は "1" か "0"）。
    """
    path = Path(path)
    if not path.exists():
        return []
    check_log(path)
    try:
        with open(path, encoding=ENCODING, newline="") as f:
            return list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError) as e:
        raise LogFileError(f"記録ファイルを読めません: {path}") from e
