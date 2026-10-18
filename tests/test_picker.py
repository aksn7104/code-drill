"""出題の選び方（picker.py）の単体テスト

説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import random
import unittest

from picker import pick_questions, pick_today

QUESTIONS = [{"id": f"q{i}"} for i in range(1, 6)]  # q1〜q5 の5問


class PickQuestionsTest(unittest.TestCase):
    def test_01_requested_count(self):
        """TC-PCK-01 | 正常系 | 指定した数だけ選ぶ

        入力：5問のリストから2問
        期待：2問が返る
        根拠：設計書 §5-5、§7（questions_per_day）
        """
        self.assertEqual(len(pick_questions(QUESTIONS, 2, random.Random(1))), 2)

    def test_02_no_duplicates(self):
        """TC-PCK-02 | 正常系 | 同じ問題が重複して選ばれない

        入力：5問のリストから3問を、乱数の元を変えて50回
        期待：どの回も、選ばれた3問のidがすべて異なる
        根拠：設計書 §5-5（同じ問題を2回出さない）
        """
        for seed in range(50):
            ids = [q["id"] for q in pick_questions(QUESTIONS, 3, random.Random(seed))]
            self.assertEqual(len(ids), len(set(ids)))

    def test_03_fewer_than_count(self):
        """TC-PCK-03 | 境界値 | 問題が要求数より少ないときは、ある分だけ選ぶ

        入力：1問のリストから2問
        期待：1問が返り、例外は出ない
        根拠：設計書 §5-5
        """
        self.assertEqual(len(pick_questions(QUESTIONS[:1], 2, random.Random(1))), 1)

    def test_04_exactly_count(self):
        """TC-PCK-04 | 境界値 | 問題の数と要求数がちょうど同じ

        入力：5問のリストから5問
        期待：5問すべてが返る
        根拠：設計書 §5-5
        """
        picked = pick_questions(QUESTIONS, 5, random.Random(1))
        self.assertEqual(sorted(q["id"] for q in picked), [q["id"] for q in QUESTIONS])

    def test_05_empty_list(self):
        """TC-PCK-05 | 境界値 | 問題が0問のリストから選ぶ

        入力：空のリストから2問
        期待：空のリストが返り、例外は出ない
        根拠：設計書 §5-5
        """
        self.assertEqual(pick_questions([], 2, random.Random(1)), [])

    def test_06_zero_count(self):
        """TC-PCK-06 | 境界値 | 0問を指定したときは、何も選ばない

        入力：5問のリストから0問
        期待：空のリストが返る
        根拠：設計書 §7（questions_per_day）
        """
        self.assertEqual(pick_questions(QUESTIONS, 0, random.Random(1)), [])

    def test_07_negative_count(self):
        """TC-PCK-07 | 異常系 | 負の数を指定すると、エラーになる

        入力：5問のリストから-1問
        期待：ValueError（黙って何かを返さない）
        根拠：設定ミスに気づけるようにするため
        """
        with self.assertRaises(ValueError):
            pick_questions(QUESTIONS, -1, random.Random(1))

    def test_08_reproducible(self):
        """TC-PCK-08 | 正常系 | 乱数の元が同じなら、同じ結果になる（テストの再現性）

        入力：同じ乱数の元（7）で2回選ぶ
        期待：2回の結果が同じ
        根拠：テストの結果が毎回同じになるようにするため
        """
        a = pick_questions(QUESTIONS, 2, random.Random(7))
        b = pick_questions(QUESTIONS, 2, random.Random(7))
        self.assertEqual(a, b)

    def test_09_original_not_changed(self):
        """TC-PCK-09 | 正常系 | 元の問題のリストを書き換えない

        入力：選ぶ前後で、元のリストを比べる
        期待：同じ
        根拠：副作用がないことの確認
        """
        before = list(QUESTIONS)
        pick_questions(QUESTIONS, 2, random.Random(1))
        self.assertEqual(QUESTIONS, before)

    def test_10_every_question_can_be_picked(self):
        """TC-PCK-10 | 正常系 | どの問題も選ばれうる（特定の問題に偏らない）

        入力：5問のリストから2問を、乱数の元を変えて200回
        期待：5問すべてが、少なくとも1回は選ばれる
        根拠：設計書 §5-5（ランダムに選ぶ）
        """
        seen = set()
        for seed in range(200):
            seen.update(q["id"] for q in pick_questions(QUESTIONS, 2, random.Random(seed)))
        self.assertEqual(seen, {q["id"] for q in QUESTIONS})


def qs(*pairs):
    """(id, level) の並びから問題のリストを作る。"""
    return [{"id": i, "level": lv} for i, lv in pairs]


def ids(questions):
    return [q["id"] for q in questions]


class PickTodayTest(unittest.TestCase):
    def test_11_unseen_first(self):
        """TC-PCK-11 | 正常系 | 今の周回でまだ出していない問題を先に選ぶ

        入力：4問のうち a・b は出題済み、2問を選ぶ
        期待：c・d が選ばれる
        根拠：決定事項 判断2（②今の周回で未出題）
        """
        q = qs(("a", 1), ("b", 1), ("c", 1), ("d", 1))
        got = pick_today(q, 2, {"a", "b"}, {}, 1, random.Random(1))
        self.assertEqual(set(ids(got)), {"c", "d"})

    def test_12_wrong_before_correct(self):
        """TC-PCK-12 | 正常系 | 未出題が足りないときは、直近が不正解の問題、次に正解の問題の順で補う

        入力：4問すべて出題済み。a は不正解、b・c・d は正解。2問を選ぶ
        期待：a が入る
        根拠：決定事項 判断2（③出題済みで不正解 → ④正解）
        """
        q = qs(("a", 1), ("b", 1), ("c", 1), ("d", 1))
        for seed in range(20):
            got = pick_today(q, 2, {"a", "b", "c", "d"}, {"a": False, "b": True, "c": True, "d": True},
                             1, random.Random(seed))
            self.assertIn("a", ids(got))

    def test_13_unseen_beats_wrong(self):
        """TC-PCK-13 | 正常系 | 未出題は、出題済みの不正解より先に選ぶ

        入力：a は出題済み・不正解、b・c は未出題。2問を選ぶ
        期待：b・c（a は選ばれない）
        根拠：決定事項 判断2（順序 ②が③より先）
        """
        q = qs(("a", 1), ("b", 1), ("c", 1))
        got = pick_today(q, 2, {"a"}, {"a": False}, 1, random.Random(1))
        self.assertEqual(set(ids(got)), {"b", "c"})

    def test_14_level_priority(self):
        """TC-PCK-14 | 正常系 | 未出題のうち、今の難易度以下を先に選ぶ

        入力：Lv2 のとき、未出題が Lv1・Lv2・Lv3・Lv4。2問を選ぶ
        期待：Lv1・Lv2 の問題
        根拠：決定事項 判断4（現在の難易度以下から出す）
        """
        q = qs(("l1", 1), ("l2", 2), ("l3", 3), ("l4", 4))
        for seed in range(20):
            got = pick_today(q, 2, set(), {}, 2, random.Random(seed))
            self.assertEqual(set(ids(got)), {"l1", "l2"})

    def test_15_higher_levels_ascending(self):
        """TC-PCK-15 | 境界値 | 今の難易度以下が足りないときは、上の難易度を低い順に補う

        入力：Lv1 のとき、未出題が Lv1・Lv3・Lv2・Lv5。3問を選ぶ
        期待：Lv1・Lv2・Lv3
        根拠：1単元は4問・1日2問で、難易度を厳密に絞ると問題が足りなくなるため（優先順位として扱う）
        """
        q = qs(("a", 1), ("c", 3), ("b", 2), ("e", 5))
        got = pick_today(q, 3, set(), {}, 1, random.Random(1))
        self.assertEqual(set(ids(got)), {"a", "b", "c"})

    def test_16_previously_wrong_first(self):
        """TC-PCK-16 | 正常系 | 未出題のうち、前の周回で間違えた問題を先に選ぶ

        入力：未出題は a・b・c。b は前の周回で不正解。1問を選ぶ
        期待：b
        根拠：決定事項 判断2（復習の優先）
        """
        q = qs(("a", 1), ("b", 1), ("c", 1))
        for seed in range(20):
            got = pick_today(q, 1, set(), {"a": True, "b": False}, 1, random.Random(seed))
            self.assertEqual(ids(got), ["b"])

    def test_17_count_larger_than_available(self):
        """TC-PCK-17 | 境界値 | 問題の数より多く頼まれたら、ある分だけ返す（重複しない）

        入力：2問のリストから5問
        期待：2問、重複なし
        根拠：1単元が少ないとき
        """
        got = pick_today(qs(("a", 1), ("b", 1)), 5, set(), {}, 1, random.Random(1))
        self.assertEqual(sorted(ids(got)), ["a", "b"])

    def test_18_reproducible(self):
        """TC-PCK-18 | 正常系 | 同じ乱数の元なら、同じ結果になる（同順位の中はランダム）

        入力：同順位の問題8問から3問を、同じ seed で2回
        期待：同じ結果
        根拠：試験を毎回同じ条件で再現するため
        """
        q = qs(*[(f"q{i}", 1) for i in range(8)])
        a = pick_today(q, 3, set(), {}, 1, random.Random(5))
        b = pick_today(q, 3, set(), {}, 1, random.Random(5))
        self.assertEqual(ids(a), ids(b))


if __name__ == "__main__":
    unittest.main()
