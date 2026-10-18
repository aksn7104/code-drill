"""テストを実行し、試験仕様書と試験結果報告を docs/ に書き出す。

使い方（code-drill フォルダの中で）：
    python run_tests.py

    docs/試験仕様書.md      試験項目の一覧（テストの説明から自動で作る）
    docs/試験結果報告.md    今回の実行結果（合否・実施日時・環境）

結果の表を作らず、実行だけしたいときは：
    python -m unittest discover -s tests -t .

終了コード：0＝不合格・エラーなし、1＝不合格・エラーあり
"""

import inspect
import platform
import re
import sys
import traceback
import unittest
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"

# テストの説明（docstring）の1行目：「TC-GRD-01 | 観点 | 試験内容」
HEAD = re.compile(r"^(TC-[A-Z]+-\d+)\s*\|\s*(.+?)\s*\|\s*(.+)$")
# 2行目以降の項目名
FIELDS = [("input", "入力："), ("expect", "期待："), ("basis", "根拠："), ("defect", "不具合：")]

# 試験項目のグループ（IDの2つ目の部分）：(見出し, 試験の種類)
GROUPS = {
    "GRD": ("採点（grading.py）", "単体試験"),
    "PCK": ("出題の選び方（picker.py）", "単体試験"),
    "LDR": ("読み込み（loader.py）", "単体試験"),
    "CHK": ("問題集の検査（checker.py）", "単体試験"),
    "SCH": ("日程と言語の切り替え（timetable.py）", "単体試験"),
    "CFG": ("設定（config.py）", "単体試験"),
    "REC": ("記録（recorder.py）", "単体試験"),
    "HIS": ("記録の集計（history.py）", "単体試験"),
    "PRG": ("進み具合（progress.py）", "単体試験"),
    "SES": ("学習の流れ（session.py。画面を使わない部品）", "単体試験"),
    "GUI": ("ウィンドウの画面（gui.py。仮想の画面で操作）", "画面の試験"),
    "WEB": ("ブラウザの画面（web.py。通信なしの確認と、本物のサーバーの確認）", "画面の試験"),
    "NTF": ("通知（notifier.py・notify.py。実際には送らず、偽のサーバーで確認）", "単体試験・結合試験"),
    "SEC": ("秘密情報・個人の記録を Git に上げない仕組み（.gitignore・.env・設定の検査）", "単体試験・結合試験"),
    "NOT": ("Notion 連携（notion_sync.py）", "単体試験・結合試験"),
    "RPT": ("週間レポート（weekly_report.py）", "単体試験・結合試験"),
    "FUN": ("楽しむ部品（キャラ・すがた・称号・すごろく）", "単体試験"),
    "CMP": ("キャラとすごろくを画面に出す・休みの日と練習のあとの「もう1問」「難易度」", "単体試験・画面の試験"),
    "ART": ("キャラ「くりまんじゅう後輩」「オイシーサー」のイラストと、画面への表示", "単体試験・結合試験"),
    "EXT": ("もう1問・難易度を下げる・Git案内・長めの読解の日", "単体試験・結合試験"),
    "PRM": ("AIへの指示文（prompts/）", "単体試験・結合試験"),
    "REL": ("公開の準備（自動試験の設定・README・AI用の指示文・公開前の点検）", "単体試験・結合試験"),
    "DAT": ("同梱の問題集（questions/ の下のすべてのYAML）", "データ検証"),
    "CLI": ("画面と全体の流れ（drill.py を実際に起動）", "結合試験"),
    "EDN": ("無料版・有料版の書き出し（build_editions.py）", "単体試験・結合試験"),
}

PASS_LIKE = ("合格", "既知の不具合", "スキップ")


def parse_doc(doc):
    """テストの説明を読み取って、辞書にして返す。決まった形でなければ None。"""
    lines = inspect.cleandoc(doc or "").splitlines()
    if not lines:
        return None
    m = HEAD.match(lines[0])
    if not m:
        return None
    info = {"id": m.group(1), "aspect": m.group(2), "title": m.group(3)}
    info.update({key: "" for key, _ in FIELDS})
    for line in lines[1:]:
        for key, label in FIELDS:
            if line.startswith(label):
                info[key] = line[len(label):].strip()
    return info


def flatten(suite):
    """テストの入れ子（スイート）を、テスト1件ずつに開く。"""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def last_line(err):
    """例外の内容から、短い1行を取り出す。"""
    text = traceback.format_exception_only(err[0], err[1])[-1].strip()
    return text if len(text) <= 100 else text[:100] + "…"


