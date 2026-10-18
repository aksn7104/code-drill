"""記録からの集計（history.py）の単体テスト

説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
記録の行は read_log の結果と同じ形（値はすべて文字列）で用意する。
"""

import unittest

import history


def row(date, qid, correct, lang="python", rnd=1):
    return {"date": date, "qid": qid, "lang": lang, "unit": "u", "correct": str(int(correct)),
            "level": "1", "round": str(rnd), "note": ""}


class AskedInRoundTest(unittest.TestCase):
    def test_01_collects_ids(self):
        """TC-HIS-01 | 正常系 | 指定した言語・周回で出題済みの問題idを集める

        入力：python の周回1に2問、周回2に1問、sql の周回1に1問の記録
        期待：python の周回1は {p-1, p-2} だけ
        根拠：決定事項 判断2・3（今の周回で出した問題を数える）
        """
        rows = [row("2026-10-01", "p-1", 1), row("2026-10-01", "p-2", 0),
                row("2026-10-02", "p-3", 1, rnd=2), row("2026-10-02", "s-1", 1, lang="sql")]
        self.assertEqual(history.asked_in_round(rows, "python", 1), {"p-1", "p-2"})

    def test_02_empty(self):
        """TC-HIS-02 | 境界値 | 記録が空なら、空の集合を返す

        入力：記録なし
        期待：空の集合
        根拠：初めて起動したとき
        """
        self.assertEqual(history.asked_in_round([], "python", 1), set())

    def test_03_round_is_text(self):
        """TC-HIS-03 | データ品質 | 記録の周回が文字列でも、数と比べられる

        入力：round が "1" の行と、周回 1（整数）の指定
        期待：一致する
        根拠：read_log は値を文字列で返す
        """
        self.assertEqual(history.asked_in_round([row("2026-10-01", "p-1", 1)], "python", 1), {"p-1"})


class LastResultsTest(unittest.TestCase):
    def test_04_last_wins(self):
        """TC-HIS-04 | 正常系 | 同じ問題を何度も出したときは、最後の結果を使う

        入力：p-1 が 不正解→正解、p-2 が 正解→不正解 の記録
        期待：p-1 は True、p-2 は False
        根拠：決定事項 判断2（直近の結果が不正解の問題を優先）
        """
        rows = [row("2026-10-01", "p-1", 0), row("2026-10-01", "p-2", 1),
                row("2026-10-02", "p-1", 1), row("2026-10-02", "p-2", 0)]
        self.assertEqual(history.last_results(rows, "python"), {"p-1": True, "p-2": False})

    def test_05_other_language_ignored(self):
        """TC-HIS-05 | 正常系 | 別の言語の記録は混ざらない

        入力：sql の記録だけ
        期待：python の結果は空
        根拠：言語ごとに進むため
        """
        self.assertEqual(history.last_results([row("2026-10-01", "s-1", 1, lang="sql")], "python"), {})


class PerfectStreakTest(unittest.TestCase):
    def test_06_counts_consecutive_days(self):
        """TC-HIS-06 | 正常系 | 全問正解の学習日が連続した数を返す

        入力：3日続けて全問正解の記録
        期待：3
        根拠：決定事項 判断4（2日連続の全問正解で難易度を提案）
        """
        rows = [row(f"2026-10-0{d}", f"p-{d}", 1) for d in (1, 2, 3)]
        self.assertEqual(history.perfect_streak(rows, "python"), 3)

    def test_07_wrong_breaks(self):
        """TC-HIS-07 | 境界値 | 不正解がある日で連続が途切れる

        入力：1日目 全問正解、2日目 1問不正解、3日目 全問正解
        期待：1（3日目だけ）
        根拠：判断4
        """
        rows = [row("2026-10-01", "p-1", 1), row("2026-10-02", "p-2", 1), row("2026-10-02", "p-3", 0),
                row("2026-10-03", "p-4", 1)]
        self.assertEqual(history.perfect_streak(rows, "python"), 1)

    def test_08_since_is_exclusive(self):
        """TC-HIS-08 | 境界値 | since の日までは数えない（その翌日から数える）

        入力：10-01〜10-03 が全問正解。since="2026-10-02"
        期待：1（10-03 だけ）
        根拠：難易度を上げた日までの実績で、すぐ次の提案をしないため
        """
        rows = [row(f"2026-10-0{d}", f"p-{d}", 1) for d in (1, 2, 3)]
        self.assertEqual(history.perfect_streak(rows, "python", since="2026-10-02"), 1)

    def test_09_no_rows(self):
        """TC-HIS-09 | 境界値 | 記録がなければ 0

        入力：記録なし
        期待：0
        根拠：初めて起動したとき
        """
        self.assertEqual(history.perfect_streak([], "python"), 0)

    def test_10_other_language_ignored(self):
        """TC-HIS-10 | 正常系 | 別の言語の記録は数えない（sql の日は python の連続を途切れさせない）

        入力：python が 10-01 と 10-03 に全問正解、sql が 10-02 に不正解
        期待：python の連続は 2
        根拠：言語ごとに進むため
        """
        rows = [row("2026-10-01", "p-1", 1), row("2026-10-02", "s-1", 0, lang="sql"),
                row("2026-10-03", "p-2", 1)]
        self.assertEqual(history.perfect_streak(rows, "python"), 2)


if __name__ == "__main__":
    unittest.main()
