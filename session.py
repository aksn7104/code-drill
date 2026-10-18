"""学習の流れ：今日は何を出すか → 出題 → 採点 → 記録 → 難易度の提案

このファイルは、画面（input / print）を使わない。
文字の画面（drill.py）も、あとから作る GUI（gui.py）やブラウザ版（web.py）も、
同じ部品を呼ぶだけで、同じ動きになる。画面の部品が受け持つのは、表示と入力だけ。

おもな部品：
    plan_scheduled()  問題集を指定しないとき：休み・未回答・今日の言語と単元を決めて、問題を選ぶ
    plan_file()       問題集を指定したとき：そのファイルから選ぶ（進み具合は使わない）
    Session           1問ずつの出題：answer() で採点 → record() で記録して次へ
    judge()           1問の採点
    level_up_offer()  全問正解の学習日が続いたときの難易度の提案
"""

import importlib
from collections import namedtuple
from pathlib import Path

from checker import check_questions
from grading import is_correct, to_answer_text
from history import asked_in_round, last_results, perfect_streak
from loader import load_questions, load_rules
from picker import pick_questions, pick_today
try:  # 有料版だけにある fun.py（キャラ・称号・すごろく）。無料版にはないので、なくても動くように読む
    fun = importlib.import_module("fun")
except ImportError:
    fun = None
from progress import (
    MAX_LEVEL,
    add_pending,
    lang_state,
    load_progress,
    locate_unit,
    lower_level,
    raise_level,
    remove_pending,
    save_progress,
)
from recorder import DEFAULT_ROUND, append_log, make_row, read_log
from timetable import DAY_NAMES, find_languages, is_study_day, pick_language, study_day_number, unit_files


class SessionError(Exception):
    """学習の流れで、使い手に伝えるべき問題が起きたとき（問題集に問題がない、など）。"""


# 1問の採点結果。shown_answer は、不正解のときに見せる正解（複数あるときは先頭の書き方）
Outcome = namedtuple("Outcome", "correct shown_answer explanation")

# 今日の計画。kind は "rest"（休み）/ "pending"（未回答）/ "today"（今日の分）/ "file"（問題集の指定）。
# intro は、出題の前に見せる文章（1行ずつ）。entries は {"lang", "path", "q", "round"} の並び。
# progress は進み具合（問題集を指定したときは None）
Plan = namedtuple("Plan", "kind intro entries lang progress")

# 難易度の提案。streak は全問正解が続いた日数
LevelUpOffer = namedtuple("LevelUpOffer", "streak from_level to_level")

# 出題の前の検査で、文章に入れる誤りの数（全部は --check で見られる）
SHOWN_PROBLEMS = 3
LEGEND = fun.LEGEND if fun else ""  # すごろくの凡例（無料版は空）


def explain_problems(problems, path):
    """出題の前の検査で見つかった誤りを、エラーの文章にする（先頭の数件だけ）。"""
    lines = [f"問題集に誤りがあります（{len(problems)}件）: {path}"]
    lines += [f"  [{p.qid}] {p.message}" for p in problems[:SHOWN_PROBLEMS]]
    if len(problems) > SHOWN_PROBLEMS:
        lines.append(f"  …ほか {len(problems) - SHOWN_PROBLEMS}件")
    lines.append(f"全部の誤りは、python drill.py --check {path} で確認できます")
    return "\n".join(lines)


def judge(raw, q, rules):
    """入力された答え raw を採点して、Outcome を返す。"""
    correct = is_correct(to_answer_text(raw, q), q, rules)
    # 正解が複数あるときは、先頭の書き方を見せる
    shown = q["answer"][0] if isinstance(q["answer"], list) else q["answer"]
    return Outcome(correct, shown, q["explanation"].rstrip())


def summary_lines(results, log_path):
    """最後に見せる2行（正解数と記録先）。"""
    # True は 1 として数えられるので、sum で正解の数になる
    return [
        f"今日は {len(results)} 問中 {sum(results)} 問正解でした。",
        f"結果を記録しました: {log_path}",
    ]


