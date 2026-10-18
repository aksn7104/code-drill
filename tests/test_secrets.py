"""秘密情報（パスワード・トークン）と個人の記録が、Git（やコード）に入らないための仕組みの試験

守るもの：.env（パスワード・トークン）、data/（学習の記録・進み具合）、config.yaml（個人の設定）
守り方：
  ・.gitignore で、これらを Git の対象から外す（実際の git で確かめる）
  ・.env の見本（.env.example）は、値を空にして、Git に上げても安全にする
  ・コードや見本に、パスワードを直接書いていないか、全ファイルを走査する
  ・config.yaml にパスワードを書いたら、エラーにして .env に誘導する
  ・.env が Git に入りうる状態（.gitignore に書かれていない・すでに追加済み）なら、通知の前に止める
git が使えない環境では、実際の git を使う試験はスキップする。
説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import notifier  # noqa: E402

from tests.editions import PAID  # noqa: E402
from tests.test_notifier import CliBase  # noqa: E402

HAS_GIT = shutil.which("git") is not None


def git(folder, *args):
    return subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True, timeout=30)


def new_repo(folder):
    git(folder, "init", "-q")
    return folder


class GitignoreTest(unittest.TestCase):
    def test_01_gitignore_entries(self):
        """TC-SEC-01 | データ品質 | .gitignore に、.env・data/・config.yaml が書かれている

        入力：同梱の .gitignore
        期待：.env、.env.*、data/、config.yaml、__pycache__/ の行がある。見本（.env.example）を除外する行がある
        根拠：設計書 §11（Git に上げないもの）。パスワード・記録・個人設定を、うっかり上げないため
        """
        path = ROOT / ".gitignore"
        self.assertTrue(path.exists())
        lines = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()}
        for entry in (".env", ".env.*", "!.env.example", "data/", "config.yaml", "__pycache__/"):
            self.assertIn(entry, lines)

    @unittest.skipUnless(HAS_GIT, "git がない")
    def test_02_gitignore_works_in_real_git(self):
        """TC-SEC-02 | 結合 | 実際の git で、守るものは除外され、見本は除外されない

        入力：同梱の .gitignore を、新しい git リポジトリに置いて、各ファイルを git check-ignore で調べる
        期待：除外される：.env、.env.local、data/log.csv、data/progress.json、config.yaml、__pycache__/x.pyc。除外されない：.env.example、config.example.yaml、drill.py、questions/python/a.yaml
        根拠：書き方を間違えると、見本まで除外したり、パスワードが除外されなかったりするため
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo = new_repo(Path(tmp))
            shutil.copy(ROOT / ".gitignore", repo / ".gitignore")
            ignored = [".env", ".env.local", "data/log.csv", "data/progress.json", "config.yaml", "__pycache__/x.pyc"]
            kept = [".env.example", "config.example.yaml", "drill.py", "questions/python/a.yaml", "docs/不具合票.md"]
            for name in ignored:
                self.assertEqual(git(repo, "check-ignore", "-q", "--", name).returncode, 0, f"除外されていない: {name}")
            for name in kept:
                self.assertEqual(git(repo, "check-ignore", "-q", "--", name).returncode, 1, f"除外されている: {name}")


class ExampleEnvTest(unittest.TestCase):
    def test_03_env_example_has_no_values(self):
        """TC-SEC-03 | データ品質 | .env.example は、使える項目をすべて書き、値はすべて空（Git に上げても安全）

        入力：同梱の .env.example
        期待：DRILL_SMTP_HOST・PORT・SECURITY・USER・PASSWORD、DRILL_MAIL_FROM・TO、DRILL_NTFY_TOPIC・SERVER・TOKEN、DRILL_NOTION_TOKEN・DATABASE_ID の全項目がある。値はどれも空
        根拠：コピーして使う見本に、本物の値を入れた状態で上げてしまう事故を防ぐ。項目の書き忘れも防ぐ
        """
        values = notifier.load_env(ROOT / ".env.example")
        expected = {
            "DRILL_SMTP_HOST", "DRILL_SMTP_PORT", "DRILL_SMTP_SECURITY", "DRILL_SMTP_USER", "DRILL_SMTP_PASSWORD",
            "DRILL_MAIL_FROM", "DRILL_MAIL_TO", "DRILL_NTFY_TOPIC", "DRILL_NTFY_SERVER", "DRILL_NTFY_TOKEN",
        }
        if PAID:  # Notion 連携は有料版だけ
            expected |= {"DRILL_NOTION_TOKEN", "DRILL_NOTION_DATABASE_ID"}
        self.assertEqual(set(values), expected)
        self.assertEqual({k: v for k, v in values.items() if v}, {})

    def test_04_env_example_keys_are_the_ones_the_code_reads(self):
        """TC-SEC-04 | データ品質 | .env.example の項目は、notifier.py が実際に読む項目と一致する（書き間違い・読み漏らしがない）

        入力：notifier.py のコードの中の "DRILL_…" の名前と、.env.example の項目
        期待：コードが読む名前は、すべて .env.example にある（notifier.py と notion_sync.py の両方）
        根拠：見本どおりに書いたのに読まれない、を防ぐ
        """
        source = "".join((ROOT / name).read_text(encoding="utf-8") for name in ("notifier.py", "notion_sync.py") if (ROOT / name).exists())
        # DRILL_MESSAGE は、PowerShell にメッセージを渡す内部の環境変数で、.env の設定ではない
        code_keys = set(re.findall(r'"(DRILL_[A-Z_]+)"', source)) - {"DRILL_MESSAGE"}
        example_keys = set(notifier.load_env(ROOT / ".env.example"))
        self.assertTrue(code_keys)
        self.assertEqual(code_keys - example_keys, set())


