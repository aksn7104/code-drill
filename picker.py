"""出題する問題を選ぶ。"""

import random


def pick_questions(questions, count, rng=random):
    """問題のリストから、重複しないように count 問をランダムに選ぶ。

    問題の数が count より少ないときは、ある分だけ選ぶ。
    rng には、乱数の元を渡せる。テストでは、結果が毎回同じになる
    random.Random(1) のようなものを渡して使う。
    """
    count = min(count, len(questions))
    return rng.sample(questions, count)


def pick_today(questions, count, asked, last_correct, level, rng=random):
    """今日の問題を、決めた優先順位で count 問選ぶ。

    優先順位（先に書いたものほど先に選ぶ）：
      ① 今の周回でまだ出していない問題
          その中でも、前に間違えた問題 → 今の難易度以下 → それより上の難易度（低い順）
      ② 出題済みで、直近の結果が不正解の問題
      ③ 出題済みで、直近の結果が正解の問題
    同じ順位の中は、ランダム。

    asked は今の周回で出題済みの問題id の集合、last_correct は {問題id: 直近の正誤}、
    level は今の難易度（1〜5）。
    """
    def shuffled(items):
        items = list(items)
        rng.shuffle(items)
        return items

    unseen = [q for q in questions if q["id"] not in asked]
    wrong = [q for q in questions if q["id"] in asked and last_correct.get(q["id"]) is False]
    right = [q for q in questions if q["id"] in asked and last_correct.get(q["id"]) is not False]

    def unseen_key(q):
        previously_wrong = 0 if last_correct.get(q["id"]) is False else 1
        within_level = 0 if q["level"] <= level else 1
        # 今の難易度以下は同順位。それより上は低い順
        rank = 0 if q["level"] <= level else q["level"]
        return (previously_wrong, within_level, rank)

    ordered = sorted(shuffled(unseen), key=unseen_key) + shuffled(wrong) + shuffled(right)
    return ordered[:count]