class Session:
    """1問ずつの出題。answer() で採点し、record() で記録して次の問題に進む。

    progress を渡すと、1問答えるたびに未回答から外して保存する。
    answer と record を分けているのは、画面に結果を見せてから記録する順番を守るため。
    """

    def __init__(self, entries, log_path, today, progress=None, progress_path=None):
        self.entries = list(entries)
        self.log_path = log_path
        self.today = today
        self.progress = progress
        self.progress_path = progress_path
        self.results = []  # 記録まで終えた問題の正誤（True / False）
        self._rules_of = {}
        self._outcome = None  # 採点したが、まだ記録していない結果

    @property
    def total(self):
        return len(self.entries)

    @property
    def finished(self):
        return len(self.results) >= self.total

    @property
    def number(self):
        """今の問題の番号（1から）。全部終えたら、問題数+1。"""
        return len(self.results) + 1

    @property
    def current(self):
        """今の問題（entry）。全部終えたら None。"""
        return None if self.finished else self.entries[len(self.results)]

    def answer(self, raw):
        """今の問題を採点して、Outcome を返す（記録はまだしない）。"""
        entry = self.current
        if entry is None:
            raise SessionError("すべての問題に答え終えています")
        rules = self._rules_of.setdefault(entry["lang"], load_rules(entry["path"]))
        self._outcome = judge(raw, entry["q"], rules)
        return self._outcome

    def record(self):
        """採点した結果を記録して、次の問題に進む。"""
        entry = self.current
        if entry is None or self._outcome is None:
            raise SessionError("record() の前に answer() で採点してください")
        correct = self._outcome.correct
        # 1問答えるたびに記録する。途中でやめても、答えた分は残る
        append_log(
            self.log_path,
            [make_row(entry["q"], correct, entry["lang"], self.today, entry["round"], entry.get("note", ""))],
        )
        if self.progress is not None:
            remove_pending(self.progress, entry["lang"], entry["path"].name, entry["q"]["id"])
            save_progress(self.progress_path, self.progress)
        self.results.append(correct)
        self._outcome = None


def _checked_questions(path):
    """問題集を読み、問題がない・誤りがあるときは SessionError にする。(問題, 言語の設定) を返す。"""
    questions = load_questions(path)
    rules = load_rules(path)
    if not questions:
        raise SessionError(f"問題集に問題がありません: {path}")
    problems = check_questions(questions)
    if problems:
        raise SessionError(explain_problems(problems, path))
    return questions, rules


def resolve_pending(progress, questions_dir):
    """未回答の問題を問題集から探す。(見つかったもの, 見つからなかったもの) を返す。

    見つかったものは、{"item", "lang", "path", "q"} の辞書。
    """
    found, dropped = [], []
    for item in progress["pending"]:
        path = Path(questions_dir) / item["lang"] / item["file"]
        question = None
        if path.is_file():
            question = next((q for q in load_questions(path) if q.get("id") == item["qid"]), None)
        if question is None:
            dropped.append(item)
        else:
            found.append({"item": item, "lang": item["lang"], "path": path, "q": question})
    return found, dropped


def available_languages(config, questions_dir):
    return config["languages"] or find_languages(questions_dir)