class NoHardcodedSecretsTest(unittest.TestCase):
    def test_05_no_secrets_in_shared_files(self):
        """TC-SEC-05 | データ品質 | Git に上がるファイル（コード・見本・文書。試験は除く）に、パスワードやトークンらしい値が直接書かれていない

        入力：プロジェクトの *.py・*.yaml・*.md・.env.example（tests/ と __pycache__ を除く）を走査
        期待：「password/token/secret/api_key = 値」「DRILL_…PASSWORD=値」「DRILL_…TOKEN=値」の、値が空でないものがない
        根拠：パスワードを Git に上げない（個人情報の保護）。コードに直接書くと、上げた瞬間に漏れる
        """
        pattern = re.compile(
            r"""(?ix)
            (?:password|passwd|token|secret|api[_-]?key|DRILL_[A-Z_]*(?:PASSWORD|TOKEN))
            \s*[:=]\s*
            ["']?(?P<value>[^\s"'#,)\]}]+)
            """
        )
        harmless = {"password", "token", "none", "null", "true", "false", "token,", "self", "env"}
        found = []
        for path in ROOT.rglob("*"):
            relative = path.relative_to(ROOT)
            if path.suffix not in (".py", ".yaml", ".md", ".example") or "tests" in relative.parts or "__pycache__" in relative.parts:
                continue
            if "docs" in relative.parts:
                continue  # 報告書は、試験の説明の文章
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                for match in pattern.finditer(line):
                    value = match.group("value")
                    if value.lower() in harmless or not re.search(r"[A-Za-z0-9]", value) or value.startswith(("env", "os.", "self.", "token", "password", "{", "(")):
                        continue
                    found.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(found, [], "秘密情報らしい値が直接書かれています")


class ConfigGuardTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "config.yaml"

    def test_06_config_rejects_secrets(self):
        """TC-SEC-06 | 異常系 | config.yaml にパスワード・トークンなどを書いたら ConfigError にし、.env に書くよう伝える。値は画面に出さない

        入力：password、smtp_password、DRILL_SMTP_PASSWORD、ntfy_token、api_key、secret_word を書いた設定（値は s3cret-pass）
        期待：どれも ConfigError。メッセージに「.env」が出る。「s3cret-pass」は出ない
        根拠：config.yaml は、人に見せたり共有したりしやすい。秘密は .env にだけ書く
        """
        for key in ("password", "smtp_password", "DRILL_SMTP_PASSWORD", "ntfy_token", "api_key", "secret_word"):
            self.path.write_text(f"{key}: s3cret-pass\n", encoding="utf-8")
            with self.assertRaises(config.ConfigError, msg=key) as cm:
                config.load_config(self.path)
            self.assertIn(".env", str(cm.exception))
            self.assertNotIn("s3cret-pass", str(cm.exception))

    def test_07_config_still_ignores_other_unknown_keys(self):
        """TC-SEC-07 | 境界値 | 秘密と関係のない知らない項目は、これまでどおり読み飛ばす

        入力：future_option: 1（秘密らしくない名前）
        期待：エラーにならない
        根拠：将来の項目を、誤って弾かない（TC-CFG の「知らない項目は読み飛ばす」を壊さない）
        """
        self.path.write_text("future_option: 1\n", encoding="utf-8")
        self.assertEqual(config.load_config(self.path)["questions_per_day"], 2)


