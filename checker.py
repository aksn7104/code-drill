"""問題集（と言語の設定）の形式を検査する。画面への表示や入力は、ここでは行わない。

使われ方は2つ：
  ・python drill.py --check で、誤りを全部まとめて表示する
  ・出題の前に、同じ検査を行い、誤りがあれば出題せずに止める

検査の内容は、設計書 §9 と、tests/test_data.py の項目が土台。
誤りは、見つけたものをすべて集めて返す（最初の1つで止まらない）。
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from loader import QuestionFileError, load_questions

REQUIRED_KEYS = ["id", "unit", "level", "type", "question", "code", "answer", "explanation"]
TEXT_KEYS = ["unit", "question", "code", "explanation"]
QUESTION_SUFFIXES = (".yaml", ".yml")
LANGUAGE_FILE = "_language.yaml"

# 答えが問題文やコードに書かれていないかを調べるときの、答えの最小の長さ
# （1〜2文字は、偶然の一致が多いので調べない）
GIVEAWAY_MIN_LENGTH = 3


@dataclass(frozen=True)
class Problem:
    """見つかった誤り1件。どのファイルの、どの問題の、どんな誤りかを持つ。"""

    path: str | None
    qid: str | None
    message: str

    def __str__(self):
        parts = []
        if self.path:
            parts.append(str(self.path))
        if self.qid:
            parts.append(f"[{self.qid}]")
        parts.append(self.message)
        return "  ".join(parts)


@dataclass
class CheckResult:
    """検査の結果。検査したファイルの数・問題の数と、見つかった誤り。"""

    file_count: int = 0
    question_count: int = 0
    problems: list = field(default_factory=list)


def _is_text(value):
    return isinstance(value, str)


def _is_blank_text(value):
    return _is_text(value) and not value.strip()


def _check_answer(q):
    """answer の誤りのメッセージを返す。誤りがなければ空のリスト。"""
    answer = q["answer"]
    if isinstance(answer, list):
        answers = answer
        if not answers:
            return ["answer が空のリストです"]
    else:
        answers = [answer]

    messages = []
    for a in answers:
        if _is_text(a):
            if not a.strip():
                messages.append("answer に、空の答えがあります")
        elif a is None or isinstance(a, (bool, int, float)):
            messages.append(
                "answer を引用符で囲んでください"
                "（引用符なしの NULL・yes・no・数字は、YAML が文字ではなく別の型として読みます。"
                f"今の値：{a!r}）"
            )
        else:
            messages.append("answer は、文字（または文字のリスト）で書いてください")
    return messages


def _check_choices(q):
    """選択式の choices と answer の関係の誤りのメッセージを返す。"""
    if "choices" not in q:
        return ["choices がありません（選択式には必要です）"]
    choices = q["choices"]
    if not isinstance(choices, list) or len(choices) < 2 or not all(_is_text(c) for c in choices):
        return ['choices は、2つ以上の文字を並べたリストで書いてください（例：["+", "-"]）']

    messages = []
    if len(choices) != len(set(choices)):
        messages.append("choices に重複があります（同じ選択肢が2つ以上あります）")
    answers = q["answer"] if isinstance(q["answer"], list) else [q["answer"]]
    for a in answers:
        if _is_text(a) and a not in choices:
            messages.append(f"answer「{a}」が、choices の中にありません")
    return messages


def _check_one(q):
    """1問の誤りのメッセージのリストを返す（項目が足りないときも、できる範囲で調べ続ける）。"""
    messages = []

    for key in REQUIRED_KEYS:
        if key not in q:
            messages.append(f"{key} がありません")

    if "id" in q and (not _is_text(q["id"]) or not q["id"].strip()):
        messages.append(
            f"id は、空でない文字で書いてください（数字だけの id は引用符で囲みます。今の値：{q['id']!r}）"
        )

    if "level" in q:
        level = q["level"]
        if not (isinstance(level, int) and not isinstance(level, bool) and 1 <= level <= 5):
            messages.append(f"level は 1〜5 の整数で書いてください（今の値：{level!r}）")

    if "type" in q and q["type"] not in ("choice", "blank"):
        messages.append(f"type は choice か blank で書いてください（今の値：{q['type']!r}）")

    for key in TEXT_KEYS:
        if key not in q:
            continue
        if not _is_text(q[key]):
            messages.append(f"{key} は文字で書いてください（今の値：{q[key]!r}）")
        elif _is_blank_text(q[key]):
            messages.append(f"{key} が空です")

    if "hint" in q and q["hint"] is not None and not _is_text(q["hint"]):
        messages.append(f"hint は文字で書いてください（今の値：{q['hint']!r}）")

    if "long" in q and not isinstance(q["long"], bool):
        messages.append(f"long は true か false で書いてください（今の値：{q['long']!r}）")

    if "code" in q and _is_text(q["code"]) and "___" not in q["code"]:
        messages.append("code に空欄の印（___）がありません")

    if "answer" in q:
        answer_messages = _check_answer(q)
        messages += answer_messages
        if not answer_messages:
            if q.get("type") == "choice":
                messages += _check_choices(q)
            messages += _check_giveaway(q)
    elif q.get("type") == "choice":
        messages += _check_choices_without_answer(q)

    return messages


def _check_choices_without_answer(q):
    """answer が欠けている選択式でも、choices だけは調べる。"""
    if "choices" not in q:
        return ["choices がありません（選択式には必要です）"]
    return []


def _check_giveaway(q):
    """答えが、問題文かコードにそのまま書かれていないかを調べる。"""
    if not (_is_text(q.get("question")) and _is_text(q.get("code"))):
        return []
    text = q["question"] + q["code"]
    answers = q["answer"] if isinstance(q["answer"], list) else [q["answer"]]
    return [
        f"答えの「{a}」が、問題文かコードにそのまま書かれています"
        for a in answers
        if _is_text(a) and len(a) >= GIVEAWAY_MIN_LENGTH and a in text
    ]


def check_questions(questions, path=None):
    """問題のリストを検査し、見つかった誤り（Problem のリスト）を返す。誤りがなければ空のリスト。"""
    problems = []
    first_seen = {}  # id → 最初に出てきた番号（重複を見つけるため）
    for number, q in enumerate(questions, start=1):
        if not isinstance(q, dict):
            problems.append(Problem(path, f"{number}番目の問題", "問題は「項目: 値」の形で書いてください"))
            continue

        qid = q["id"] if _is_text(q.get("id")) and q["id"].strip() else f"{number}番目の問題"
        for message in _check_one(q):
            problems.append(Problem(path, qid, message))

        if _is_text(q.get("id")) and q["id"].strip():
            if q["id"] in first_seen:
                problems.append(
                    Problem(
                        path,
                        qid,
                        f"id「{q['id']}」が重複しています（{first_seen[q['id']]}番目の問題と同じです）",
                    )
                )
            else:
                first_seen[q["id"]] = number
    return problems


def check_language_file(path):
    """_language.yaml の誤り（Problem のリスト）を返す。ファイルがなければ空のリスト。"""
    path = Path(path)
    if not path.exists():
        return []
    where = str(path)
    try:
        with open(path, encoding="utf-8") as f:
            settings = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [Problem(where, None, f"YAML の書き方に誤りがあります\n{e}")]
    except UnicodeDecodeError:
        return [Problem(where, None, "文字コードが UTF-8 ではありません")]
    except OSError as e:
        return [Problem(where, None, f"読めません（{e.strerror}）")]

    if settings is None:
        return []
    if not isinstance(settings, dict):
        return [Problem(where, None, f"{LANGUAGE_FILE} は「項目: 値」の形で書いてください")]

    problems = []
    if "name" in settings and (not _is_text(settings["name"]) or not settings["name"].strip()):
        problems.append(Problem(where, None, f"name は、空でない文字で書いてください（今の値：{settings['name']!r}）"))
    for key in ("case_sensitive", "ignore_spaces"):
        if key in settings and not isinstance(settings[key], bool):
            problems.append(
                Problem(where, None, f"{key} は true か false で書いてください（今の値：{settings[key]!r}）")
            )
    return problems


def _collect(paths):
    """指定されたパス（ファイルまたはフォルダ）から、検査する問題集と設定ファイルを集める。"""
    files, language_files, problems = [], [], []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            problems.append(Problem(str(path), None, "見つかりません"))
        elif path.is_dir():
            found = sorted(
                f
                for f in path.rglob("*")
                if f.is_file() and f.suffix in QUESTION_SUFFIXES and not f.name.startswith("_")
            )
            if not found:
                problems.append(Problem(str(path), None, "問題集（YAML）が見つかりません"))
            files += found
            language_files += sorted(path.rglob(LANGUAGE_FILE))
        else:
            files.append(path)
            language_files.append(path.parent / LANGUAGE_FILE)

    unique = lambda items: list(dict.fromkeys(items))  # noqa: E731  順番を保ったまま重複を除く
    return unique(files), unique(language_files), problems


def check_paths(paths):
    """ファイルやフォルダを検査して、CheckResult を返す。

    フォルダは、中のすべての問題集（_ で始まる設定ファイルを除く）を検査する。
    ファイルをまたいだ id の重複も調べる。
    """
    files, language_files, problems = _collect(paths)
    result = CheckResult(problems=problems)

    first_file_of_id = {}  # id → 最初に出てきたファイル
    for path in files:
        try:
            questions = load_questions(path)
        except QuestionFileError as e:
            result.problems.append(Problem(str(path), None, str(e)))
            continue

        result.file_count += 1
        if not questions:
            result.problems.append(Problem(str(path), None, "問題がありません（問題が1問もありません）"))
            continue

        result.question_count += len(questions)
        result.problems += check_questions(questions, str(path))

        for q in questions:
            qid = q.get("id") if isinstance(q, dict) else None
            if not (_is_text(qid) and qid.strip()):
                continue
            if qid in first_file_of_id and first_file_of_id[qid] != path:
                result.problems.append(
                    Problem(
                        str(path),
                        qid,
                        f"id「{qid}」が重複しています（{first_file_of_id[qid]} にも同じ id があります）",
                    )
                )
            else:
                first_file_of_id.setdefault(qid, path)

    for path in language_files:
        result.problems += check_language_file(path)
    return result


def format_report(result):
    """検査の結果を、画面に出す文章（行のリスト）にする。"""
    lines = [f"検査したもの：問題集 {result.file_count} 個、{result.question_count}問"]
    lines += [f"  {problem}" for problem in result.problems]
    if result.problems:
        lines.append(f"誤りが {len(result.problems)}件 ありました。直してから、もう一度実行してください。")
    else:
        lines.append("誤りはありません。")
    return lines