def plan_scheduled(config, questions_dir, log_path, progress_path, today):
    """問題集を指定しないとき：休み→未回答→今日の言語・単元・難易度、の順に決めて、Plan を返す。

    進み具合（未回答・単元・周回）は、ここで保存する。
    """
    progress = load_progress(progress_path)
    if not is_study_day(today, config["days"]):
        return Plan("rest", ["今日は休みの日です。ゆっくり休んでください。"], [], None, progress)

    intro = []
    found, dropped = resolve_pending(progress, questions_dir)
    if found or dropped:
        for item in dropped:
            intro.append(f"未回答だった問題「{item['qid']}」が問題集に見つかりません。飛ばします。")
            remove_pending(progress, item["lang"], item["file"], item["qid"])
        save_progress(progress_path, progress)
        if found:
            intro += [f"前回の未回答の問題を出します（{len(found)}問）。", ""]
            entries = [
                {"lang": f["lang"], "path": f["path"], "q": f["q"], "round": lang_state(progress, f["lang"])["round"]}
                for f in found
            ]
            return Plan("pending", intro, entries, None, progress)

    rows = read_log(log_path)
    languages = available_languages(config, questions_dir)
    lang = pick_language(study_day_number(rows, today), languages, config["language_rotation"])
    unit, round_no, path, rules, todays = _choose_today(
        lang, config["questions_per_day"], questions_dir, rows, progress
    )
    entries = [{"lang": lang, "path": path, "q": q, "round": round_no} for q in todays]
    state = lang_state(progress, lang)

    extra_intro = []
    if config["long_day"] == DAY_NAMES[today.weekday()]:
        long_entry = _pick_long(lang, questions_dir, rows, round_no, state["level"])
        if long_entry is not None:
            entries.append(long_entry)
            extra_intro = ["今日は「長めの読解」の問題も1問あります。"]

    add_pending(progress, [{"lang": lang, "file": e["path"].name, "qid": e["q"]["id"]} for e in entries])
    save_progress(progress_path, progress)

    opening = fun.opening_line(config, lang) if fun else ""
    intro += [opening] if opening else []
    intro += [
        f"今日の言語：{rules.get('name', lang)}",
        f"単元：{Path(unit).stem}　難易度：Lv{state['level']}　周回：{round_no}",
        *extra_intro,
        "",
    ]
    return Plan("today", intro, entries, lang, progress)


def _as_list(questions):
    """問題の並びのうち、辞書だけを取り出す（形の誤りは、検査で知らせる）。"""
    return [q for q in questions if isinstance(q, dict)]


def _only_long(questions):
    """長めの読解の問題だけで、日常の問題がない（空のファイルは、これに当てはまらない。誤りとして知らせる）。"""
    items = _as_list(questions)
    return bool(items) and not _normal(items)


def _normal(questions):
    """日常の問題（長めの読解の問題 long: true を除く）。"""
    return [q for q in questions if not q.get("long")]


def _choose_today(lang, count, questions_dir, rows, progress):
    """今の単元と周回を決めて、count 問を選ぶ。(単元, 周回, ファイル, 言語の設定, 選んだ問題) を返す。

    進み具合の単元・周回は更新するが、保存と未回答の追加は、呼び出した側が行う。
    """
    # 長めの読解の問題だけのファイルは、単元として数えない（土曜の長めの日にだけ使う）
    files = [f for f in unit_files(questions_dir, lang) if not _only_long(load_questions(f))]
    if not files:
        raise SessionError(f"言語「{lang}」に、日常の問題がありません（長めの読解の問題だけです）")
    by_name = {f.name: f for f in files}
    state = lang_state(progress, lang)

    def is_done(unit, round_no):
        ids = {q["id"] for q in _normal(load_questions(by_name[unit])) if isinstance(q, dict) and "id" in q}
        return bool(ids) and ids <= asked_in_round(rows, lang, round_no)

    unit, round_no = locate_unit(list(by_name), state["unit"], state["round"], is_done)
    path = by_name[unit]
    questions, rules = _checked_questions(path)
    state["unit"], state["round"] = unit, round_no
    todays = pick_today(
        _normal(questions),
        count,
        asked_in_round(rows, lang, round_no),
        last_results(rows, lang),
        state["level"],
    )
    return unit, round_no, path, rules, todays


def _pick_long(lang, questions_dir, rows, round_no, level):
    """言語の問題集から、長めの読解の問題を1問選ぶ。なければ None。"""
    candidates = []
    for path in unit_files(questions_dir, lang):
        longs = [q for q in load_questions(path) if isinstance(q, dict) and q.get("long") is True]
        if longs:
            _checked_questions(path)
            candidates += [(path, q) for q in longs]
    if not candidates:
        return None
    by_id = {q["id"]: path for path, q in candidates}
    picked = pick_today(
        [q for _, q in candidates], 1, asked_in_round(rows, lang, round_no), last_results(rows, lang), level
    )
    q = picked[0]
    return {"lang": lang, "path": by_id[q["id"]], "q": q, "round": round_no}


