"""通知の部品。メッセージを1つ受け取って、知らせる。画面への表示や入力は、ここでは行わない。

どの部品も同じ形（メッセージ（文字）を1つ受け取る関数）なので、設定の notifier を書き換えるだけで差し替えられる。

    send = make_notifier("email", load_env(".env"))
    send("今日の学習の時間です")

部品：
    none     何もしない（通知を使わない人用。既定）
    windows  Windows の画面の右下に、トースト通知を出す（Windows だけ）
    email    メールを送る。送り先などの設定は .env に書く（下記）
    ntfy     スマホなどに、プッシュ通知を送る（ntfy というアプリ。iPhone・Android 対応）。設定は .env に書く（下記）

PCの外に出る部品（email・ntfy）は、config.yaml の privacy が standard のときだけ使える（既定の strict では断る）。
どの部品でも、送る文章は notify.py が作る決まった一文だけで、記録（問題・正誤など）は含めない。

メールの設定（.env に「名前=値」で書く。Git には上げない。見本は .env.example）：
    DRILL_SMTP_HOST       メールサーバーの名前（例：smtp.gmail.com）
    DRILL_SMTP_PORT       ポート番号（例：587）
    DRILL_MAIL_FROM       送り主のアドレス
    DRILL_MAIL_TO         送り先のアドレス（カンマで区切ると複数）
    DRILL_SMTP_SECURITY   省略可。starttls（既定）/ ssl / none（暗号化なし。自分のPCの中だけで使う）
    DRILL_SMTP_USER       省略可。ログインが要るサーバーのとき、ユーザー名
    DRILL_SMTP_PASSWORD   省略可。同じく、パスワード（ユーザー名と両方が必要）

ntfy の設定（.env）：
    DRILL_NTFY_TOPIC      送り先の名前。10文字以上の英数字・- ・_ で、推測されにくいものにする（知っている人は誰でも読める）
    DRILL_NTFY_SERVER     省略可。既定は https://ntfy.sh。自分で立てたサーバーを使うときに書く（このPC以外への http は不可）
    DRILL_NTFY_TOKEN      省略可。アクセス制限のあるサーバー用のトークン
"""

import smtplib
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlsplit

NOTIFIER_NAMES = ("none", "windows", "email", "ntfy")

# PCの外に出る部品。privacy が strict のときは使えない。部品を足したときは、ここに入れるか決める
EXTERNAL_NOTIFIERS = ("email", "ntfy")

PRIVACY_LEVELS = ("strict", "standard")

NTFY_DEFAULT_SERVER = "https://ntfy.sh"
NTFY_TOPIC_PATTERN = re.compile(r"[A-Za-z0-9_-]{10,}")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")

SMTP_REQUIRED = ("DRILL_SMTP_HOST", "DRILL_SMTP_PORT", "DRILL_MAIL_FROM", "DRILL_MAIL_TO")
SECURITY_MODES = ("starttls", "ssl", "none")
TIMEOUT_SECONDS = 30

# Windows のトースト通知を出す PowerShell の命令。メッセージは、命令文には入れず、環境変数 DRILL_MESSAGE から読む
# （メッセージの中身が、命令として実行されないようにするため）
TOAST_SCRIPT = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
    "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
    "$n = $t.GetElementsByTagName('text');"
    "$n.Item(0).AppendChild($t.CreateTextNode('code-drill')) | Out-Null;"
    "$n.Item(1).AppendChild($t.CreateTextNode($env:DRILL_MESSAGE)) | Out-Null;"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('code-drill').Show("
    "[Windows.UI.Notifications.ToastNotification]::new($t))"
)


class NotifyError(Exception):
    """通知の設定が正しくない、または通知を送れなかったときの例外。

    メッセージは、そのまま画面に出して、使う人に伝えられる文章にする（パスワードは入れない）。
    """


def load_env(path):
    """.env を読み、{名前: 値} の辞書を返す。ファイルがなければ空の辞書。

    空行と # で始まる行は飛ばす。値の前後の空白と、全体を囲む引用符（" か '）は除く。
    """
    path = Path(path)
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise NotifyError(f"{path.name} の文字コードが UTF-8 ではありません: {path}") from None
    except OSError as e:
        raise NotifyError(f"{path.name} を読めません: {path}（{e.strerror}）") from e
    values = {}
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not sep or not name:
            # 行の中身（パスワードかもしれない）は、画面に出さない
            raise NotifyError(f"{path.name} の{number}行目が「名前=値」の形ではありません")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values