class Recorder(unittest.TestResult):
    """テスト1件ごとの結果（合格・不合格など）を記録する。"""

    def __init__(self):
        super().__init__()
        self.outcomes = {}  # テストのid → (結果, 備考)

    def addSuccess(self, test):
        self.outcomes[test.id()] = ("合格", "")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcomes[test.id()] = ("不合格", last_line(err))

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes[test.id()] = ("エラー", last_line(err))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcomes[test.id()] = ("スキップ", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.outcomes[test.id()] = ("既知の不具合", "未対応の不具合として登録済み")

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.outcomes[test.id()] = ("想定外の合格", "直っているので、テストの「既知の不具合」の印を外す")


def collect():
    """テストを集めて実行し、(項目の一覧, 結果の記録) を返す。"""
    suite = unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    tests = list(flatten(suite))
    recorder = Recorder()
    suite.run(recorder)

    items, missing = [], []
    for test in tests:
        method = getattr(test, test._testMethodName)
        info = parse_doc(method.__doc__)
        if info is None:
            missing.append(test.id())
            continue
        result, note = recorder.outcomes.get(test.id(), ("未実行", ""))
        info.update(result=result, note=note)
        items.append(info)
    items.sort(key=lambda i: i["id"])
    return items, missing


def cell(text):
    """Markdown の表に入れられる形にする（| と改行を処理）。"""
    return str(text).replace("|", "\\|").replace("\n", " ")


def group_of(item):
    return item["id"].split("-")[1]


def write_spec(items):
    """試験仕様書を書く。"""
    lines = [
        "# 試験仕様書（コード学習の自動化 汎用版）",
        "",
        "> このファイルは `python run_tests.py` が、テストの説明（tests/ の docstring）から自動で作る。直接は編集しない。",
        "",
        "## 1. 目的",
        "",
        "問題の読み込み・選び方・採点・画面の流れが、設計書（`docs/汎用版_設計書.md`）どおりに動き、",
        "誤った入力や壊れた問題集でも、分かる表示で止まることを確かめる。",
        "",
        "## 2. 試験の種類",
        "",
        "| 種類 | 内容 | 対象 |",
        "|---|---|---|",
        "| 単体試験 | 関数を1つずつ、画面や入力なしで確かめる | grading.py / picker.py / loader.py / recorder.py |",
        "| データ検証 | 同梱の問題集が、設計書の形式どおりに書かれているかを確かめる | questions/ の下のすべてのYAML |",
        "| 結合試験 | drill.py を実際のコマンドとして起動し、入力と画面の出力、終了コードを確かめる | drill.py 全体 |",
        "",
        "## 3. 試験観点",
        "",
        "| 観点 | 内容 |",
        "|---|---|",
        "| 正常系 | 設計書どおりの使い方で、期待どおりに動く |",
        "| 境界値 | 範囲の端、0件、1件、ちょうど同じ数など |",
        "| 異常系 | 誤った入力、壊れたファイル、欠けた項目で、止まり方が分かりやすい |",
        "| 環境差 | 日本語入力（全角）、Windowsの改行やBOM、起動するフォルダの違いなど |",
        "| データ品質 | 問題集のデータが、決まりを守っている |",
        "",
        "## 4. 合格基準",
        "",
        "- 不合格・エラーが0件であること",
        "- 「既知の不具合」（未対応として `docs/不具合票.md` に登録済み）は、件数と内容を報告し、条件付き合格として扱う",
        "",
        "## 5. 実施方法",
        "",
        "```",
        "python run_tests.py                          # 実行して、この仕様書と結果報告を更新する",
        "python -m unittest discover -s tests -t .    # 実行だけ（報告書は作らない）",
        "```",
        "",
        "## 6. 試験項目",
        "",
        f"全 {len(items)} 項目。",
    ]
    for key, (title, kind) in GROUPS.items():
        group = [i for i in items if group_of(i) == key]
        if not group:
            continue
        lines += [
            "",
            f"### {title}（{kind}、{len(group)}項目）",
            "",
            "| ID | 観点 | 試験内容 | 入力・手順 | 期待結果 | 根拠 | 関連不具合 |",
            "|---|---|---|---|---|---|---|",
        ]
        for i in group:
            lines.append(
                f"| {i['id']} | {cell(i['aspect'])} | {cell(i['title'])} | {cell(i['input'])} "
                f"| {cell(i['expect'])} | {cell(i['basis'])} | {cell(i['defect'])} |"
            )
    (DOCS / "試験仕様書.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def judge(counts):
    """全体の判定を返す。"""
    if counts.get("不合格", 0) or counts.get("エラー", 0) or counts.get("想定外の合格", 0):
        return "不合格（修正が必要）"
    if counts.get("既知の不具合", 0):
        return f"条件付き合格（未対応の既知の不具合 {counts['既知の不具合']}件）"
    return "合格"


def write_report(items, counts):
    """試験結果報告を書く。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    env = f"Python {platform.python_version()} / PyYAML {yaml.__version__} / {platform.system()} {platform.release()}"
    lines = [
        "# 試験結果報告（コード学習の自動化 汎用版）",
        "",
        "> このファイルは `python run_tests.py` が自動で作る。直接は編集しない。試験項目は `docs/試験仕様書.md`、不具合の詳細は `docs/不具合票.md` を参照。",
        "",
        "## 1. 実施概要",
        "",
        "| 項目 | 内容 |",
        "|---|---|",
        f"| 実施日時 | {now} |",
        f"| 実施環境 | {env} |",
        f"| 実施方法 | `python run_tests.py`（unittest） |",
        f"| 試験項目数 | {len(items)} |",
        f"| 判定 | **{judge(counts)}** |",
        "",
        "## 2. 結果の集計",
        "",
        "| 結果 | 件数 |",
        "|---|---|",
    ]
    for status in ("合格", "不合格", "エラー", "既知の不具合", "想定外の合格", "スキップ", "未実行"):
        if counts.get(status, 0) or status in ("合格", "不合格", "エラー"):
            lines.append(f"| {status} | {counts.get(status, 0)} |")
    lines += ["", "観点別の集計：", "", "| 観点 | 項目数 | 合格 | 既知の不具合 | 不合格・エラー |", "|---|---|---|---|---|"]
    aspects = []
    for i in items:
        if i["aspect"] not in aspects:
            aspects.append(i["aspect"])
    for aspect in aspects:
        part = [i for i in items if i["aspect"] == aspect]
        ok = sum(1 for i in part if i["result"] == "合格")
        known = sum(1 for i in part if i["result"] == "既知の不具合")
        bad = len(part) - ok - known
        lines.append(f"| {aspect} | {len(part)} | {ok} | {known} | {bad} |")

    open_items = [i for i in items if i["result"] == "既知の不具合"]
    lines += ["", "## 3. 未対応の既知の不具合", ""]
    if open_items:
        lines += ["| ID | 試験内容 | 関連不具合 |", "|---|---|---|"]
        for i in open_items:
            lines.append(f"| {i['id']} | {cell(i['title'])} | {cell(i['defect'])} |")
    else:
        lines.append("なし")

    bad_items = [i for i in items if i["result"] in ("不合格", "エラー", "想定外の合格")]
    lines += ["", "## 4. 不合格・エラー", ""]
    if bad_items:
        lines += ["| ID | 試験内容 | 結果 | 内容 |", "|---|---|---|---|"]
        for i in bad_items:
            lines.append(f"| {i['id']} | {cell(i['title'])} | {i['result']} | {cell(i['note'])} |")
    else:
        lines.append("なし")

    lines += ["", "## 5. 試験項目ごとの結果"]
    for key, (title, kind) in GROUPS.items():
        group = [i for i in items if group_of(i) == key]
        if not group:
            continue
        lines += ["", f"### {title}", "", "| ID | 観点 | 試験内容 | 結果 | 関連不具合 |", "|---|---|---|---|---|"]
        for i in group:
            lines.append(
                f"| {i['id']} | {cell(i['aspect'])} | {cell(i['title'])} | {i['result']} | {cell(i['defect'])} |"
            )
    (DOCS / "試験結果報告.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    items, missing = collect()
    if missing:
        print("説明（docstring）が決まった形でないテストがあります:")
        for test_id in missing:
            print(f"  {test_id}")

    counts = {}
    for i in items:
        counts[i["result"]] = counts.get(i["result"], 0) + 1

    DOCS.mkdir(exist_ok=True)
    write_spec(items)
    write_report(items, counts)

    print(f"試験項目 {len(items)} 件")
    for status, n in counts.items():
        print(f"  {status}: {n}")
    for i in items:
        if i["result"] not in PASS_LIKE:
            print(f"  [{i['result']}] {i['id']} {i['title']}  {i['note']}")
    print(f"判定: {judge(counts)}")
    print("書き出し: docs/試験仕様書.md, docs/試験結果報告.md")

    failed = counts.get("不合格", 0) + counts.get("エラー", 0) + counts.get("想定外の合格", 0) + len(missing)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