def plan_extra(config, questions_dir, log_path, progress_path, today, lang):
    """「もう1問」：同じ言語の、続きの問題を1問だけ選ぶ。未回答には入れない。

    単元の順番は崩さず、今の単元を出し終えていれば、次の単元から選ぶ。
    """
    if lang not in available_languages(config, questions_dir) or not unit_files(questions_dir, lang):
        raise SessionError(f"言語「{lang}」の問題集がありません")
    progress = load_progress(progress_path)
    rows = read_log(log_path)
    unit, round_no, path, rules, picked = _choose_today(lang, 1, questions_dir, rows, progress)
    save_progress(progress_path, progress)
    entries = [{"lang": lang, "path": path, "q": q, "round": round_no, "note": "追加"} for q in picked]
    return Plan("extra", ["もう1問、出します。", ""], entries, lang, progress)


def unit_done_notice(entries, rows):
    """出題した問題の単元を、今の周回で出し終えていたら、Git に保存する案内（1行ずつ）を返す。"""
    lines = []
    seen = set()
    for e in entries:
        key = (e["lang"], e["path"], e["round"])
        if key in seen:
            continue
        seen.add(key)
        ids = {q["id"] for q in _normal(load_questions(e["path"])) if isinstance(q, dict) and "id" in q}
        if ids and ids <= asked_in_round(rows, e["lang"], e["round"]):
            stem = e["path"].stem
            lines += [
                f"単元「{stem}」を解き終えました。ここまでを Git に保存するなら：",
                "  git add -A",
                f'  git commit -m "{stem} を完了"',
            ]
    return lines


def plan_file(path, config):
    """問題集のファイルを指定したとき：進み具合は使わず、ランダムに選ぶ（お試し・練習用）。"""
    questions, rules = _checked_questions(path)
    lang = path.resolve().parent.name  # 言語は、問題集を置いたフォルダの名前
    todays = pick_questions(questions, config["questions_per_day"])
    entries = [{"lang": lang, "path": path, "q": q, "round": DEFAULT_ROUND} for q in todays]
    intro = [f"今日の言語：{rules.get('name', lang)}", ""]
    return Plan("file", intro, entries, lang, None)


def level_up_offer(progress, lang, log_path, needed):
    """全問正解の学習日が needed 日以上続いていたら、LevelUpOffer を返す。なければ None。"""
    state = lang_state(progress, lang)
    if state["level"] >= MAX_LEVEL:
        return None
    streak = perfect_streak(read_log(log_path), lang, state["since"])
    if streak < needed:
        return None
    return LevelUpOffer(streak, state["level"], state["level"] + 1)


def parse_yes(text):
    """提案への答え（[y/N]）を読む。y・yes だけが「上げる」。"""
    return text.strip().lower() in ("y", "yes")


def apply_level_up(progress, progress_path, lang, today, accept):
    """提案への答えを反映して保存する。上げたときは知らせの文章、断ったときは空の文字を返す。"""
    state = lang_state(progress, lang)
    message = ""
    if accept:
        raise_level(progress, lang, today)
        message = f"難易度を Lv{state['level']} に上げました。"
    else:
        state["since"] = today.isoformat()  # 連続の数え直し（毎日は聞かない）
    save_progress(progress_path, progress)
    return message


def choose_level_up_language(languages, requested, option="--level-up"):
    """--level-up・--level-down の対象の言語を決める。requested が空なら、言語が1つのときだけ省略できる。"""
    if not requested:
        if len(languages) != 1:
            raise SessionError(
                f"言語が複数あります。{option} の後ろに言語名を付けてください（{', '.join(languages)}）"
            )
        return languages[0]
    if requested not in languages:
        raise SessionError(f"言語「{requested}」がありません（使える言語: {', '.join(languages) or 'なし'}）")
    return requested


