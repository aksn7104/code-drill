"""問題集と、言語ごとの設定（_language.yaml）を読み込む。"""

from pathlib import Path

import yaml  # YAML を読むための外部ライブラリ（pip install pyyaml）

# _language.yaml がない言語で使う、採点のきまり（既定値）
DEFAULT_RULES = {"case_sensitive": True, "ignore_spaces": True}


class QuestionFileError(Exception):
    """問題集や設定のファイルが読めない、または形式が正しくないときの例外。

    メッセージは、そのまま画面に出して、使う人に伝えられる文章にする。
    """


def _read_yaml(path):
    """YAML ファイルを読み、中身を返す。読めないときは QuestionFileError にする。"""
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise QuestionFileError(f"ファイルが見つかりません: {path}") from None
    except yaml.YAMLError as e:
        raise QuestionFileError(f"YAML の書き方に誤りがあります: {path}\n{e}") from e
    except UnicodeDecodeError:
        raise QuestionFileError(f"文字コードが UTF-8 ではありません: {path}") from None


def load_questions(path):
    """YAML ファイルを読み込み、問題のリスト（辞書のリスト）を返す。

    中身が空のファイルは、問題が0問として、空のリストを返す。
    """
    questions = _read_yaml(path)
    if questions is None:
        return []
    if not isinstance(questions, list) or not all(isinstance(q, dict) for q in questions):
        raise QuestionFileError(
            f"問題集は、問題を並べたリストの形で書いてください"
            f"（各問題は「- id: …」で始めます）: {path}"
        )
    return questions


def load_rules(question_file):
    """問題集と同じフォルダの _language.yaml から、採点のきまりを読む。

    ファイルがなければ、既定値をそのまま返す。
    """
    rules = dict(DEFAULT_RULES)  # 既定値のコピーを作る（元を書き換えないため）
    language_file = Path(question_file).parent / "_language.yaml"
    if language_file.exists():
        settings = _read_yaml(language_file) or {}
        if not isinstance(settings, dict):
            raise QuestionFileError(
                f"_language.yaml は「項目: 値」の形で書いてください: {language_file}"
            )
        rules.update(settings)  # ファイルに書いてある項目で上書きする
    return rules
