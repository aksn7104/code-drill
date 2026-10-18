"""進み具合（progress.py）の単体テスト

説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import progress


class ProgressTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "data" / "progress.json"


class LoadSaveTest(ProgressTestCase):
    def test_01_missing_file_gives_defaults(self):
        """TC-PRG-01 | 正常系 | ファイルがなければ、空の進み具合を返す

        入力：存在しないパス
        期待：langs も pending も空
        根拠：初めて起動したとき
        """
        p = progress.load_progress(self.path)
        self.assertEqual(p["langs"], {})
        self.assertEqual(p["pending"], [])

    def test_02_roundtrip(self):
        """TC-PRG-02 | 正常系 | 保存したものを読み直すと同じになる（フォルダも自動で作る）

        入力：python を level 3・周回 2 にして保存→読み込み
        期待：同じ値。data フォルダがなくても保存できる
        根拠：決定事項（data/progress.json に保存）
        """
        p = progress.load_progress(self.path)
        st = progress.lang_state(p, "python")
        st["level"], st["round"] = 3, 2
        progress.add_pending(p, [{"lang": "python", "file": "u01.yaml", "qid": "p-1"}])
        progress.save_progress(self.path, p)
        q = progress.load_progress(self.path)
        self.assertEqual(q["langs"]["python"]["level"], 3)
        self.assertEqual(q["langs"]["python"]["round"], 2)
        self.assertEqual(q["pending"], [{"lang": "python", "file": "u01.yaml", "qid": "p-1"}])

    def test_03_broken_json(self):
        """TC-PRG-03 | 異常系 | JSON として壊れたファイルは、ProgressError にする

        入力：「{ふぉ」と書いたファイル
        期待：ProgressError（メッセージにファイルの場所を含む）
        根拠：壊れたまま黙って初期化すると、進み具合が消えるため
        """
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{ふぉ", encoding="utf-8")
        with self.assertRaises(progress.ProgressError) as cm:
            progress.load_progress(self.path)
        self.assertIn(str(self.path), str(cm.exception))

    def test_04_wrong_shape(self):
        """TC-PRG-04 | 異常系 | 形が違うファイル（リストなど）は ProgressError にする

        入力：[1, 2]
        期待：ProgressError
        根拠：手で書き換えて壊した場合
        """
        self.path.parent.mkdir(parents=True)
        self.path.write_text("[1, 2]", encoding="utf-8")
        with self.assertRaises(progress.ProgressError):
            progress.load_progress(self.path)

    def test_05_bad_values(self):
        """TC-PRG-05 | 異常系 | level が範囲外・round が数でないときは ProgressError にする

        入力：level 9、または round "x"
        期待：どちらも ProgressError
        根拠：壊れた値で出題を続けないため
        """
        self.path.parent.mkdir(parents=True)
        for bad in ({"python": {"level": 9}}, {"python": {"round": "x"}}):
            self.path.write_text(json.dumps({"langs": bad, "pending": []}), encoding="utf-8")
            with self.assertRaises(progress.ProgressError):
                progress.load_progress(self.path)

    def test_06_japanese_not_escaped(self):
        """TC-PRG-06 | データ品質 | 日本語のファイル名があっても、UTF-8 で保存・復元できる

        入力：unit が「第1章.yaml」
        期待：読み直して同じ
        根拠：Windows の既定の文字コードに依存しないため
        """
        p = progress.load_progress(self.path)
        progress.lang_state(p, "python")["unit"] = "第1章.yaml"
        progress.save_progress(self.path, p)
        self.assertEqual(progress.load_progress(self.path)["langs"]["python"]["unit"], "第1章.yaml")

    def test_07_no_temp_file_left(self):
        """TC-PRG-07 | 正常系 | 保存したあとに、一時ファイルが残らない

        入力：保存を2回
        期待：data フォルダの中は progress.json だけ
        根拠：途中で止まっても壊れないよう、一時ファイルに書いてから置き換えるため
        """
        p = progress.load_progress(self.path)
        progress.save_progress(self.path, p)
        progress.save_progress(self.path, p)
        self.assertEqual([f.name for f in self.path.parent.iterdir()], ["progress.json"])

    def test_08_unwritable(self):
        """TC-PRG-08 | 環境差 | 保存先に書き込めないときは ProgressError にする

        入力：保存先のフォルダの場所に、同名のファイルがある
        期待：ProgressError
        根拠：Traceback を出さず、原因を伝えるため
        """
        self.path.parent.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.write_text("x", encoding="utf-8")
        with self.assertRaises(progress.ProgressError):
            progress.save_progress(self.path, progress.load_progress(self.path / "none"))


class StateTest(ProgressTestCase):
    def test_09_lang_state_defaults(self):
        """TC-PRG-09 | 正常系 | 言語の初期状態は、単元なし・Lv1・周回1・since なし

        入力：まだ無い言語
        期待：unit None、level 1、round 1、since ""
        根拠：決定事項 判断3・4
        """
        st = progress.lang_state(progress.load_progress(self.path), "python")
        self.assertEqual((st["unit"], st["level"], st["round"], st["since"]), (None, 1, 1, ""))

    def test_10_lang_state_is_stored(self):
        """TC-PRG-10 | 正常系 | lang_state が返す辞書を書き換えると、進み具合に反映される

        入力：level を 2 に書き換え
        期待：もう一度 lang_state すると 2
        根拠：drill.py が状態を更新して保存するため
        """
        p = progress.load_progress(self.path)
        progress.lang_state(p, "python")["level"] = 2
        self.assertEqual(progress.lang_state(p, "python")["level"], 2)

    def test_11_add_pending_no_duplicates(self):
        """TC-PRG-11 | 境界値 | 同じ未回答を2回追加しても1件だけ

        入力：同じ内容を2回 add_pending
        期待：pending は1件
        根拠：中断→再起動→中断のくり返し
        """
        p = progress.load_progress(self.path)
        item = {"lang": "python", "file": "u01.yaml", "qid": "p-1"}
        progress.add_pending(p, [item])
        progress.add_pending(p, [dict(item)])
        self.assertEqual(len(p["pending"]), 1)

    def test_12_remove_pending(self):
        """TC-PRG-12 | 正常系 | 回答した問題だけ、未回答から外す

        入力：p-1、p-2 を追加して p-1 を remove
        期待：p-2 だけ残る
        根拠：決定事項 判断1
        """
        p = progress.load_progress(self.path)
        progress.add_pending(p, [{"lang": "python", "file": "u01.yaml", "qid": "p-1"},
                                 {"lang": "python", "file": "u01.yaml", "qid": "p-2"}])
        progress.remove_pending(p, "python", "u01.yaml", "p-1")
        self.assertEqual([i["qid"] for i in p["pending"]], ["p-2"])

    def test_13_remove_missing_is_ok(self):
        """TC-PRG-13 | 異常系 | ないものを外そうとしても、エラーにならない

        入力：空の状態で remove
        期待：何も起きない
        根拠：二重に外す操作で落ちないため
        """
        p = progress.load_progress(self.path)
        progress.remove_pending(p, "python", "u01.yaml", "p-1")
        self.assertEqual(p["pending"], [])

    def test_14_raise_level(self):
        """TC-PRG-14 | 正常系 | 難易度を1つ上げ、since を今日にする

        入力：Lv1 の python に 2026-10-14 で raise_level
        期待：level 2、since "2026-10-14"
        根拠：決定事項 判断4
        """
        p = progress.load_progress(self.path)
        progress.raise_level(p, "python", date(2026, 10, 14))
        st = progress.lang_state(p, "python")
        self.assertEqual((st["level"], st["since"]), (2, "2026-10-14"))

    def test_15_raise_level_cap(self):
        """TC-PRG-15 | 境界値 | Lv5 からは上がらない

        入力：Lv5 で raise_level
        期待：level は 5 のまま
        根拠：難易度は 1〜5
        """
        p = progress.load_progress(self.path)
        progress.lang_state(p, "python")["level"] = 5
        progress.raise_level(p, "python", date(2026, 10, 14))
        self.assertEqual(progress.lang_state(p, "python")["level"], 5)


class LocateUnitTest(unittest.TestCase):
    UNITS = ["u01.yaml", "u02.yaml", "u03.yaml"]

    def test_16_none_starts_at_first(self):
        """TC-PRG-16 | 正常系 | 単元が未設定なら、最初の単元から始める

        入力：state_unit None、何も出題していない
        期待：("u01.yaml", 周回1)
        根拠：決定事項 判断3
        """
        self.assertEqual(progress.locate_unit(self.UNITS, None, 1, lambda u, r: False), ("u01.yaml", 1))

    def test_17_stays_when_not_done(self):
        """TC-PRG-17 | 正常系 | まだ全問を出していない単元には留まる

        入力：state_unit u02、u02 は未完了
        期待：("u02.yaml", 1)
        根拠：決定事項 判断3
        """
        self.assertEqual(progress.locate_unit(self.UNITS, "u02.yaml", 1, lambda u, r: False), ("u02.yaml", 1))

    def test_18_advances_when_done(self):
        """TC-PRG-18 | 正常系 | 全問を出し終えた単元は飛ばして、次の単元へ進む

        入力：u01 だけ完了
        期待：("u02.yaml", 1)
        根拠：決定事項 判断3
        """
        self.assertEqual(progress.locate_unit(self.UNITS, "u01.yaml", 1, lambda u, r: u == "u01.yaml"),
                         ("u02.yaml", 1))

    def test_19_wraps_to_next_round(self):
        """TC-PRG-19 | 境界値 | 最後の単元を終えたら、周回+1 で最初の単元に戻る

        入力：すべての単元が周回1で完了
        期待：("u01.yaml", 2)
        根拠：決定事項 判断3
        """
        self.assertEqual(progress.locate_unit(self.UNITS, "u03.yaml", 1, lambda u, r: r == 1), ("u01.yaml", 2))

    def test_20_unknown_unit_restarts(self):
        """TC-PRG-20 | 異常系 | 進み具合にある単元ファイルが無くなっていたら、最初の単元に戻る

        入力：state_unit が units にない
        期待：("u01.yaml", 周回そのまま)
        根拠：ファイルを消す・名前を変える操作で落ちないため
        """
        self.assertEqual(progress.locate_unit(self.UNITS, "gone.yaml", 2, lambda u, r: False), ("u01.yaml", 2))

    def test_21_single_unit(self):
        """TC-PRG-21 | 境界値 | 単元が1つだけでも、完了すれば周回+1 で同じ単元に戻る

        入力：units が1つ、周回1で完了
        期待：("u01.yaml", 2)
        根拠：1単元だけの言語も使えるため
        """
        self.assertEqual(progress.locate_unit(["u01.yaml"], "u01.yaml", 1, lambda u, r: r == 1), ("u01.yaml", 2))


if __name__ == "__main__":
    unittest.main()
