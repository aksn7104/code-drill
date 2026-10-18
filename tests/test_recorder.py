"""記録（recorder.py）の単体テスト

説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import tempfile
import unittest
from datetime import date
from pathlib import Path

import recorder

HEADER = "date,qid,lang,unit,correct,level,round,note"
SAMPLE_Q = {"id": "py-1", "unit": "打率を計算する（割り算・float）", "level": 2}


def row(correct=True, **changes):
    """試験用の記録を1行ぶん作る。"""
    r = recorder.make_row(SAMPLE_Q, correct, "python", date(2026, 10, 17))
    r.update(changes)
    return r


class RecorderTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.log = self.folder / "log.csv"


class MakeRowTest(unittest.TestCase):
    def test_03_make_row_correct(self):
        """TC-REC-03 | 正常系 | 正解の記録が、決まった列と値で作られる

        入力：Lv2・id「py-1」の問題に正解、言語「python」、日付 2026-10-17
        期待：date=2026-10-17、qid=py-1、lang=python、unit=問題の単元、correct=1、level=2、round=1、note=空
        根拠：設計書 §6（log.csv の列）
        """
        r = recorder.make_row(SAMPLE_Q, True, "python", date(2026, 10, 17))
        self.assertEqual(
            r,
            {
                "date": "2026-10-17",
                "qid": "py-1",
                "lang": "python",
                "unit": "打率を計算する（割り算・float）",
                "correct": 1,
                "level": 2,
                "round": 1,
                "note": "",
            },
        )
        self.assertEqual(list(r), recorder.FIELDNAMES)  # 列の順番も決まりどおり

    def test_04_make_row_wrong_and_default_date(self):
        """TC-REC-04 | 正常系 | 不正解は 0、日付を渡さなければ今日になる

        入力：不正解、日付なし
        期待：correct=0、date は今日の日付（YYYY-MM-DD）
        根拠：設計書 §6
        """
        r = recorder.make_row(SAMPLE_Q, False, "python")
        self.assertEqual(r["correct"], 0)
        self.assertEqual(r["date"], date.today().isoformat())


class AppendLogTest(RecorderTestCase):
    def test_01_create_new_file(self):
        """TC-REC-01 | 正常系 | ファイルがなければ作り、見出しの行と記録の行を書く

        入力：存在しないパスに、1問ぶんの記録を追記
        期待：1行目が見出し、2行目が記録。読み込むと1件
        根拠：設計書 §5-8（log.csv に1問1行で追記する）
        """
        recorder.append_log(self.log, [row()])
        lines = self.log.read_text(encoding="utf-8-sig").splitlines()
        self.assertEqual(lines[0], HEADER)
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(recorder.read_log(self.log)), 1)

    def test_02_append_keeps_single_header(self):
        """TC-REC-02 | 正常系 | 続けて追記しても、見出しは1つのまま、行が増える

        入力：1問ぶんを2回、続けて追記
        期待：見出し1行＋記録2行。1回目の記録が消えない
        根拠：設計書 §5-8
        """
        recorder.append_log(self.log, [row(qid="a")])
        recorder.append_log(self.log, [row(qid="b")])
        lines = self.log.read_text(encoding="utf-8-sig").splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines.count(HEADER), 1)
        self.assertEqual([r["qid"] for r in recorder.read_log(self.log)], ["a", "b"])

    def test_05_japanese_and_bom_once(self):
        """TC-REC-05 | 環境差 | 日本語が文字化けせず、BOMはファイルの先頭に1つだけ（Excelで開ける）

        入力：日本語の単元名を、3回追記
        期待：読み込んでも日本語が同じ。先頭にBOMがあり、ファイル全体でBOMは1つだけ
        根拠：Excel は BOM がない UTF-8 の CSV を、日本語が文字化けして開くことがあるため
        """
        for _ in range(3):
            recorder.append_log(self.log, [row()])
        data = self.log.read_bytes()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(data.count(b"\xef\xbb\xbf"), 1)
        self.assertEqual(recorder.read_log(self.log)[0]["unit"], SAMPLE_Q["unit"])

    def test_06_creates_missing_folders(self):
        """TC-REC-06 | 境界値 | 記録先のフォルダがなくても、作って書く

        入力：まだ存在しない2階層のフォルダの下のパス
        期待：フォルダごと作られ、記録が書かれる
        根拠：初回の実行では data/ フォルダがないため
        """
        deep = self.folder / "data" / "sub" / "log.csv"
        recorder.append_log(deep, [row()])
        self.assertEqual(len(recorder.read_log(deep)), 1)

    def test_07_special_characters(self):
        """TC-REC-07 | 境界値 | カンマ・引用符・改行を含む値も、壊れずに記録・読み込みできる

        入力：単元名に「a,b "c"」と改行、メモにカンマ
        期待：読み込むと、書いたとおりの文字列。行数が増えない
        根拠：CSV の区切り文字や改行が、値の中に入る場合
        """
        tricky = 'a,b "c"\nd'
        recorder.append_log(self.log, [row(unit=tricky, note="x,y")])
        loaded = recorder.read_log(self.log)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["unit"], tricky)
        self.assertEqual(loaded[0]["note"], "x,y")

    def test_08_empty_existing_file(self):
        """TC-REC-08 | 境界値 | 0バイトの既存ファイルには、見出しから書く

        入力：中身が空のファイルに追記
        期待：見出し1行＋記録1行
        根拠：ファイルだけ作ってある場合（手で空のファイルを作ったとき）
        """
        self.log.write_bytes(b"")
        recorder.append_log(self.log, [row()])
        lines = self.log.read_text(encoding="utf-8-sig").splitlines()
        self.assertEqual(lines[0], HEADER)
        self.assertEqual(len(lines), 2)

    def test_13_existing_file_without_bom(self):
        """TC-REC-13 | 環境差 | BOMなしの既存ファイルにも、追記できる

        入力：見出しだけを書いた、BOMなしのUTF-8のファイルに追記
        期待：エラーにならず、1件が追記される
        根拠：他のソフトで保存し直したファイルを想定
        """
        self.log.write_text(HEADER + "\r\n", encoding="utf-8")
        recorder.append_log(self.log, [row()])
        self.assertEqual(len(recorder.read_log(self.log)), 1)

    def test_10_header_mismatch(self):
        """TC-REC-10 | 異常系 | 見出しが違う既存ファイルには追記せず、エラーにする

        入力：「a,b,c」の見出しのファイルに追記
        期待：LogFileError。ファイルの中身は変わらない
        根拠：別の形式のファイルを壊さないため
        """
        original = b"a,b,c\r\n1,2,3\r\n"
        self.log.write_bytes(original)
        with self.assertRaises(recorder.LogFileError):
            recorder.append_log(self.log, [row()])
        self.assertEqual(self.log.read_bytes(), original)  # 改行コードも含め、1バイトも変わらない

    def test_11_path_is_folder(self):
        """TC-REC-11 | 異常系 | 記録先がフォルダのときは、エラーにする

        入力：記録先にフォルダを指定
        期待：LogFileError（例外の種類が OSError のままにならない）
        根拠：誤った場所の指定でも、分かるエラーにする
        """
        with self.assertRaises(recorder.LogFileError):
            recorder.append_log(self.folder, [row()])


class ReadLogTest(RecorderTestCase):
    def test_09_missing_file(self):
        """TC-REC-09 | 境界値 | 記録ファイルがまだないときは、空のリストを返す

        入力：存在しないパス
        期待：空のリスト（エラーにならない）
        根拠：初回の実行では、記録がまだないため
        """
        self.assertEqual(recorder.read_log(self.log), [])

    def test_12_invalid_bytes(self):
        """TC-REC-12 | 異常系 | UTF-8として読めない文字が混じった記録は、エラーにする

        入力：見出しのあとに、UTF-8として正しくないバイト列
        期待：LogFileError
        根拠：別の文字コード（Shift_JIS など）で保存し直された場合
        """
        self.log.write_bytes(HEADER.encode("utf-8") + b"\r\n" + b"\x82\xa0\r\n")
        with self.assertRaises(recorder.LogFileError):
            recorder.read_log(self.log)


class CheckWritableTest(RecorderTestCase):
    def test_14_writable_ok(self):
        """TC-REC-14 | 正常系 | 書き込める記録ファイルなら、確認が通り、中身は変わらない

        入力：1件の記録がある、普通のファイル
        期待：エラーにならない。確認の前後でファイルの中身が同じ
        根拠：問題を出す前の確認で、記録を壊さないため
        """
        recorder.append_log(self.log, [row()])
        before = self.log.read_bytes()
        recorder.check_writable(self.log)
        self.assertEqual(self.log.read_bytes(), before)

    def test_15_missing_file_ok(self):
        """TC-REC-15 | 境界値 | ファイルがまだない（初回）ときも、確認が通り、ファイルは作らない

        入力：存在しないパス
        期待：エラーにならない。ファイルもフォルダも作られない
        根拠：確認だけで、空のファイルを残さないため
        """
        target = self.folder / "data" / "log.csv"
        recorder.check_writable(target)
        self.assertFalse(target.exists())
        self.assertFalse(target.parent.exists())

    def test_16_locked_file(self):
        """TC-REC-16 | 環境差 | Excelなどで開いていて書き込めないときは、閉じるよう伝えるエラーにする

        入力：書き込みを開くと PermissionError になる記録ファイル（Windowsでソフトが開いている状態を再現）
        期待：LogFileError。メッセージに「開いている」と「閉じて」が入る
        根拠：Windowsは、開いているファイルへの書き込みを許さない。Linuxでは再現できないため、書き込みの失敗を作り出して確かめる
        """
        from unittest import mock

        recorder.append_log(self.log, [row()])
        denied = PermissionError(13, "Permission denied")
        with mock.patch("recorder.open", side_effect=denied, create=True):
            with self.assertRaises(recorder.LogFileError) as cm:
                recorder.check_writable(self.log)
        self.assertIn("開いている", str(cm.exception))
        self.assertIn("閉じて", str(cm.exception))

    def test_17_locked_file_on_append(self):
        """TC-REC-17 | 環境差 | 追記の最中に書き込めなくなったときも、同じ案内のエラーにする

        入力：確認のあとで、書き込みの瞬間にだけ PermissionError になる
        期待：LogFileError。メッセージに「閉じて」が入る（OSError のままにならない）
        根拠：問題に答えている間に、ほかのソフトでファイルを開かれた場合
        """
        from unittest import mock

        recorder.append_log(self.log, [row()])
        denied = PermissionError(13, "Permission denied")
        real_open = open

        def fake_open(path, mode="r", *args, **kwargs):
            if "a" in mode:
                raise denied
            return real_open(path, mode, *args, **kwargs)

        with mock.patch("recorder.open", side_effect=fake_open, create=True):
            with self.assertRaises(recorder.LogFileError) as cm:
                recorder.append_log(self.log, [row()])
        self.assertIn("閉じて", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