def check_env_location(path, runner=subprocess.run):
    """.env が Git に上がってしまう状態でないかを確かめる。上がりうるなら NotifyError にする。

    git のリポジトリの中で、.env が .gitignore で除外されていない、またはすでに git に追加されているときは、止める。
    .env がない・git のリポジトリではない・git コマンドがない、ときは何もしない（確かめようがないため）。
    """
    path = Path(path)
    if not path.exists():
        return
    try:
        result = runner(
            ["git", "-C", str(path.parent), "check-ignore", "-q", "--", path.name],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return
    if result.returncode == 1:  # 0＝除外されている／1＝除外されていない（追加済みも含む）／128＝リポジトリではない
        raise NotifyError(
            f"{path.name} が Git に上がってしまう状態です（パスワードが漏れるおそれがあります）。"
            f"①.gitignore に「{path.name}」を書いてください（同梱の .gitignore には書いてあります）。"
            f"②すでに git に追加してしまっているときは「git rm --cached {path.name}」で外してください。"
            f"パスワードを一度でも上げてしまったときは、そのパスワードを変更してください"
        )


def check_privacy(name, privacy):
    """privacy の設定で、この部品を使ってよいかを確かめる。だめなら NotifyError にする。

    strict：PCの外に出る部品（EXTERNAL_NOTIFIERS）は使えない。standard：すべて使える。
    """
    if privacy not in PRIVACY_LEVELS:
        raise NotifyError(f"privacy は {', '.join(PRIVACY_LEVELS)} のどちらかで書いてください（今の値：{privacy}）")
    if privacy == "strict" and name == "notion":
        raise NotifyError(
            "privacy が strict（既定）のため、学習の記録をPCの外（Notion）に送れません。"
            "使うときは、config.yaml に「privacy: standard」と書いてください"
            "（送られるのは、問題の id・単元の名前・正誤・難易度・日付です。問題文やコードは送りません）。"
            "PCの外に出さないなら、この機能は使わないでください"
        )
    if privacy == "strict" and name in EXTERNAL_NOTIFIERS:
        raise NotifyError(
            f"privacy が strict（既定）のため、PCの外に送る通知（{name}）は使えません。"
            f"使うときは、config.yaml に「privacy: standard」と書いてください"
            f"（送る文章は「今日の学習の時間です」のような決まった一文だけで、記録の中身は含みません）。"
            f"PCの外に出さないなら、notifier を none か windows にしてください"
        )


def make_notifier(name, env=None, *, platform=None, runner=None, smtp=None, smtp_ssl=None, opener=None):
    """部品の名前から、通知の関数 send(メッセージ) を作る。

    platform・runner・smtp・smtp_ssl・opener は、試験で送る道具を差し替えるためのもの（普段は指定しない）。
    """
    env = env or {}
    name = (name or "").strip().lower()
    if name == "none":
        return _send_nothing
    if name == "windows":
        return _windows_notifier(platform or sys.platform, runner or subprocess.run)
    if name == "email":
        return _email_notifier(env, smtp or smtplib.SMTP, smtp_ssl or smtplib.SMTP_SSL)
    if name == "ntfy":
        return _ntfy_notifier(env, opener or urllib.request.urlopen)
    raise NotifyError(f"通知の部品「{name}」は使えません（{', '.join(NOTIFIER_NAMES)} から選びます）")


def _send_nothing(message):
    return None


def _windows_notifier(platform, runner):
    def send(message):
        if not platform.startswith("win"):
            raise NotifyError("notifier: windows は Windows でだけ使えます（メールなど、ほかの部品を選んでください）")
        env = _environ()
        env["DRILL_MESSAGE"] = message
        args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", TOAST_SCRIPT]
        try:
            result = runner(args, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS)
        except FileNotFoundError:
            raise NotifyError("PowerShell が見つかりません。トースト通知を出せませんでした") from None
        except (OSError, subprocess.SubprocessError) as e:
            raise NotifyError(f"トースト通知を出せませんでした: {e}") from e
        if result.returncode != 0:
            raise NotifyError(f"トースト通知を出せませんでした: {(result.stderr or '').strip()}")

    return send


def _environ():
    import os

    return dict(os.environ)


def _email_notifier(env, smtp, smtp_ssl):
    missing = [key for key in SMTP_REQUIRED if not env.get(key, "").strip()]
    if missing:
        raise NotifyError(f".env に、メールの設定が足りません: {', '.join(missing)}")
    host = env["DRILL_SMTP_HOST"].strip()
    try:
        port = int(env["DRILL_SMTP_PORT"].strip())
    except ValueError:
        port = 0
    if not 1 <= port <= 65535:
        raise NotifyError(f"DRILL_SMTP_PORT は、1〜65535 の整数で書いてください（今の値：{env['DRILL_SMTP_PORT']}）")
    security = env.get("DRILL_SMTP_SECURITY", "").strip().lower() or "starttls"
    if security not in SECURITY_MODES:
        raise NotifyError(f"DRILL_SMTP_SECURITY は {', '.join(SECURITY_MODES)} から選んでください（今の値：{security}）")
    user = env.get("DRILL_SMTP_USER", "").strip()
    password = env.get("DRILL_SMTP_PASSWORD", "")
    if bool(user) != bool(password):
        raise NotifyError("ログインには DRILL_SMTP_USER と DRILL_SMTP_PASSWORD の両方が必要です（片方しか書かれていません）")
    sender = env["DRILL_MAIL_FROM"].strip()
    recipients = [x.strip() for x in env["DRILL_MAIL_TO"].split(",") if x.strip()]

    def send(message):
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = "code-drill：学習のお知らせ"
        msg.set_content(message)
        try:
            if security == "ssl":
                connection = smtp_ssl(host, port, timeout=TIMEOUT_SECONDS, context=ssl.create_default_context())
            else:
                connection = smtp(host, port, timeout=TIMEOUT_SECONDS)
            with connection as server:
                if security == "starttls":
                    server.starttls(context=ssl.create_default_context())
                if user:
                    server.login(user, password)
                server.send_message(msg)
        except (smtplib.SMTPException, OSError) as e:
            # パスワードを出さないよう、設定の値は入れず、サーバーの名前と原因だけを伝える
            raise NotifyError(f"メールを送れませんでした（{host}:{port}）: {type(e).__name__}: {e}") from e

    return send


def _ntfy_notifier(env, opener):
    topic = env.get("DRILL_NTFY_TOPIC", "").strip()
    if not topic:
        raise NotifyError(".env に、ntfy の設定が足りません: DRILL_NTFY_TOPIC")
    if not NTFY_TOPIC_PATTERN.fullmatch(topic):
        # topic は合言葉と同じなので、入力された値は画面に出さない
        raise NotifyError("DRILL_NTFY_TOPIC は、10文字以上の英数字・- ・_ だけで書いてください（推測されにくい名前にします）")
    server = (env.get("DRILL_NTFY_SERVER", "").strip() or NTFY_DEFAULT_SERVER).rstrip("/")
    parts = urlsplit(server)
    local = (parts.hostname or "") in LOCAL_HOSTS
    if parts.scheme not in ("http", "https") or not parts.hostname or (parts.scheme == "http" and not local):
        raise NotifyError("DRILL_NTFY_SERVER は https:// で始めてください（このPCの中のサーバーだけは http:// も使えます）")
    token = env.get("DRILL_NTFY_TOKEN", "").strip()
    where = parts.netloc

    def send(message):
        headers = {"Title": "code-drill", "Content-Type": "text/plain; charset=utf-8"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(f"{server}/{topic}", data=message.encode("utf-8"), headers=headers, method="POST")
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", 200)
        except urllib.error.HTTPError as e:
            raise NotifyError(f"ntfy のサーバー（{where}）が受け付けませんでした（HTTP {e.code}）") from None
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise NotifyError(f"ntfy のサーバー（{where}）に送れませんでした: {reason}") from None
        if status >= 300:
            raise NotifyError(f"ntfy のサーバー（{where}）が受け付けませんでした（HTTP {status}）")

    return send
