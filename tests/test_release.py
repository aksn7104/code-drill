"""公開の準備（段階8）の試験：自動試験の設定・README・AI用の指示文・公開前の点検

ここで試すのは「公開してよい状態か」。GitHub への送信（公開）そのものは行わない。
GitHub Actions が実際に動くこと（特に Windows）は、公開したあとでないと確かめられない。
説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import ast
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checker  # noqa: E402
from tests.editions import PAID, paid_only  # noqa: E402

HAS_GIT = shutil.which("git") is not None
IGNORE = shutil.ignore_patterns("__pycache__", ".git")


def source_files():
    """公開するコード（試験を除く、ルートの *.py）。"""
    return sorted(p for p in ROOT.glob("*.py"))


def copy_project(dest):
    shutil.copytree(ROOT, dest / "project", ignore=IGNORE)
    return dest / "project"


class DependencyTest(unittest.TestCase):
    def test_01_requirements_cover_imports(self):
        """TC-REL-01 | データ品質 | 標準ライブラリ以外で使っているのは PyYAML だけで、requirements.txt に書かれている

        入力：ルートの *.py と tests/*.py の import 文を調べる
        期待：標準ライブラリとこのプロジェクトの部品を除くと yaml だけ。requirements.txt に PyYAML がある
        根拠：初めて使う人が `pip install -r requirements.txt` だけで動かせるように。書き忘れ・不要な依存を防ぐ
        """
        local = {p.stem for p in ROOT.glob("*.py")} | {"tests"}
        found = set()
        for path in source_files() + sorted((ROOT / "tests").glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    found |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    found.add(node.module.split(".")[0])
        third_party = {m for m in found if m not in sys.stdlib_module_names and m not in local}
        self.assertEqual(third_party, {"yaml"})
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        self.assertIn("pyyaml", requirements)


class WorkflowTest(unittest.TestCase):
    def load(self):
        path = ROOT / ".github" / "workflows" / "tests.yml"
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        # YAML では on が True として読まれることがある
        triggers = data.get("on", data.get(True))
        return data, triggers, text

    def test_02_workflow_runs_on_windows_and_linux(self):
        """TC-REL-02 | データ品質 | 自動試験の設定が、push と pull request で、Windows と Linux の両方で、Python 3.13 の試験を動かす

        入力：.github/workflows/tests.yml
        期待：トリガーに push・pull_request。os に windows-latest と ubuntu-latest。python-version に 3.13。依存の導入（requirements.txt）と `python run_tests.py` を実行する。時間切れの設定（timeout-minutes）がある
        根拠：計画（段階8：WindowsとLinuxの自動試験）。Windows での実行は、ここまで一度も確かめられていない
        """
        data, triggers, text = self.load()
        self.assertIn("push", triggers)
        self.assertIn("pull_request", triggers)
        job = next(iter(data["jobs"].values()))
        self.assertEqual(set(job["strategy"]["matrix"]["os"]), {"windows-latest", "ubuntu-latest"})
        self.assertIn("3.13", [str(v) for v in job["strategy"]["matrix"].get("python-version", [])])
        self.assertIn("requirements.txt", text)
        self.assertIn("run_tests.py", text)
        self.assertIn("timeout-minutes", job)

    def test_03_workflow_is_least_privilege(self):
        """TC-REL-03 | 異常系 | 自動試験の設定は、読み取り権限だけを持ち、秘密（secrets）を使わない

        入力：.github/workflows/tests.yml
        期待：permissions が contents: read だけ。「secrets.」の文字がない。リポジトリへの書き込みや公開をする手順（git push・gh release など）がない
        根拠：試験のための設定が、パスワードの流出や、意図しない公開の入り口にならないように
        """
        data, _, text = self.load()
        self.assertEqual(data.get("permissions"), {"contents": "read"})
        for word in ("secrets.", "git push", "gh release", "gh repo"):
            self.assertNotIn(word, text)

    def test_04_run_tests_fails_when_a_test_fails(self):
        """TC-REL-04 | 異常系 | 試験が1つでも失敗したら、run_tests.py は 0 以外の終了コードで終わる（自動試験が「失敗」と表示するため）

        入力：プロジェクトのコピーに、わざと失敗する試験を1件だけ置いて run_tests.py を実行
        期待：終了コードが 0 ではない
        根拠：終了コードが常に 0 だと、壊れていても自動試験が「成功」になってしまう
        """
        with tempfile.TemporaryDirectory() as tmp:
            project = copy_project(Path(tmp))
            # コピーの試験は、わざと失敗する1件だけにする（この試験自身を呼び出して、無限に増えないように）
            for old_test in (project / "tests").glob("test_*.py"):
                old_test.unlink()
            (project / "tests" / "test_zz_forced_failure.py").write_text(
                '"""x"""\nimport unittest\n\n\nclass T(unittest.TestCase):\n    def test_01_fail(self):\n'
                '        """TC-DAT-99 | 異常系 | わざと失敗\n\n        入力：なし\n        期待：失敗\n        根拠：試験用\n        """\n        self.fail("forced")\n',
                encoding="utf-8",
            )
            p = subprocess.run([sys.executable, "run_tests.py"], cwd=project, capture_output=True, text=True, timeout=600)
            self.assertNotEqual(p.returncode, 0)


class ReadmeTest(unittest.TestCase):
    def setUp(self):
        path = ROOT / "README.md"
        self.assertTrue(path.exists())
        self.text = path.read_text(encoding="utf-8")

    def test_05_readme_sections(self):
        """TC-REL-05 | データ品質 | README に、初めての人に必要な項目（何ができるか・導入・使い方・設定・通知・個人情報・試験・問題集の増やし方・制限）がある

        入力：README.md の見出し
        期待：見出しの文字に、「できること」「導入」「使い方」「設定」「通知」「個人情報」「試験」「問題集」「制限」が含まれる
        根拠：公開した人が、READMEだけで始められるように
        """
        headings = " ".join(re.findall(r"^#+\s*(.+)$", self.text, flags=re.M))
        for word in ("できること", "導入", "使い方", "設定", "通知", "個人情報", "試験", "問題集", "制限"):
            self.assertIn(word, headings, f"見出しに「{word}」がない")

    def test_06_readme_commands_exist(self):
        """TC-REL-06 | データ品質 | README に書かれたコマンド（python ○○.py）と指定（--○○）は、実際にある

        入力：README.md の「python xxx.py」と「--xxx」を、すべて拾う
        期待：xxx.py はプロジェクトに存在する。--xxx はいずれかのコードに書かれている。drill.py・gui.py・web.py・notify.py・run_tests.py はすべて紹介されている
        根拠：書かれた手順どおりに動かない、を防ぐ
        """
        scripts = set(re.findall(r"python\s+([A-Za-z0-9_./]+\.py)", self.text))
        for name in scripts:
            self.assertTrue((ROOT / name).exists(), f"存在しない: {name}")
        for name in ("drill.py", "gui.py", "web.py", "notify.py", "run_tests.py"):
            if name == "web.py" and not PAID:  # ブラウザ版は有料版だけ
                continue
            self.assertIn(name, scripts, f"READMEで紹介されていない: {name}")
        code = "\n".join(p.read_text(encoding="utf-8") for p in source_files())
        for option in set(re.findall(r"(?<![-\w])(--[a-z][a-z-]+)", self.text)) - {"--help", "--version"}:  # --help は argparse の標準、--version は python 自身の指定（python --version）
            self.assertTrue(f'"{option}"' in code, f"存在しない指定: {option}")

    def test_07_readme_is_honest_about_limits(self):
        """TC-REL-07 | データ品質 | README が、確かめられていないこと（Windows の実行・見た目・本物の通知）と、「絶対に漏れない」とは言い切れないことを書いている

        入力：README.md
        期待：「未確認」の文字がある。「Windows」「見た目」の記述がある。「絶対」と書く場合は、否定の形（言い切れない など）に限る
        根拠：誇張しない。使う人が、自分の環境で確かめる必要があると分かるように
        """
        self.assertIn("未確認", self.text)
        self.assertIn("Windows", self.text)
        self.assertIn("見た目", self.text)
        for line in self.text.splitlines():
            if "絶対" in line:
                self.assertRegex(line, r"(ない|できません|言い切れ)")


class PromptTest(unittest.TestCase):
    def setUp(self):
        path = ROOT / "prompts" / "generate_questions.md"
        self.assertTrue(path.exists())
        self.text = path.read_text(encoding="utf-8")

    def test_08_prompt_has_required_parts(self):
        """TC-REL-08 | データ品質 | AI に貼る指示文に、決めるべき項目（言語・単元・難易度・問題数）の差し込み場所と、形式の必須項目、守る決まりがある

        入力：prompts/generate_questions.md の、AI に貼り付ける部分
        期待：貼り付ける部分に {言語}・{単元}・{難易度}・{問題数} がある。必須項目（id, unit, level, type, question, code, answer, explanation）がすべて書かれている。「--check」の案内がある。answer を引用符で囲む決まりがある
        根拠：設計書 §9。AI が作った問題集が、形式の検査に通るように
        """
        # 貼り付ける部分（````text … ````）の中に、差し込み場所と決まりがあること（説明の表にあるだけでは足りない）
        match = re.search(r"````text\n(.*?)\n````", self.text, flags=re.S)
        self.assertIsNotNone(match, "貼り付ける部分（````text）がない")
        paste = match.group(1)
        for placeholder in ("{言語}", "{単元}", "{難易度}", "{問題数}"):
            self.assertIn(placeholder, paste)
        for key in checker.REQUIRED_KEYS:
            self.assertIn(key, paste)
        self.assertIn("引用符", paste)
        self.assertIn("--check", self.text)

    def test_09_prompt_example_passes_the_checker(self):
        """TC-REL-09 | 結合 | 指示文の中の YAML の見本が、実際の形式検査（--check と同じ）に通る

        入力：指示文の中の ```yaml … ``` の見本を、言語フォルダに置いて検査
        期待：誤りが 0 件（問題が1問以上ある）
        根拠：見本どおりに作らせた問題集が、検査で弾かれる、という矛盾を防ぐ
        """
        blocks = re.findall(r"```yaml\n(.*?)```", self.text, flags=re.S)
        self.assertTrue(blocks, "YAML の見本がない")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "sample"
            folder.mkdir()
            (folder / "_language.yaml").write_text("name: Sample\ncase_sensitive: true\nignore_spaces: true\n", encoding="utf-8")
            (folder / "u01.yaml").write_text(blocks[0], encoding="utf-8")
            result = checker.check_paths([folder])
        self.assertEqual([str(p) for p in result.problems], [])
        self.assertGreaterEqual(result.question_count, 1)


class LicenseTest(unittest.TestCase):
    def test_13_license_is_polyform_strict_without_personal_name(self):
        """TC-REL-13 | データ品質 | LICENSE が PolyForm Strict 1.0.0 の全文で、著作権者に個人の名前・メールアドレスが入っていない。README に書かれている

        入力：LICENSE、README.md
        期待：「PolyForm Strict License 1.0.0」と、再配布・改変を許さない一文（other than distributing the software or making changes or new works）と、無保証の一文（comes as is, without any warranty）を含む。「Required Notice: Copyright 年 名前」の行がある。メールアドレスを含まない。README に「PolyForm Strict」「再配布」とライセンスの項目がある
        根拠：本人の希望（公開はするが、再配布は防ぎたい。2026-10-18。MIT は誰でも再配布・販売できるため、やめた）。ライセンスがないと、公開しても他の人は使えない扱いになる。個人名は本人が決めるまで入れない
        """
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        for phrase in (
            "PolyForm Strict License 1.0.0",
            "other than distributing the software or making changes or new works based on the software",
            "the software comes as is, without any warranty or condition",
        ):
            self.assertIn(phrase, text)
        self.assertRegex(text, r"(?m)^Required Notice: Copyright 20\d\d \S+")
        self.assertNotRegex(text, r"@")
        self.assertNotIn("Permission is hereby granted", text)  # MIT の文面が残っていない
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("PolyForm Strict", readme)
        self.assertIn("再配布", readme)
        self.assertRegex(readme, r"(?m)^#+\s*ライセンス")


@unittest.skipUnless(HAS_GIT, "git がない")
class DryRunTest(unittest.TestCase):
    """公開の予行演習：プロジェクトのコピーに、わざと秘密のファイルを置き、git add -A で何が上がるかを調べる。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        project = copy_project(Path(cls._tmp.name))
        (project / ".env").write_text("DRILL_SMTP_PASSWORD=hunter2hunter2\n", encoding="utf-8")
        (project / ".env.local").write_text("X=1\n", encoding="utf-8")
        (project / "data").mkdir(exist_ok=True)
        (project / "data" / "log.csv").write_text("date,qid\n2026-10-14,p-1\n", encoding="utf-8")
        (project / "data" / "progress.json").write_text("{}", encoding="utf-8")
        (project / "config.yaml").write_text("notifier: email\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
        # -z：日本語のファイル名（docs/不具合票.md など）を、引用符つきの別の表記にせず、そのまま受け取る
        out = subprocess.run(
            ["git", "-C", str(project), "ls-files", "-z"], capture_output=True, check=True
        ).stdout.decode("utf-8")
        cls.project = project
        cls.tracked = [name for name in out.split("\0") if name]

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_10_secrets_and_records_are_not_tracked(self):
        """TC-REL-10 | 異常系 | git add -A しても、.env・data/・config.yaml は上がらない（予行演習）

        入力：コピーに本物らしい .env・.env.local・data/log.csv・data/progress.json・config.yaml を置いて git add -A
        期待：git ls-files（上がるファイル）に、これらがない
        根拠：公開前に、パスワードと個人の記録が上がらないことを、実際の git で確かめる
        """
        for name in (".env", ".env.local", "data/log.csv", "data/progress.json", "config.yaml"):
            self.assertNotIn(name, self.tracked)

    def test_11_release_files_are_tracked(self):
        """TC-REL-11 | 正常系 | 公開に必要なファイルは、すべて上がる

        入力：同じ予行演習の git ls-files
        期待：README.md・requirements.txt・.gitignore・.env.example・config.example.yaml・.github/workflows/tests.yml・prompts/generate_questions.md・ルートの *.py・tests/*.py・questions の問題集が含まれる
        根拠：除外のしすぎで、動かないリポジトリにならないように
        """
        required = [
            "README.md", "requirements.txt", ".gitignore", ".env.example", "config.example.yaml",
            ".github/workflows/tests.yml", "prompts/generate_questions.md", "LICENSE",
            "questions/python/_language.yaml", "questions/python/batting_01_variables.yaml",
            "questions/sql/_language.yaml", "tests/__init__.py",
        ]
        required += [p.name for p in source_files()]
        required += [f"tests/{p.name}" for p in (ROOT / "tests").glob("test_*.py")]
        for name in required:
            self.assertIn(name, self.tracked, f"上がらない: {name}")

    def test_14_docs_are_scanned_too(self):
        """TC-REL-14 | データ品質 | 日本語の名前のファイル（docs/不具合票.md など）も、上がるファイルの一覧に正しく入っていて、走査の対象になる

        入力：予行演習の git ls-files（日本語のファイル名を含む）
        期待：docs/不具合票.md・docs/試験仕様書.md・docs/試験結果報告.md が一覧にあり、実際に読める
        根拠：一覧の表記が崩れて（引用符つきの文字化けのように）、報告書が個人情報の点検から漏れる、という見落としを防ぐ
        """
        for name in ("docs/不具合票.md", "docs/試験仕様書.md", "docs/試験結果報告.md"):
            self.assertIn(name, self.tracked)
            self.assertTrue((self.project / name).is_file())

    def test_12_no_personal_information_in_tracked_files(self):
        """TC-REL-12 | 異常系 | 上がるファイルに、メールアドレス（example.com 以外）・自分のPCの個人フォルダの場所（各OSのホームの下）が含まれない

        入力：予行演習で上がるファイルをすべて走査（バイナリは除く）
        期待：メールアドレスは example.com / example.org / example.net のものだけ。個人のフォルダの場所（ホームの下の場所）がない。報告書（docs/）も対象
        根拠：作者や利用者の個人情報が、公開物に混ざらないように
        """
        email = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
        home = re.compile(r"(/home/[a-z][\w.-]*/|/Users/[A-Za-z][\w.-]*/|[A-Za-z]:\\Users\\)")
        found = []
        for name in self.tracked:
            path = self.project / name
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for m in email.finditer(text):
                if m.group(1).lower() not in ("example.com", "example.org", "example.net"):
                    found.append(f"{name}: メールアドレス {m.group(0)}")
            for m in home.finditer(text):
                if name == "tests/test_release.py":
                    continue  # この試験自身の正規表現
                found.append(f"{name}: 個人の場所 {m.group(0)}")
        self.assertEqual(found, [])


