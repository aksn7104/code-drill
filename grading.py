"""答えの採点。画面への表示や入力は、ここでは行わない（drill.py の役目）。"""

import unicodedata


def to_halfwidth(text):
    """全角の英数字・記号・スペースを半角にそろえる（Unicode の NFKC 正規化）。

    日本語入力をオンにしたまま答えても、採点できるようにするため。
    「２」→「2」、「ｆ」→「f」、「／」→「/」、全角スペース→半角スペース。
    """
    return unicodedata.normalize("NFKC", str(text))


def to_answer_text(raw, q):
    """入力された文字を、採点に使う答えの文字に直す。

    選択式の問題で番号（1〜）が入力されたら、その番号の選択肢の文字にする。
    それ以外は、入力された文字をそのまま返す（全角は半角にそろえる）。
    """
    raw = to_halfwidth(raw).strip()
    if q["type"] == "choice" and raw.isdigit():
        number = int(raw)
        if 1 <= number <= len(q["choices"]):
            return q["choices"][number - 1]
    return raw


def normalize(text, rules):
    """採点のきまりに合わせて、文字をそろえる。"""
    text = to_halfwidth(text).strip()
    if rules["ignore_spaces"]:
        text = "".join(text.split())  # 空白（スペースや改行）をすべて取り除く
    if not rules["case_sensitive"]:
        text = text.lower()  # 大文字・小文字を区別しないときは、小文字にそろえる
    return text


def is_correct(answer_text, q, rules):
    """答えが正解かどうかを True / False で返す。"""
    correct = q["answer"]
    # 正解が1つだけの書き方（文字）でも、複数の書き方（リスト）でも扱えるようにする
    if not isinstance(correct, list):
        correct = [correct]
    return normalize(answer_text, rules) in [normalize(c, rules) for c in correct]
