"""記録（log.csv を read_log で読んだ行）からの集計。画面への表示や入力は、ここでは行わない。

行の値はすべて文字列（correct は "1" か "0"、round は "1" など）。
"""


def asked_in_round(rows, lang, round_no):
    """指定した言語・周回で、出題済みの問題id の集合を返す。"""
    return {r["qid"] for r in rows if r["lang"] == lang and r["round"] == str(round_no)}


def last_results(rows, lang):
    """言語ごとに、問題id → 直近の正誤（True / False）を返す。同じ問題は、後の行が優先。"""
    results = {}
    for r in rows:
        if r["lang"] == lang:
            results[r["qid"]] = r["correct"] == "1"
    return results


def perfect_streak(rows, lang, since=""):
    """全問正解だった学習日が、直近から何日連続しているかを返す。

    その言語を学習した日だけを並べて数える（ほかの言語の日や休みの日は、連続を途切れさせない）。
    since の日までは数えない（その翌日から数える。since="" なら全期間）。
    """
    days = {}  # 日付 → その日の全問が正解か
    for r in rows:
        if r["lang"] != lang or r["date"] <= since:
            continue
        days[r["date"]] = days.get(r["date"], True) and r["correct"] == "1"
    streak = 0
    for day in sorted(days, reverse=True):
        if not days[day]:
            break
        streak += 1
    return streak
