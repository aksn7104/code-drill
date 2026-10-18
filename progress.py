"""進み具合（data/progress.json）の読み書きと更新。画面への表示や入力は、ここでは行わない。

形：{"langs": {"python": {"unit": "u01.yaml", "level": 1, "round": 1, "since": ""}},
     "pending": [{"lang": "python", "file": "u01.yaml", "qid": "p-1"}]}
  unit    今の単元（問題集のファイル名）。None は、まだ始めていない
  level   今の難易度（1〜5）
  round   今の周回
  since   難易度を上げた日（YYYY-MM-DD）。連続の数え始めに使う。"" は上げていない
  pending 出題したが、まだ答えていない問題
"""

import json
import os
from pathlib import Path

MAX_LEVEL = 5


class ProgressError(Exception):
    """進み具合のファイルが読めない・書けない・形が違うときの例外。

    メッセージは、そのまま画面に出して、使う人に伝えられる文章にする。
    """


def _new_state():
    return {"unit": None, "level": 1, "round": 1, "since": ""}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _validate(data, path):
    where = f"進み具合のファイルの形が正しくありません: {path}"
    hint = "（直せないときは、このファイルを別の場所に移してから起動すると、最初からやり直せます）"
    if not isinstance(data, dict):
        raise ProgressError(f"{where}\n{hint}")
    langs = data.get("langs", {})
    pending = data.get("pending", [])
    if not isinstance(langs, dict) or not isinstance(pending, list):
        raise ProgressError(f"{where}\n{hint}")

    for lang, state in langs.items():
        if not isinstance(state, dict):
            raise ProgressError(f"{where}\n{hint}")
        merged = _new_state()
        merged.update(state)
        if not (_is_int(merged["level"]) and 1 <= merged["level"] <= MAX_LEVEL):
            raise ProgressError(f"{where}\n「{lang}」の level は 1〜5 の整数にしてください{hint}")
        if not (_is_int(merged["round"]) and merged["round"] >= 1):
            raise ProgressError(f"{where}\n「{lang}」の round は 1 以上の整数にしてください{hint}")
        if merged["unit"] is not None and not isinstance(merged["unit"], str):
            raise ProgressError(f"{where}\n「{lang}」の unit は文字にしてください{hint}")
        if not isinstance(merged["since"], str):
            raise ProgressError(f"{where}\n「{lang}」の since は文字にしてください{hint}")
        langs[lang] = merged

    for item in pending:
        if not (isinstance(item, dict) and all(isinstance(item.get(k), str) for k in ("lang", "file", "qid"))):
            raise ProgressError(f"{where}\npending の中身が正しくありません{hint}")
    return {"langs": langs, "pending": pending}


def load_progress(path):
    """進み具合を読む。ファイルがなければ、空の進み具合を返す。"""
    path = Path(path)
    if not path.exists():
        return {"langs": {}, "pending": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ProgressError(
            f"進み具合のファイルが壊れています: {path}\n{e}\n"
            "（直せないときは、このファイルを別の場所に移してから起動すると、最初からやり直せます）"
        ) from e
    except UnicodeDecodeError:
        raise ProgressError(f"進み具合のファイルの文字コードが UTF-8 ではありません: {path}") from None
    except OSError as e:
        raise ProgressError(f"進み具合のファイルを読めません: {path}（{e.strerror}）") from e
    return _validate(data, path)


def save_progress(path, progress):
    """進み具合を保存する。一時ファイルに書いてから置き換えるので、途中で止まっても壊れない。"""
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    except OSError as e:
        try:
            temp.unlink()
        except OSError:
            pass
        raise ProgressError(f"進み具合を保存できません: {path}（{e.strerror}）") from e


def lang_state(progress, lang):
    """言語の状態（辞書）を返す。まだなければ、初期の状態を作って入れる。"""
    return progress["langs"].setdefault(lang, _new_state())


def add_pending(progress, items):
    """未回答の問題を追加する（すでにあるものは、重ねて追加しない）。"""
    for item in items:
        if item not in progress["pending"]:
            progress["pending"].append(dict(item))


def remove_pending(progress, lang, file, qid):
    """回答した問題を、未回答から外す。なくてもエラーにしない。"""
    target = {"lang": lang, "file": file, "qid": qid}
    progress["pending"] = [i for i in progress["pending"] if i != target]


def raise_level(progress, lang, today):
    """難易度を1つ上げて、上げた日を記録する。すでに最高なら何もしない。"""
    state = lang_state(progress, lang)
    if state["level"] >= MAX_LEVEL:
        return
    state["level"] += 1
    state["since"] = today.isoformat()


def lower_level(progress, lang, today):
    """難易度を1つ下げて、下げた日を記録する。すでに最低（Lv1）なら何もしない。"""
    state = lang_state(progress, lang)
    if state["level"] <= 1:
        return
    state["level"] -= 1
    state["since"] = today.isoformat()


def locate_unit(units, state_unit, round_no, is_done):
    """今日使う単元と周回を決める。

    units は単元（ファイル名）の並び、is_done(単元, 周回) は「その周回で全問を出し終えたか」。
    出し終えた単元は飛ばして次へ進み、最後の単元の次は、周回+1 で最初の単元に戻る。
    """
    index = units.index(state_unit) if state_unit in units else 0
    for _ in range(len(units) * 2):  # 問題のない単元だけのときに、止まらなくなるのを防ぐ上限
        if not is_done(units[index], round_no):
            break
        index += 1
        if index == len(units):
            index = 0
            round_no += 1
    return units[index], round_no