@unittest.skipUnless(HAS_GIT, "git がない")
class EnvLocationTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.env = self.folder / ".env"
        self.env.write_text("DRILL_NTFY_TOPIC=x\n", encoding="utf-8")

    def test_08_not_ignored_in_repo_is_refused(self):
        """TC-SEC-08 | 異常系 | git のリポジトリの中で、.env が .gitignore に書かれていなければ、NotifyError にする

        入力：git init しただけのフォルダ（.gitignore なし）に .env がある
        期待：NotifyError。メッセージに「.gitignore」が出る。.env の中身は出ない
        根拠：うっかり git add して、パスワードを上げてしまう前に止める
        """
        new_repo(self.folder)
        with self.assertRaises(notifier.NotifyError) as cm:
            notifier.check_env_location(self.env)
        self.assertIn(".gitignore", str(cm.exception))
        self.assertNotIn("DRILL_NTFY_TOPIC", str(cm.exception))

    def test_09_ignored_is_accepted(self):
        """TC-SEC-09 | 正常系 | .gitignore に書かれていれば通る。リポジトリの外（git を使っていない）でも通る

        入力：.gitignore に .env がある／git のリポジトリではないフォルダ
        期待：どちらも例外にならない
        根拠：git を使わない人も、使える
        """
        new_repo(self.folder)
        (self.folder / ".gitignore").write_text(".env\n", encoding="utf-8")
        notifier.check_env_location(self.env)
        with tempfile.TemporaryDirectory() as other:
            plain = Path(other) / ".env"
            plain.write_text("A=1\n", encoding="utf-8")
            notifier.check_env_location(plain)

    def test_10_already_tracked_is_refused(self):
        """TC-SEC-10 | 異常系 | .gitignore に書いてあっても、すでに git に追加済みの .env は、NotifyError にし、外す方法を伝える

        入力：.gitignore に .env がある状態で、git add -f で .env を追加済み
        期待：NotifyError。メッセージに「git rm --cached」が出る
        根拠：追加済みのファイルには、.gitignore が効かない。気づかないまま上げるのを防ぐ
        """
        new_repo(self.folder)
        (self.folder / ".gitignore").write_text(".env\n", encoding="utf-8")
        git(self.folder, "add", "-f", ".env")
        with self.assertRaises(notifier.NotifyError) as cm:
            notifier.check_env_location(self.env)
        self.assertIn("git rm --cached", str(cm.exception))

    def test_11_no_env_or_no_git_passes(self):
        """TC-SEC-11 | 境界値 | .env がなければ何も確かめない。git コマンドがない環境でも止めない

        入力：存在しない .env／git を呼ぶと FileNotFoundError になる環境
        期待：どちらも例外にならない
        根拠：git が入っていない人のPCでも、通知が使えること
        """
        notifier.check_env_location(self.folder / "nothing.env")

        def no_git(*args, **kwargs):
            raise FileNotFoundError("git")

        notifier.check_env_location(self.env, runner=no_git)


@unittest.skipUnless(HAS_GIT, "git がない")
class EnvLocationCliTest(CliBase):
    def test_12_cli_stops_before_sending(self):
        """TC-SEC-12 | 結合 | notify.py は、.env が Git に入りうる状態なら、何も送らずに止まる。直すと送れる

        入力：git init しただけのフォルダで、notifier: email ＋ privacy: standard、.env は正しい／.gitignore に .env を足したあと
        期待：1回目は終了コード1、標準エラーに「.gitignore」、メールは届かない。2回目は終了コード0でメールが1通届く
        根拠：パスワードを使う前に、置き場所の安全を確かめる
        """
        self.start_server()
        new_repo(self.folder)
        self.config.write_text("notifier: email\nprivacy: standard\n", encoding="utf-8")
        p = self.run_notify()
        self.assertEqual(p.returncode, 1)
        self.assertIn(".gitignore", p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(self.server.mails, [])
        (self.folder / ".gitignore").write_text(".env\n", encoding="utf-8")
        p = self.run_notify()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(self.server.mails), 1)

    def test_13_cli_does_not_check_for_local_parts(self):
        """TC-SEC-13 | 境界値 | none・windows のときは .env を使わないので、Git の状態を確かめない

        入力：git init しただけのフォルダで、notifier: none ＋ .env あり
        期待：終了コード0（止まらない）
        根拠：パスワードを使わない設定の人を、邪魔しない
        """
        new_repo(self.folder)
        self.env.write_text("DRILL_SMTP_PASSWORD=x\n", encoding="utf-8")
        self.config.write_text("notifier: none\n", encoding="utf-8")
        self.assertEqual(self.run_notify().returncode, 0)

    def test_14_cli_checks_location_before_reading_env(self):
        """TC-SEC-14 | 異常系 | .env の置き場所の確認は、.env を読む前に行う（中身は、安全だと分かってから読む）

        入力：git init しただけのフォルダで、.env が壊れた形（「名前=値」でない行）
        期待：エラーは Git に関するもの（「.gitignore」が出る）。.env の形のエラー（「行目」）ではない
        根拠：上がりうる状態のファイルを、先に読み込まない
        """
        new_repo(self.folder)
        self.config.write_text("notifier: ntfy\nprivacy: standard\n", encoding="utf-8")
        self.env.write_text("this-is-not-a-pair\n", encoding="utf-8")
        p = self.run_notify()
        self.assertEqual(p.returncode, 1)
        self.assertIn(".gitignore", p.stderr)
        self.assertNotIn("行目", p.stderr)


if __name__ == "__main__":
    unittest.main()
