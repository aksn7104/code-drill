"""設定ファイル（config.yaml）を読む。画面への表示や入力は、ここでは行わない。

設定ファイルがなくても動くように、すべての項目に既定値がある。
"""

from pathlib import Path

import yaml

from notifier import NOTIFIER_NAMES, PRIVACY_LEVELS
from timetable import DAY_NAMES

# 設定ファイルがないとき、または書かれていない項目に使う値
DEFAULT_CONFIG = {
    "days": ["mon", "tue", "wed", "thu", "fri", "sat"],  # 学習する曜日（日曜は休み）
    "languages": None,  # None は、questions/ の下のフォルダから自動で見つける
    "language_rotation": None,  # None は、languages の順に1日ずつ回す
    "questions_per_day": 2,
    "level_up_streak": 2,  # 全問正解の学習日が何日続いたら、難易度を上げる提案をするか
    "characters": {"python": "くりまんじゅう後輩", "sql": "オイシーサー"},  # 言語ごとのキャラ。{} でキャラなし
    "long_day": "sat",  # 長めの読解の問題を出す曜日。none で出さない
    "notifier": "none",  # 通知の部品（none / windows / email / ntfy）。none は通知しない
    "privacy": "strict",  # strict は、PCの外に出る通知（email・ntfy）を使わない。standard は使える
}


class ConfigError(Exception):
    """設定ファイルが読めない、または書き方が正しくないときの例外。

    メッセージは、そのまま画面に出して、使う人に伝えられる文章にする。
    """


def _is_positive_int(value):
    # bool は int の仲間なので、True / False を整数として通さないよう除く
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _check_days(value):
    if not isinstance(value, list) or not all(isinstance(d, str) for d in value):
        raise ConfigError("days は、曜日の名前を並べたリストで書いてください（例：[mon, tue, wed]）")
    days = [d.strip().lower() for d in value]
    for d in days:
        if d not in DAY_NAMES:
            raise ConfigError(
                f"days の「{d}」は曜日の名前ではありません（{', '.join(DAY_NAMES)} から選びます）"
            )
    return days


def _check_languages(value):
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        raise ConfigError("languages は、言語のフォルダ名を並べたリストで書いてください（例：[python, sql]）")
    return value


def _check_rotation(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ConfigError("language_rotation は「言語名: 日数」の形で書いてください（例：sql: 2）")
    for lang, every in value.items():
        if not _is_positive_int(every):
            raise ConfigError(
                f"language_rotation の「{lang}」は、1以上の整数で書いてください（今の値：{every!r}）"
            )
    return value


def _check_questions_per_day(value):
    if not _is_positive_int(value):
        raise ConfigError(f"questions_per_day は、1以上の整数で書いてください（今の値：{value!r}）")
    return value


def _check_level_up_streak(value):
    if not _is_positive_int(value):
        raise ConfigError(f"level_up_streak は、1以上の整数で書いてください（今の値：{value!r}）")
    return value


def _check_characters(value):
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in value.items()):
        raise ConfigError("characters は、「言語: キャラの名前」の形で書いてください（例：{python: 先生}。キャラなしは {}）")
    return dict(value)


def _check_long_day(value):
    if not isinstance(value, str) or value.strip().lower() not in DAY_NAMES + ["none"]:
        raise ConfigError(
            f"long_day は、曜日の名前（{', '.join(DAY_NAMES)}）か none で書いてください（今の値：{value!r}）"
        )
    return value.strip().lower()


def _check_notifier(value):
    names = ", ".join(NOTIFIER_NAMES)
    if not isinstance(value, str) or value.strip().lower() not in NOTIFIER_NAMES:
        raise ConfigError(f"notifier は {names} のどれかで書いてください（今の値：{value!r}）")
    return value.strip().lower()


def _check_privacy(value):
    if not isinstance(value, str) or value.strip().lower() not in PRIVACY_LEVELS:
        raise ConfigError(f"privacy は {', '.join(PRIVACY_LEVELS)} のどちらかで書いてください（今の値：{value!r}）")
    return value.strip().lower()


# 名前にこれらを含む項目は、config.yaml には書けない（秘密は .env に書く）
SECRET_WORDS = ("password", "passwd", "token", "secret", "api_key", "apikey", "api-key")


def _check_not_secret(key):
    name = str(key).strip().lower()
    if name.startswith("drill_") or any(word in name for word in SECRET_WORDS):
        raise ConfigError(
            f"config.yaml には「{key}」を書けません。パスワード・トークンなどの秘密は、.env に書いてください"
            f"（config.yaml は、人に見せたり共有したりすることがあるためです。見本は .env.example）"
        )


CHECKS = {
    "days": _check_days,
    "languages": _check_languages,
    "language_rotation": _check_rotation,
    "questions_per_day": _check_questions_per_day,
    "level_up_streak": _check_level_up_streak,
    "characters": _check_characters,
    "long_day": _check_long_day,
    "notifier": _check_notifier,
    "privacy": _check_privacy,
}


def load_config(path):
    """設定ファイルを読み、設定（辞書）を返す。ファイルがなければ、既定値を返す。"""
    config = dict(DEFAULT_CONFIG)
    path = Path(path)
    if not path.exists():
        return config
    try:
        with open(path, encoding="utf-8") as f:
            settings = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"設定ファイルの YAML の書き方に誤りがあります: {path}\n{e}") from e
    except UnicodeDecodeError:
        raise ConfigError(f"設定ファイルの文字コードが UTF-8 ではありません: {path}") from None
    except OSError as e:
        raise ConfigError(f"設定ファイルを読めません: {path}（{e.strerror}）") from e

    if settings is None:  # 中身が空のファイルは、既定値のまま
        return config
    if not isinstance(settings, dict):
        raise ConfigError(f"設定ファイルは「項目: 値」の形で書いてください: {path}")

    for key, value in settings.items():
        _check_not_secret(key)
        if key in CHECKS:  # 知らない項目は、将来の項目の可能性があるので読み飛ばす
            config[key] = CHECKS[key](value)
    return config