class ReadmeContentTest(unittest.TestCase):
    """README の中身が、コードの実際の内容と食い違っていないか（段階9-5）。"""

    def setUp(self):
        self.text = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_15_readme_lists_every_config_key(self):
        """TC-REL-15 | データ品質 | README の設定の表に、設定（config.py の DEFAULT_CONFIG）の全項目が載っている

        入力：README.md の設定の表と、config.DEFAULT_CONFIG
        期待：DEFAULT_CONFIG の項目名は、すべて README に `項目名` の形で書かれている
        根拠：設定を足したのに説明を書き忘れる、を防ぐ（使う人は README だけで設定できるように）
        """
        import config

        for key in config.DEFAULT_CONFIG:
            if key == "characters" and not PAID:  # キャラは有料版だけ
                continue
            self.assertIn(f"`{key}`", self.text, f"READMEに設定「{key}」がない")

    def test_16_table_of_contents_links_exist(self):
        """TC-REL-16 | データ品質 | README の目次のリンクは、すべて実在の見出しを指している

        入力：目次の [ ](#…) と、見出し（GitHub と同じ規則で作った名前）
        期待：リンク先がすべて見出しにある
        根拠：目次を押しても飛ばない、を防ぐ
        """
        def anchor(heading):
            return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")

        anchors = {anchor(h) for h in re.findall(r"^#{2,3}\s*(.+)$", self.text, flags=re.M)}
        links = re.findall(r"\]\(#([^)]+)\)", self.text)
        self.assertTrue(links)
        for link in links:
            self.assertIn(link, anchors, f"目次のリンク先がない: #{link}")

    def test_17_readme_explains_notification_setup(self):
        """TC-REL-17 | データ品質 | README の通知の説明に、手で試す・時刻を決める・変える・確認する・やめる・来ないときの確認、が書かれている

        入力：README.md
        期待：schtasks の Create・Change・Query・Run・Delete、--when start・--when remind、「通知が来ないとき」、windows・ntfy・email の手順がある
        根拠：本人の希望（通知の確認方法・時間調整のやり方を README にきちんと書く）
        """
        for word in ("schtasks /Create", "schtasks /Change", "schtasks /Query", "schtasks /Run", "schtasks /Delete",
                     "--when start", "--when remind", "通知が来ないとき", "手順A", "手順B", "手順C", "/ST"):
            self.assertIn(word, self.text, word)

    def test_18_readme_introduces_all_features(self):
        """TC-REL-18 | データ品質 | README が、週間レポート・Notion・AI への指示文（問題集と言語の設定）・言語の選び方を紹介している

        入力：README.md
        期待：weekly_report.py、notion_sync.py、prompts/generate_questions.md、prompts/generate_language.md、languages、language_rotation の記述がある
        根拠：本人の希望（言語の選択方法などを詳しく）。機能を足したのに紹介しない、を防ぐ
        """
        words = ["prompts/generate_questions.md", "prompts/generate_language.md", "`languages`", "`language_rotation`", "--level-down"]
        if PAID:  # 週間レポートと Notion 連携は有料版だけ
            words += ["python weekly_report.py", "python notion_sync.py"]
        for word in words:
            self.assertIn(word, self.text, word)

    @paid_only
    def test_19_readme_badge_names_match_the_code(self):
        """TC-REL-19 | データ品質 | README の称号の表が、コード（fun.BADGES）の称号と一致している

        入力：README.md の称号の表と、fun.BADGES
        期待：BADGES の名前と条件の説明が、すべて README にある
        根拠：説明とコードの食い違いを防ぐ
        """
        import importlib

        fun = importlib.import_module("fun")  # 有料版だけにあるモジュール（無料版の試験では、このテストは飛ばす）

        for key, emoji, name, description in fun.BADGES:
            self.assertIn(name, self.text, name)
            self.assertIn(description, self.text, description)


if __name__ == "__main__":
    unittest.main()