def level_up_now(progress, progress_path, lang, today):
    """問題を解かずに難易度を1つ上げる。知らせの文章を返す。"""
    state = lang_state(progress, lang)
    if state["level"] >= MAX_LEVEL:
        return f"{lang} の難易度は、すでに最高（Lv{MAX_LEVEL}）です。"
    raise_level(progress, lang, today)
    save_progress(progress_path, progress)
    return f"{lang} の難易度を Lv{state['level'] - 1} から Lv{state['level']} に上げました。"


def level_down_now(progress, progress_path, lang, today):
    """問題を解かずに難易度を1つ下げる。知らせの文章を返す。"""
    state = lang_state(progress, lang)
    if state["level"] <= 1:
        return f"{lang} の難易度は、すでに最低（Lv1）です。"
    lower_level(progress, lang, today)
    save_progress(progress_path, progress)
    return f"{lang} の難易度を Lv{state['level'] + 1} から Lv{state['level']} に下げました。"


def farewell(config, lang, questions_dir, log_path, progress_path, today):
    """学習のあとに出す行：キャラのひとことと、今日もらった称号（なければ空のリスト）。無料版は、いつも空。"""
    if fun is None:
        return []
    catalog = fun.unit_catalog(questions_dir, available_languages(config, questions_dir))
    return fun.closing_lines(config, lang, read_log(log_path), catalog, load_progress(progress_path), today)


def companion(config, lang, questions_dir, log_path, progress_path, today):
    """画面に出す、キャラとすごろくのまとめ（辞書）。

    name（キャラの名前。characters: {} なら None）・level・form・next_form・avatar・say（ひとこと）・
    squares（その言語のすごろくの盤面）・board（盤面を1行の文字にしたもの）。
    無料版（fun.py がない）は、キャラもすごろくもない形（name が None、squares が空）を返す。
    """
    if fun is None:
        return {"name": None, "level": 1, "form": "", "next_form": "", "avatar": "", "portrait": None,
                "portrait_png": None, "say": "", "squares": [], "board": ""}
    languages = available_languages(config, questions_dir)
    catalog = fun.unit_catalog(questions_dir, languages)
    rows = read_log(log_path)
    progress = load_progress(progress_path)
    name, level, form, next_form = fun.status(config, lang, rows, catalog, progress)
    squares = fun.board(rows, catalog, progress, config["days"]).get(lang, [])
    opening = fun.opening_line(config, lang)
    return {
        "name": name,
        "level": level,
        "form": form,
        "next_form": next_form,
        "avatar": fun.avatar(form),
        "portrait": fun.portrait(name, form, "svg"),  # イラスト（SVG）。ないときは None
        "portrait_png": fun.portrait(name, form, "png"),  # ウィンドウ版用（PNG）
        "say": opening.split("：", 1)[-1] if opening else "",
        "squares": squares,
        "board": fun.board_text(squares),
    }


def board_lines(config, questions_dir, log_path, progress_path, today):
    """すごろくの盤面を、言語ごとに「言語：盤面」の行にして返す。最後の行は凡例。無料版は、いつも空。"""
    if fun is None:
        return []
    languages = available_languages(config, questions_dir)
    catalog = fun.unit_catalog(questions_dir, languages)
    board = fun.board(read_log(log_path), catalog, load_progress(progress_path), config["days"])
    lines = [f"{lang}：{fun.board_text(squares)}" for lang, squares in board.items() if squares]
    return lines + [fun.LEGEND] if lines else []


def rest_language(config, questions_dir, log_path, today):
    """休みの日に「もう1問」を出すときの言語。平日と同じ決め方（学習した日数で交代）。"""
    rows = read_log(log_path)
    languages = available_languages(config, questions_dir)
    return pick_language(study_day_number(rows, today), languages, config["language_rotation"])
