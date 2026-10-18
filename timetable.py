"""学習する日・今日の言語・使う問題集ファイルを決める。画面への表示や入力は、ここでは行わない。

日付は、呼び出す側から渡す（datetime.date）。こうしておくと、試験で
「水曜日」「学習日の3日目」を、いつでも同じ条件で再現できる。
"""

from pathlib import Path

# date.weekday() は、月曜が 0、日曜が 6 を返す。その順番に並べた曜日の名前
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# 問題集のファイルの拡張子
QUESTION_SUFFIXES = (".yaml", ".yml")


class ScheduleError(Exception):
    """言語や問題集を決められないときの例外。

    メッセージは、そのまま画面に出して、使う人に伝えられる文章にする。
    """


def is_study_day(today, days):
    """今日が学習する日かを True / False で返す。days は ["mon", "tue", …] の形。"""
    return DAY_NAMES[today.weekday()] in days


def study_day_number(rows, today):
    """今日が「学習日の何日目」かを返す（初日は 1）。

    記録（read_log の結果）にある、今日より前の日付の数（同じ日は1日と数える）に 1 を足す。
    今日の分がすでに記録されていても、数は変わらない（同じ日に2回実行しても同じ言語になる）。
    今日より先の日付は、数えない。
    """
    earlier = {row["date"] for row in rows if row["date"] < today.isoformat()}
    return len(earlier) + 1


def pick_language(day_number, languages, rotation):
    """学習日の何日目かから、今日の言語を決める。

    rotation が {"sql": 2} なら、「2日に1度（2日目、4日目、…）は sql」。
    ほかの日は、languages の先頭の言語。複数の言語の日が重なったら、rotation に先に書いた言語を優先する。
    rotation が None のときは、languages の順に1日ずつ回す。
    """
    if not languages:
        raise ScheduleError(
            "使える言語がありません。questions/ の下に、言語のフォルダと問題集（YAML）を置いてください"
        )
    if rotation is None:
        return languages[(day_number - 1) % len(languages)]  # % は割り算の余り

    for lang in rotation:
        if lang not in languages:
            raise ScheduleError(
                f"language_rotation の「{lang}」が、languages にありません"
                f"（languages: {', '.join(languages)}）"
            )
    for lang, every in rotation.items():
        if day_number % every == 0:
            return lang
    return languages[0]


def _question_files(language_dir):
    """言語フォルダの中の問題集ファイルを、名前順で返す（_ で始まる設定ファイルは除く）。"""
    return sorted(
        p
        for p in Path(language_dir).iterdir()
        if p.is_file() and p.suffix in QUESTION_SUFFIXES and not p.name.startswith("_")
    )


def find_languages(questions_dir):
    """questions/ の下で、問題集を持つフォルダの名前を、名前順で返す。"""
    questions_dir = Path(questions_dir)
    if not questions_dir.is_dir():
        return []
    return sorted(
        d.name
        for d in questions_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_") and _question_files(d)
    )


def unit_files(questions_dir, lang):
    """言語フォルダの問題集（単元）を、ファイル名の順で返す。なければ ScheduleError。"""
    language_dir = Path(questions_dir) / lang
    files = _question_files(language_dir) if language_dir.is_dir() else []
    if not files:
        raise ScheduleError(
            f"言語「{lang}」の問題集が見つかりません: {language_dir}"
            f"（フォルダを作り、問題集の YAML を置いてください）"
        )
    return files


def first_question_file(questions_dir, lang):
    """言語フォルダの問題集のうち、ファイル名の最初のものを返す。

    単元ごとの進み具合を持つ段階6-2までの、仮の決め方。
    """
    language_dir = Path(questions_dir) / lang
    files = _question_files(language_dir) if language_dir.is_dir() else []
    if not files:
        raise ScheduleError(
            f"言語「{lang}」の問題集が見つかりません: {language_dir}"
            f"（フォルダを作り、問題集の YAML を置いてください）"
        )
    return files[0]
