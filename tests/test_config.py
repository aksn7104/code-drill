"""設定（config.py）の単体テスト

説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import tempfile
import unittest
from pathlib import Path

import config


class ConfigTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "config.yaml"

    def write(self, text):
        self.path.write_text(text, encoding="utf-8")


class LoadConfigTest(ConfigTestCase):
    def test_01_no_file_gives_defaults(self):
        """TC-CFG-01 | 正常系 | 設定ファイルがなければ、既定値で動く

        入力：存在しないパス
        期待：days=月〜土、languages=None（自動）、language_rotation=None、questions_per_day=2
        根拠：設計書 §2（設定がなくても、python drill.py で2問が解ける）
        """
        c = config.load_config(self.path)
        self.assertEqual(c["days"], ["mon", "tue", "wed", "thu", "fri", "sat"])
        self.assertIsNone(c["languages"])
        self.assertIsNone(c["language_rotation"])
        self.assertEqual(c["questions_per_day"], 2)

    def test_02_override(self):
        """TC-CFG-02 | 正常系 | 書いた項目だけが上書きされ、ほかは既定値のまま

        入力：languages と language_rotation と questions_per_day だけ書いた設定
        期待：その3項目は書いた値。days は既定のまま
        根拠：設計書 §7
        """
        self.write("languages: [python, sql]\nlanguage_rotation:\n  sql: 2\nquestions_per_day: 3\n")
        c = config.load_config(self.path)
        self.assertEqual(c["languages"], ["python", "sql"])
        self.assertEqual(c["language_rotation"], {"sql": 2})
        self.assertEqual(c["questions_per_day"], 3)
        self.assertEqual(len(c["days"]), 6)

    def test_03_empty_file(self):
        """TC-CFG-03 | 境界値 | 中身が空の設定ファイルは、既定値で動く

        入力：0バイトのファイル
        期待：既定値（エラーにならない）
        根拠：見本をコピーして、中身を全部消した場合
        """
        self.write("")
        self.assertEqual(config.load_config(self.path)["questions_per_day"], 2)

    def test_04_uppercase_days(self):
        """TC-CFG-04 | 境界値 | 曜日は大文字で書いても読める

        入力：days: [Mon, SAT]
        期待：["mon", "sat"]
        根拠：書き方のゆれに強くする
        """
        self.write("days: [Mon, SAT]\n")
        self.assertEqual(config.load_config(self.path)["days"], ["mon", "sat"])

    def test_05_invalid_day_name(self):
        """TC-CFG-05 | 異常系 | 曜日の名前が正しくないとエラーにする

        入力：days: [mon, funday]
        期待：ConfigError（メッセージに funday が入る）
        根拠：打ち間違いに気づけるように
        """
        self.write("days: [mon, funday]\n")
        with self.assertRaises(config.ConfigError) as cm:
            config.load_config(self.path)
        self.assertIn("funday", str(cm.exception))

    def test_06_not_a_mapping(self):
        """TC-CFG-06 | 異常系 | 「項目: 値」の形でない設定はエラーにする

        入力：リスト形式（- python）の設定
        期待：ConfigError
        根拠：形式の違うYAMLを渡された場合
        """
        self.write("- python\n- sql\n")
        with self.assertRaises(config.ConfigError):
            config.load_config(self.path)

    def test_07_broken_yaml(self):
        """TC-CFG-07 | 異常系 | YAMLの書き方が誤っているとエラーにする

        入力：引用符が閉じていないYAML
        期待：ConfigError（Traceback にならない）
        根拠：設計書 §5（エラーは1行で伝える）
        """
        self.write('languages: ["python\n')
        with self.assertRaises(config.ConfigError):
            config.load_config(self.path)

    def test_08_bad_rotation_values(self):
        """TC-CFG-08 | 異常系 | 切り替えの数が1以上の整数でないとエラーにする

        入力：sql: 0、sql: "2"（文字）、sql: true、sql: 1.5
        期待：どれも ConfigError
        根拠：0 では割り算の余りが計算できない。true は YAML では整数ではなく真偽値
        """
        for bad in ("0", '"2"', "true", "1.5", "-1"):
            self.write(f"language_rotation:\n  sql: {bad}\n")
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load_config(self.path)

    def test_09_bad_questions_per_day(self):
        """TC-CFG-09 | 異常系 | 1日の問題数が1以上の整数でないとエラーにする

        入力：questions_per_day: 0、"2"、true
        期待：どれも ConfigError
        根拠：設計書 §7
        """
        for bad in ("0", '"2"', "true"):
            self.write(f"questions_per_day: {bad}\n")
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load_config(self.path)

    def test_10_languages_must_be_text_list(self):
        """TC-CFG-10 | 異常系 | languages が文字のリストでないとエラーにする

        入力：languages: python（リストでない）、languages: [python, 3]
        期待：どちらも ConfigError
        根拠：書き方の間違いに気づけるように
        """
        for bad in ("python", "[python, 3]"):
            self.write(f"languages: {bad}\n")
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load_config(self.path)

    def test_11_example_file_is_valid(self):
        """TC-CFG-11 | データ品質 | 同梱の設定の見本（config.example.yaml）が、そのまま読める

        入力：config.example.yaml
        期待：エラーにならず、questions_per_day などが読める
        根拠：見本をコピーして使う人が、最初に書き間違えないように
        """
        example = Path(__file__).resolve().parent.parent / "config.example.yaml"
        self.assertTrue(example.exists())
        c = config.load_config(example)
        self.assertGreaterEqual(c["questions_per_day"], 1)

    def test_12_level_up_streak_default(self):
        """TC-CFG-12 | 正常系 | level_up_streak を書かなければ 2 になる

        入力：設定ファイルなし
        期待：level_up_streak は 2
        根拠：決定事項 判断4（2日連続で難易度を提案）
        """
        self.assertEqual(config.load_config(self.path)["level_up_streak"], 2)

    def test_13_level_up_streak_set(self):
        """TC-CFG-13 | 正常系 | level_up_streak を書けば、その値になる

        入力：level_up_streak: 3
        期待：3
        根拠：判断4（設定で変えられる）
        """
        self.path.write_text("level_up_streak: 3\n", encoding="utf-8")
        self.assertEqual(config.load_config(self.path)["level_up_streak"], 3)

    def test_14_level_up_streak_invalid(self):
        """TC-CFG-14 | 異常系 | level_up_streak が 0・負・文字・小数なら ConfigError にする

        入力：0、-1、abc、1.5
        期待：どれも ConfigError
        根拠：他の数値の設定と同じ扱い
        """
        for bad in ("0", "-1", "abc", "1.5"):
            self.path.write_text(f"level_up_streak: {bad}\n", encoding="utf-8")
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load_config(self.path)

    def test_15_notifier_default_and_set(self):
        """TC-CFG-15 | 正常系 | notifier を書かなければ none（通知しない）。windows・email は書けて、大文字でもよい

        入力：設定なし／notifier: windows／notifier: EMAIL
        期待：none／windows／email
        根拠：設計書 §7・§8（通知は任意。なくても動く）
        """
        self.assertEqual(config.load_config(self.path)["notifier"], "none")
        self.path.write_text("notifier: windows\n", encoding="utf-8")
        self.assertEqual(config.load_config(self.path)["notifier"], "windows")
        self.path.write_text("notifier: EMAIL\n", encoding="utf-8")
        self.assertEqual(config.load_config(self.path)["notifier"], "email")

    def test_16_notifier_invalid(self):
        """TC-CFG-16 | 異常系 | notifier に知らない名前・文字以外を書いたら ConfigError にし、選べる名前を伝える

        入力：sms、数字の 1、リスト
        期待：どれも ConfigError。メッセージに none・windows・email・ntfy が出る
        根拠：書き間違いに気づけるように（黙って通知なしにしない）
        """
        for bad in ("sms", "1", "[email]"):
            self.path.write_text(f"notifier: {bad}\n", encoding="utf-8")
            with self.assertRaises(config.ConfigError, msg=bad) as cm:
                config.load_config(self.path)
            for name in ("none", "windows", "email", "ntfy"):
                self.assertIn(name, str(cm.exception))


    def test_17_privacy_default_and_set(self):
        """TC-CFG-17 | 正常系 | privacy を書かなければ strict（PCの外に出る通知を使わない）。standard を書けばそうなる

        入力：設定なし／privacy: standard／privacy: STRICT
        期待：strict／standard／strict
        根拠：うっかり外に出さないことを既定にする（個人情報を守る設定を、使う人が選べる）
        """
        self.assertEqual(config.load_config(self.path)["privacy"], "strict")
        self.path.write_text("privacy: standard\n", encoding="utf-8")
        self.assertEqual(config.load_config(self.path)["privacy"], "standard")
        self.path.write_text("privacy: STRICT\n", encoding="utf-8")
        self.assertEqual(config.load_config(self.path)["privacy"], "strict")

    def test_18_privacy_invalid(self):
        """TC-CFG-18 | 異常系 | privacy に知らない値・文字以外を書いたら ConfigError にし、選べる値を伝える。ゆるい方に倒さない

        入力：none、off、true、1
        期待：どれも ConfigError。メッセージに strict と standard が出る
        根拠：書き間違いで、黙って外に出る設定にならないように
        """
        for bad in ("none", "off", "true", "1"):
            self.path.write_text(f"privacy: {bad}\n", encoding="utf-8")
            with self.assertRaises(config.ConfigError, msg=bad) as cm:
                config.load_config(self.path)
            self.assertIn("strict", str(cm.exception))
            self.assertIn("standard", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
