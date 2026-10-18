"""通知の部品（notifier.py）と、通知を出す入り口（notify.py）の試験

通知の部品は、どれも「メッセージを1つ受け取って知らせる」だけの同じ形（make_notifier が返す関数）。
ここでは、
  ・部品ごとの動きを、実際に送らずに確かめる（送る道具を差し替えて、渡された内容を見る）
  ・メールは、このPCの中に作った偽のメールサーバーに、実際に送って確かめる
  ・notify.py は、実際に起動して、終了コードと画面の文字を確かめる
Windows のトースト通知が画面に出ること、本物のメールサーバー（Gmail など）に届くことは、確かめられない
（Linux の作業環境にはないため。本人のPCで確かめる）。
説明（docstring）の書き方は、tests/test_grading.py の冒頭を参照。
"""

import email
import email.policy
import hashlib
import smtplib
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import notifier  # noqa: E402
import notify  # noqa: E402
import recorder  # noqa: E402

WEDNESDAY = date(2026, 10, 14)
SUNDAY = date(2026, 10, 18)

NTFY_ENV = {"DRILL_NTFY_TOPIC": "drill-abc123xyz789"}

FULL_ENV = {
    "DRILL_SMTP_HOST": "smtp.example.com",
    "DRILL_SMTP_PORT": "587",
    "DRILL_MAIL_FROM": "me@example.com",
    "DRILL_MAIL_TO": "me@example.com",
}


class FakeSMTP:
    """smtplib.SMTP の代わり。渡された内容を記録するだけ。"""

    instances = []
    fail_with = None

    def __init__(self, host, port, timeout=None, **kwargs):
        self.host, self.port, self.calls, self.sent = host, port, [], []
        type(self).instances.append(self)
        if FakeSMTP.fail_with:
            raise FakeSMTP.fail_with

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))
        if FakeSMTP.fail_with_login:
            raise FakeSMTP.fail_with_login

    def send_message(self, msg):
        self.calls.append("send")
        self.sent.append(msg)

    fail_with_login = None


class FakeResponse:
    """urlopen の返事の代わり。"""

    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b"{}"


class FakeSMTPSSL(FakeSMTP):
    instances = []


class FakeMailServer(socketserver.ThreadingTCPServer):
    """このPCの中だけで動く、偽のメールサーバー。届いたメールを mails に溜める。"""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        self.mails = []
        super().__init__(("127.0.0.1", 0), FakeMailHandler)


class FakeMailHandler(socketserver.StreamRequestHandler):
    def handle(self):
        def say(text):
            self.wfile.write((text + "\r\n").encode("ascii"))
            self.wfile.flush()

        say("220 fake")
        rcpts, body, in_data = [], [], False
        for raw in self.rfile:
            line = raw.rstrip(b"\r\n")  # 日本語が入るので、文字に直さず、バイトのまま扱う
            if in_data:
                if line == b".":
                    in_data = False
                    self.server.mails.append({"rcpts": rcpts, "data": b"\r\n".join(body)})
                    say("250 ok")
                else:
                    body.append(line[1:] if line.startswith(b"..") else line)
                continue
            word = line.decode("ascii", "replace").upper()
            if word.startswith("RCPT"):
                rcpts.append(line.decode("ascii", "replace").split(":", 1)[1].strip().strip("<>"))
                say("250 ok")
            elif word.startswith("DATA"):
                in_data = True
                say("354 go")
            elif word.startswith("QUIT"):
                say("221 bye")
                return
            else:
                say("250 fake")


def parse_mail(mail):
    return email.message_from_bytes(mail["data"], policy=email.policy.default)


class NotifierTestCase(unittest.TestCase):
    def setUp(self):
        FakeSMTP.instances = []
        FakeSMTP.fail_with = None
        FakeSMTP.fail_with_login = None
        FakeSMTPSSL.instances = []
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)

    def email_notifier(self, **env):
        values = dict(FULL_ENV)
        values.update(env)
        return notifier.make_notifier("email", values, smtp=FakeSMTP, smtp_ssl=FakeSMTPSSL)


class PartsTest(NotifierTestCase):
    def test_01_none_does_nothing(self):
        """TC-NTF-01 | 正常系 | none は何も送らない（通知なしでも動く）

        入力：make_notifier("none") で作った部品に、メッセージを渡す
        期待：例外にならない。道具（メール・PowerShell）は呼ばれない
        根拠：設計書 §8（通知は任意。notifier を書かない人でも使える）
        """
        calls = []
        send = notifier.make_notifier("none", {}, runner=lambda *a, **k: calls.append(a), smtp=FakeSMTP, smtp_ssl=FakeSMTPSSL)
        send("こんにちは")
        self.assertEqual(calls, [])
        self.assertEqual(FakeSMTP.instances, [])

    def test_02_unknown_name(self):
        """TC-NTF-02 | 異常系 | 知らない部品の名前は NotifyError にし、選べる名前を伝える

        入力：make_notifier("sms")
        期待：NotifyError。メッセージに none・windows・email・ntfy が出る
        根拠：書き間違いに気づけるように
        """
        with self.assertRaises(notifier.NotifyError) as cm:
            notifier.make_notifier("sms", {})
        for name in ("none", "windows", "email", "ntfy"):
            self.assertIn(name, str(cm.exception))

    def test_03_all_parts_share_one_shape(self):
        """TC-NTF-03 | 正常系 | どの部品も「メッセージを1つ受け取る関数」として同じ形で作れる（差し替えられる）

        入力：none・windows・email・ntfy を作り、同じ呼び方（send(メッセージ)）で呼ぶ
        期待：3つとも呼び出せる関数で、同じ呼び方で動く
        根拠：設計書 §8（どの部品も同じ形にして、差し替えられるようにする）
        """
        calls = []

        class Done:
            returncode, stderr = 0, ""

        for name in notifier.NOTIFIER_NAMES:
            send = notifier.make_notifier(
                name, dict(FULL_ENV, **NTFY_ENV), platform="win32", runner=lambda *a, **k: calls.append(1) or Done(),
                smtp=FakeSMTP, smtp_ssl=FakeSMTPSSL, opener=lambda request, timeout=None: FakeResponse(),
            )
            self.assertTrue(callable(send), name)
            send("合図")

    def test_04_windows_only_on_windows(self):
        """TC-NTF-04 | 環境差 | windows は、Windows 以外では NotifyError にし、理由を伝える

        入力：platform が linux の環境で windows の部品を作って送る
        期待：NotifyError。メッセージに「Windows」が出る。PowerShell は呼ばれない
        根拠：Linux・Mac で設定を間違えても、黙って何もしない状態にならないように
        """
        calls = []
        send = notifier.make_notifier("windows", {}, platform="linux", runner=lambda *a, **k: calls.append(a))
        with self.assertRaises(notifier.NotifyError) as cm:
            send("合図")
        self.assertIn("Windows", str(cm.exception))
        self.assertEqual(calls, [])

    def test_05_windows_passes_message_safely(self):
        """TC-NTF-05 | 異常系 | windows は、メッセージを PowerShell の命令文に埋め込まず、環境変数で渡す

        入力：メッセージが「'; Remove-Item x; $(whoami) "」のように、命令として働く記号を含む
        期待：powershell を呼ぶ。命令文（引数）にメッセージは含まれない。環境変数 DRILL_MESSAGE にそのまま入る
        根拠：メッセージの中身で、PowerShell が意図しない命令を実行しないため
        """
        seen = {}

        class Done:
            returncode, stderr = 0, ""

        def runner(args, **kwargs):
            seen["args"], seen["env"] = args, kwargs.get("env", {})
            return Done()

        evil = "'; Remove-Item x; $(whoami) \""
        notifier.make_notifier("windows", {}, platform="win32", runner=runner)(evil)
        self.assertEqual(seen["args"][0].lower(), "powershell")
        self.assertFalse(any(evil in str(a) for a in seen["args"]))
        self.assertEqual(seen["env"]["DRILL_MESSAGE"], evil)

    def test_06_windows_failures(self):
        """TC-NTF-06 | 異常系 | PowerShell が見つからない・失敗したときは NotifyError にし、原因を伝える

        入力：実行すると FileNotFoundError になる／終了コード1でエラー文を返す
        期待：どちらも NotifyError。後者はエラー文がメッセージに入る
        根拠：通知できなかったことを、使う人に伝えるため
        """

        def missing(*a, **k):
            raise FileNotFoundError("powershell")

        with self.assertRaises(notifier.NotifyError):
            notifier.make_notifier("windows", {}, platform="win32", runner=missing)("x")

        class Failed:
            returncode, stderr = 1, "トーストを出せません"

        with self.assertRaises(notifier.NotifyError) as cm:
            notifier.make_notifier("windows", {}, platform="win32", runner=lambda *a, **k: Failed())("x")
        self.assertIn("トーストを出せません", str(cm.exception))


class EmailTest(NotifierTestCase):
    def test_07_missing_settings(self):
        """TC-NTF-07 | 異常系 | メールの設定が足りないときは、足りない項目の名前をすべて挙げて NotifyError にする

        入力：設定が空／DRILL_MAIL_TO だけない
        期待：NotifyError。空なら4項目すべての名前が、後者なら DRILL_MAIL_TO が出る。メールは送られない
        根拠：直す場所（.env のどの行か）が分かるように
        """
        with self.assertRaises(notifier.NotifyError) as cm:
            notifier.make_notifier("email", {}, smtp=FakeSMTP, smtp_ssl=FakeSMTPSSL)("x")
        for key in FULL_ENV:
            self.assertIn(key, str(cm.exception))
        env = dict(FULL_ENV)
        del env["DRILL_MAIL_TO"]
        with self.assertRaises(notifier.NotifyError) as cm:
            notifier.make_notifier("email", env, smtp=FakeSMTP, smtp_ssl=FakeSMTPSSL)("x")
        self.assertIn("DRILL_MAIL_TO", str(cm.exception))
        self.assertNotIn("DRILL_SMTP_HOST", str(cm.exception))
        self.assertEqual(FakeSMTP.instances, [])

    def test_08_message_contents(self):
        """TC-NTF-08 | 正常系 | メールの宛先・差出人・件名・本文が、設定とメッセージのとおりになる（日本語も崩れない）

        入力：メッセージ「今日の学習の時間です（2問）」
        期待：From・To が設定どおり。件名に「code-drill」。本文がメッセージと同じ
        根拠：設計書 §8
        """
        self.email_notifier()("今日の学習の時間です（2問）")
        msg = FakeSMTP.instances[0].sent[0]
        self.assertEqual(msg["From"], "me@example.com")
        self.assertEqual(msg["To"], "me@example.com")
        self.assertIn("code-drill", msg["Subject"])
        self.assertEqual(msg.get_content().strip(), "今日の学習の時間です（2問）")

    def test_09_security_modes(self):
        """TC-NTF-09 | 環境差 | 暗号化の方式（DRILL_SMTP_SECURITY）で、使う接続が切り替わる。何も書かなければ starttls

        入力：書かない／starttls／ssl／none／知らない値（plain）
        期待：書かない・starttls は通常の接続→starttls を実行。ssl は SSL の接続（starttls は使わない）。none は暗号化なし。plain は NotifyError
        根拠：メールの会社ごとに方式が違うため。暗号化なしを、うっかり選ばないよう既定は starttls
        """
        self.email_notifier()("x")
        self.assertEqual(FakeSMTP.instances[-1].calls, ["starttls", "send"])
        self.email_notifier(DRILL_SMTP_SECURITY="starttls")("x")
        self.assertIn("starttls", FakeSMTP.instances[-1].calls)
        before = len(FakeSMTP.instances)
        self.email_notifier(DRILL_SMTP_SECURITY="ssl", DRILL_SMTP_PORT="465")("x")
        self.assertEqual(len(FakeSMTP.instances), before)  # 通常の接続は増えていない
        self.assertEqual(FakeSMTPSSL.instances[-1].calls, ["send"])
        self.email_notifier(DRILL_SMTP_SECURITY="none")("x")
        self.assertEqual(FakeSMTP.instances[-1].calls, ["send"])
        with self.assertRaises(notifier.NotifyError):
            self.email_notifier(DRILL_SMTP_SECURITY="plain")("x")

    def test_10_login_only_when_given(self):
        """TC-NTF-10 | 正常系 | ユーザー名とパスワードがあるときだけログインする。片方だけなら NotifyError

        入力：両方なし／両方あり／ユーザー名だけ
        期待：ログインしない／ログインする（starttls のあと、送信の前）／NotifyError
        根拠：ログイン不要のサーバーも、片方の書き忘れも、正しく扱うため
        """
        self.email_notifier()("x")
        self.assertFalse(any(isinstance(c, tuple) for c in FakeSMTP.instances[-1].calls))
        self.email_notifier(DRILL_SMTP_USER="u", DRILL_SMTP_PASSWORD="p")("x")
        self.assertEqual(FakeSMTP.instances[-1].calls, ["starttls", ("login", "u", "p"), "send"])
        with self.assertRaises(notifier.NotifyError) as cm:
            self.email_notifier(DRILL_SMTP_USER="u")("x")
        self.assertIn("DRILL_SMTP_PASSWORD", str(cm.exception))

    def test_11_send_failures_hide_password(self):
        """TC-NTF-11 | 異常系 | 接続・ログインに失敗したら NotifyError にする。メッセージにパスワードは出さない

        入力：接続で OSError／ログインで SMTPAuthenticationError。パスワードは「s3cret-pass」
        期待：どちらも NotifyError。メッセージにホスト名が入り、「s3cret-pass」は入らない
        根拠：エラー画面や記録にパスワードが残らないように
        """
        FakeSMTP.fail_with = OSError("接続できません")
        with self.assertRaises(notifier.NotifyError) as cm:
            self.email_notifier(DRILL_SMTP_USER="u", DRILL_SMTP_PASSWORD="s3cret-pass")("x")
        self.assertIn("smtp.example.com", str(cm.exception))
        self.assertNotIn("s3cret-pass", str(cm.exception))
        FakeSMTP.fail_with = None
        FakeSMTP.fail_with_login = smtplib.SMTPAuthenticationError(535, b"bad credentials")
        with self.assertRaises(notifier.NotifyError) as cm:
            self.email_notifier(DRILL_SMTP_USER="u", DRILL_SMTP_PASSWORD="s3cret-pass")("x")
        self.assertNotIn("s3cret-pass", str(cm.exception))

    def test_12_invalid_port(self):
        """TC-NTF-12 | 異常系 | ポート番号が整数でない・範囲外のときは NotifyError にする

        入力：DRILL_SMTP_PORT が abc／0／70000
        期待：どれも NotifyError。メッセージに DRILL_SMTP_PORT が出る
        根拠：他の数値の設定と同じ扱い
        """
        for bad in ("abc", "0", "70000"):
            with self.assertRaises(notifier.NotifyError, msg=bad) as cm:
                self.email_notifier(DRILL_SMTP_PORT=bad)("x")
            self.assertIn("DRILL_SMTP_PORT", str(cm.exception))

    def test_13_multiple_recipients(self):
        """TC-NTF-13 | 境界値 | 宛先をカンマで区切って複数書ける（前後の空白は無視する）

        入力：DRILL_MAIL_TO が「a@example.com, b@example.com」
        期待：To に2人とも入る
        根拠：自分のPCとスマホなど、複数のアドレスに送りたい場合
        """
        self.email_notifier(DRILL_MAIL_TO="a@example.com, b@example.com")("x")
        to = FakeSMTP.instances[0].sent[0]["To"]
        self.assertIn("a@example.com", to)
        self.assertIn("b@example.com", to)

    def test_14_real_connection(self):
        """TC-NTF-14 | 結合 | 本物の通信（SMTP）で、偽のメールサーバーに、日本語のメールが届く

        入力：このPCの中の偽サーバー（暗号化なし）に、DRILL_SMTP_SECURITY=none で送る
        期待：サーバーに1通届く。宛先・件名・本文（日本語）が正しく読める
        根拠：差し替えた道具ではなく、本物の smtplib を通った内容を確かめる
        """
        server = FakeMailServer()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        env = dict(FULL_ENV, DRILL_SMTP_HOST="127.0.0.1", DRILL_SMTP_PORT=str(server.server_address[1]), DRILL_SMTP_SECURITY="none")
        notifier.make_notifier("email", env)("今日の学習の時間です（2問）")
        self.assertEqual(len(server.mails), 1)
        msg = parse_mail(server.mails[0])
        self.assertEqual(server.mails[0]["rcpts"], ["me@example.com"])
        self.assertIn("code-drill", msg["Subject"])
        self.assertEqual(msg.get_content().strip(), "今日の学習の時間です（2問）")


class LoadEnvTest(NotifierTestCase):
    def test_15_load_env(self):
        """TC-NTF-15 | 正常系 | .env を「名前=値」で読む。空行・# の行は飛ばし、前後の空白と引用符を除く

        入力：コメント、空行、空白つき、"…" と '…' で囲んだ値、値に = を含む行
        期待：辞書になる。値の中の = は残る。引用符の中の # は残る
        根拠：パスワードに記号が入ることがあるため
        """
        path = self.folder / ".env"
        path.write_text(
            '# コメント\n\nA = 1\nB="two words"\nC=\'x#y\'\nD=pa=ss\nE=\n',
            encoding="utf-8",
        )
        self.assertEqual(notifier.load_env(path), {"A": "1", "B": "two words", "C": "x#y", "D": "pa=ss", "E": ""})

    def test_16_load_env_missing_file(self):
        """TC-NTF-16 | 境界値 | .env がなくてもエラーにしない（空の辞書）

        入力：存在しないパス
        期待：{}
        根拠：none・windows は .env が要らない
        """
        self.assertEqual(notifier.load_env(self.folder / "nothing.env"), {})

    def test_17_load_env_bad_line(self):
        """TC-NTF-17 | 異常系 | 「名前=値」の形でない行があれば NotifyError にし、何行目かを伝える。値は伝えない

        入力：3行目が「s3cret-pass」だけの .env／UTF-8でないファイル
        期待：NotifyError。「3行目」が出る。「s3cret-pass」は出ない。文字コードの誤りも NotifyError
        根拠：書き間違いの場所が分かるように。パスワードを画面に出さない
        """
        path = self.folder / ".env"
        path.write_text("A=1\nB=2\ns3cret-pass\n", encoding="utf-8")
        with self.assertRaises(notifier.NotifyError) as cm:
            notifier.load_env(path)
        self.assertIn("3行目", str(cm.exception))
        self.assertNotIn("s3cret-pass", str(cm.exception))
        path.write_bytes("A=あ".encode("cp932"))
        with self.assertRaises(notifier.NotifyError):
            notifier.load_env(path)


class MessageTest(unittest.TestCase):
    CONFIG = {"days": ["mon", "tue", "wed", "thu", "fri", "sat"], "questions_per_day": 2}

    def rows(self, *dates):
        return [{"date": d} for d in dates]

    def test_18_start_on_study_day(self):
        """TC-NTF-18 | 正常系 | 学習の時間の合図（start）は、学習日に「今日の学習」と問題数を伝える

        入力：水曜、questions_per_day=2／3
        期待：メッセージに「今日の学習」と「2問」／「3問」が出る
        根拠：設計書 §8（合図）
        """
        message = notify.build_message("start", self.CONFIG, [], WEDNESDAY)
        self.assertIn("今日の学習", message)
        self.assertIn("2問", message)
        self.assertIn("3問", notify.build_message("start", dict(self.CONFIG, questions_per_day=3), [], WEDNESDAY))

    def test_19_rest_day_sends_nothing(self):
        """TC-NTF-19 | 正常系 | 休みの日は、合図もリマインドも出さない（None）

        入力：日曜に start・remind。days: [mon] の設定で水曜に start
        期待：どれも None
        根拠：休みの日に鳴らさない（設計書 §5-2、設定の days に従う）
        """
        self.assertIsNone(notify.build_message("start", self.CONFIG, [], SUNDAY))
        self.assertIsNone(notify.build_message("remind", self.CONFIG, [], SUNDAY))
        self.assertIsNone(notify.build_message("start", dict(self.CONFIG, days=["mon"]), [], WEDNESDAY))

    def test_20_remind_only_without_record(self):
        """TC-NTF-20 | 正常系 | リマインド（remind）は、今日の記録がないときだけ出す。記録があれば None

        入力：記録なし／今日の記録あり／昨日の記録だけ
        期待：出す（「まだ」が入る）／None／出す
        根拠：Claude 版の 21:30 のリマインドと同じ（記録のある日は鳴らさない）
        """
        today = WEDNESDAY.isoformat()
        self.assertIn("まだ", notify.build_message("remind", self.CONFIG, [], WEDNESDAY))
        self.assertIsNone(notify.build_message("remind", self.CONFIG, self.rows(today), WEDNESDAY))
        self.assertIn("まだ", notify.build_message("remind", self.CONFIG, self.rows("2026-10-13"), WEDNESDAY))

    def test_21_start_ignores_records(self):
        """TC-NTF-21 | 境界値 | 合図（start）は、今日の記録があっても出す

        入力：今日の記録があるときの start
        期待：メッセージが出る
        根拠：合図は決まった時刻に出すもの。記録を見て鳴らし分けるのはリマインドだけ
        """
        rows = self.rows(WEDNESDAY.isoformat())
        self.assertIsNotNone(notify.build_message("start", self.CONFIG, rows, WEDNESDAY))

    def test_22_unknown_kind(self):
        """TC-NTF-22 | 異常系 | 知らない種類（kind）を渡したら ValueError にする

        入力：build_message("daily", …)
        期待：ValueError
        根拠：プログラムの呼び間違いに気づけるように
        """
        with self.assertRaises(ValueError):
            notify.build_message("daily", self.CONFIG, [], WEDNESDAY)


class CliBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.config = self.folder / "config.yaml"
        self.log = self.folder / "data" / "log.csv"
        self.env = self.folder / ".env"
        self.server = None

    def start_server(self):
        self.server = FakeMailServer()
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close()))
        self.env.write_text(
            "DRILL_SMTP_HOST=127.0.0.1\n"
            f"DRILL_SMTP_PORT={self.server.server_address[1]}\n"
            "DRILL_SMTP_SECURITY=none\nDRILL_MAIL_FROM=me@example.com\nDRILL_MAIL_TO=me@example.com\n",
            encoding="utf-8",
        )

    def run_notify(self, when="start", day="2026-10-14", *extra):
        return subprocess.run(
            [sys.executable, str(ROOT / "notify.py"), "--when", when, "--date", day,
             "--config", str(self.config), "--log", str(self.log), "--env", str(self.env), *extra],
            capture_output=True, text=True, timeout=60,
        )

    def add_record(self, day):
        recorder.append_log(self.log, [recorder.make_row({"id": "p-1", "unit": "u", "level": 1}, True, "python", today=date.fromisoformat(day))])


class CliTest(CliBase):
    def test_23_none_sends_nothing(self):
        """TC-NTF-23 | 正常系 | notifier が none（既定）なら、何も送らずに終了コード0で終わり、その旨を表示する

        入力：設定ファイルなしで notify.py --when start／記録ファイルが壊れた状態で --when remind
        期待：終了コード0。画面に「none」が出て、「通知しました」は出ない。記録は読まない（壊れていてもエラーにならない）。トレースバックは出ない
        根拠：通知なしの人が、実行しても困らないように
        """
        p = self.run_notify()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("none", p.stdout)
        self.assertNotIn("通知しました", p.stdout)
        self.assertNotIn("Traceback", p.stderr)
        # 記録ファイルが壊れていても、none なら記録を読まないので、エラーにならない
        self.log.parent.mkdir(parents=True)
        self.log.write_text("a,b\n1,2\n", encoding="utf-8")
        self.assertEqual(self.run_notify("remind").returncode, 0)

    def test_24_email_start_end_to_end(self):
        """TC-NTF-24 | 結合 | notifier: email で start を実行すると、偽のメールサーバーに合図のメールが1通届く

        入力：設定 notifier: email、.env に偽サーバーの設定。水曜に notify.py --when start
        期待：終了コード0。サーバーに1通。本文に「今日の学習」
        根拠：設定の読み込み→メッセージ作成→部品の選択→送信、が一続きで動くこと
        """
        self.start_server()
        self.config.write_text("notifier: email\nprivacy: standard\n", encoding="utf-8")
        p = self.run_notify("start")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(self.server.mails), 1)
        self.assertIn("今日の学習", parse_mail(self.server.mails[0]).get_content())

    def test_25_email_remind_depends_on_log(self):
        """TC-NTF-25 | 結合 | remind は、記録がなければメールが届き、今日の記録があれば届かない。記録ファイルは変わらない

        入力：記録なしで remind／今日の記録を作って remind
        期待：1回目は1通届く。2回目は増えず、終了コード0で「通知しません」と表示。記録ファイルの中身は実行の前後で同じ
        根拠：21:30 のリマインドと同じ動き。通知のために記録を書き換えない（読むだけ）
        """
        self.start_server()
        self.config.write_text("notifier: email\nprivacy: standard\n", encoding="utf-8")
        self.assertEqual(self.run_notify("remind").returncode, 0)
        self.assertEqual(len(self.server.mails), 1)
        self.add_record("2026-10-14")
        before = hashlib.sha256(self.log.read_bytes()).hexdigest()
        p = self.run_notify("remind")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(self.server.mails), 1)
        self.assertIn("通知しません", p.stdout)
        self.assertEqual(hashlib.sha256(self.log.read_bytes()).hexdigest(), before)

    def test_26_rest_day(self):
        """TC-NTF-26 | 正常系 | 休みの日は、何も送らず終了コード0で、休みのため通知しないと表示する

        入力：日曜に notify.py --when start（notifier: email）
        期待：終了コード0。メールは届かない。「休み」が出る
        根拠：TC-NTF-19 を、実際の起動で確かめる
        """
        self.start_server()
        self.config.write_text("notifier: email\nprivacy: standard\n", encoding="utf-8")
        p = self.run_notify("start", "2026-10-18")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.server.mails, [])
        self.assertIn("休み", p.stdout)

    def test_27_errors_are_readable(self):
        """TC-NTF-27 | 異常系 | 設定・.env・記録・日付・windows の誤りは、1行の「エラー：…」で終了コード1。トレースバックは出ない

        入力：①days が正しくない設定 ②notifier: email で .env なし ③記録ファイルの見出しが違う（remind） ④--date が正しくない ⑤notifier: windows（Windows 以外で実行。Windows では通知が実際に出るため、この項目は行わない）
        期待：どれも終了コード1。画面（標準エラー）に「エラー」。「Traceback」は出ない。②は DRILL_SMTP_HOST が、⑤は Windows が出る
        根拠：drill.py と同じ扱い
        """
        self.config.write_text("days: [funday]\n", encoding="utf-8")
        cases = [self.run_notify()]
        self.config.write_text("notifier: email\nprivacy: standard\n", encoding="utf-8")
        p2 = self.run_notify()
        cases.append(p2)
        self.start_server()  # ここから先は、.env が正しい状態で確かめる
        self.log.parent.mkdir(parents=True)
        self.log.write_text("a,b\n1,2\n", encoding="utf-8")
        cases.append(self.run_notify("remind"))
        self.assertEqual(self.server.mails, [])
        cases.append(self.run_notify("start", "2026-13-40"))
        # ⑤は Windows 以外だけ確かめる（Windows では、実際に通知が出て成功してしまうため）
        p5 = None
        if sys.platform != "win32":
            self.config.write_text("notifier: windows\n", encoding="utf-8")
            p5 = self.run_notify()
            cases.append(p5)
        for p in cases:
            self.assertEqual(p.returncode, 1, p.stdout)
            self.assertIn("エラー", p.stderr)
            self.assertNotIn("Traceback", p.stderr)
        self.assertIn("DRILL_SMTP_HOST", p2.stderr)
        if p5 is not None:
            self.assertIn("Windows", p5.stderr)

    def test_28_help(self):
        """TC-NTF-28 | 環境差 | `python notify.py --help` は、何も送らずに使い方を表示して終了する

        入力：python notify.py --help
        期待：終了コード0。「--when」「start」「remind」が書かれている
        根拠：使い方を安全に確かめられるように
        """
        p = subprocess.run([sys.executable, str(ROOT / "notify.py"), "--help"], capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        for word in ("--when", "start", "remind"):
            self.assertIn(word, p.stdout)


class NtfyTest(NotifierTestCase):
    def ntfy(self, opener=None, **env):
        values = dict(NTFY_ENV)
        values.update(env)
        seen = []

        def default_opener(request, timeout=None):
            seen.append(request)
            return FakeResponse()

        return notifier.make_notifier("ntfy", values, opener=opener or default_opener), seen

    def test_29_ntfy_missing_topic(self):
        """TC-NTF-29 | 異常系 | ntfy は、送り先の名前（DRILL_NTFY_TOPIC）がなければ NotifyError にし、足りない項目を伝える

        入力：設定が空
        期待：NotifyError。メッセージに DRILL_NTFY_TOPIC が出る
        根拠：直す場所が分かるように
        """
        with self.assertRaises(notifier.NotifyError) as cm:
            notifier.make_notifier("ntfy", {}, opener=lambda *a, **k: FakeResponse())("x")
        self.assertIn("DRILL_NTFY_TOPIC", str(cm.exception))

    def test_30_ntfy_topic_must_be_hard_to_guess(self):
        """TC-NTF-30 | 異常系 | 送り先の名前（topic）が短い・使えない文字を含むときは NotifyError にする。名前そのものは伝えない

        入力：「abc」（短い）、「drill abc123xyz789」（空白）、「drill/abc123xyz789」（スラッシュ）
        期待：どれも NotifyError。メッセージに、入力した名前は出ない
        根拠：ntfy は、topic の名前を知っている人なら誰でも読める仕組み。推測されにくい長さと文字にするため
        """
        for bad in ("abc", "drill abc123xyz789", "drill/abc123xyz789"):
            with self.assertRaises(notifier.NotifyError, msg=bad) as cm:
                self.ntfy(DRILL_NTFY_TOPIC=bad)
            self.assertNotIn(bad, str(cm.exception))

    def test_31_ntfy_request(self):
        """TC-NTF-31 | 正常系 | 既定では https://ntfy.sh の topic に、本文＝メッセージ（日本語）を POST で送る。トークンがあれば付ける

        入力：メッセージ「今日の学習の時間です（2問）」。トークンなし／あり
        期待：送り先は https://ntfy.sh/<topic>。方法は POST。本文は UTF-8 でメッセージと同じ。トークンなしは Authorization なし、ありは「Bearer …」
        根拠：ntfy の使い方（公式の POST の形）。タイトルは英数字だけ（ヘッダーに日本語を入れない）
        """
        send, seen = self.ntfy()
        send("今日の学習の時間です（2問）")
        request = seen[0]
        self.assertEqual(request.full_url, "https://ntfy.sh/drill-abc123xyz789")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.data.decode("utf-8"), "今日の学習の時間です（2問）")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertTrue(request.get_header("Title").isascii())
        send, seen = self.ntfy(DRILL_NTFY_TOKEN="tk_secret")
        send("x")
        self.assertEqual(seen[0].get_header("Authorization"), "Bearer tk_secret")

    def test_32_ntfy_server_must_be_https(self):
        """TC-NTF-32 | 異常系 | 自分で立てたサーバーを指定できる。ただし、このPC以外への http（暗号化なし）は断る

        入力：DRILL_NTFY_SERVER が https://ntfy.example.com／http://ntfy.example.com／http://127.0.0.1:8080／ftp://x
        期待：1つ目と3つ目は使える。2つ目と4つ目は NotifyError
        根拠：暗号化されない通信で、メッセージやトークンがインターネットを流れないため
        """
        send, seen = self.ntfy(DRILL_NTFY_SERVER="https://ntfy.example.com/")
        send("x")
        self.assertEqual(seen[0].full_url, "https://ntfy.example.com/drill-abc123xyz789")
        self.ntfy(DRILL_NTFY_SERVER="http://127.0.0.1:8080")
        for bad in ("http://ntfy.example.com", "ftp://x"):
            with self.assertRaises(notifier.NotifyError, msg=bad):
                self.ntfy(DRILL_NTFY_SERVER=bad)

    def test_33_ntfy_failure_hides_secrets(self):
        """TC-NTF-33 | 異常系 | 送れなかったときは NotifyError にする。メッセージに、サーバーの名前は出すが、topic とトークンは出さない

        入力：接続で URLError／サーバーが 403 を返す HTTPError／例外にならず状態 500 が返る場合
        期待：どれも NotifyError。「ntfy.sh」は出る。topic の名前・トークンは出ない
        根拠：topic とトークンは、パスワードと同じ扱い
        """
        import urllib.error

        def broken(request, timeout=None):
            raise urllib.error.URLError("接続できません")

        def forbidden(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

        class ServerError(FakeResponse):
            status = 500  # 例外にならずに、失敗の状態が返ってきた場合

        for opener in (broken, forbidden, lambda request, timeout=None: ServerError()):
            send, _ = self.ntfy(opener=opener, DRILL_NTFY_TOKEN="tk_secret")
            with self.assertRaises(notifier.NotifyError) as cm:
                send("x")
            text = str(cm.exception)
            self.assertIn("ntfy.sh", text)
            self.assertNotIn("drill-abc123xyz789", text)
            self.assertNotIn("tk_secret", text)

    def test_34_ntfy_real_connection(self):
        """TC-NTF-34 | 結合 | 本物の通信（HTTP）で、このPCの中の偽の ntfy サーバーに、日本語のメッセージが届く

        入力：偽のサーバー（127.0.0.1）を DRILL_NTFY_SERVER に指定して送る
        期待：サーバーは POST を1回受ける。パスは /<topic>。本文は日本語のメッセージのまま
        根拠：差し替えた道具ではなく、本物の urllib を通った内容を確かめる
        """
        import http.server

        received = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                received.append((self.path, self.rfile.read(length)))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        notifier.make_notifier(
            "ntfy", dict(NTFY_ENV, DRILL_NTFY_SERVER=f"http://127.0.0.1:{server.server_address[1]}")
        )("今日の学習の時間です（2問）")
        self.assertEqual(received, [("/drill-abc123xyz789", "今日の学習の時間です（2問）".encode("utf-8"))])


class PrivacyTest(unittest.TestCase):
    def test_35_check_privacy(self):
        """TC-NTF-35 | 正常系 | strict は、PCの外に出る部品（email・ntfy）を断り、理由と直し方を伝える。none・windows は通す。standard は全部通す

        入力：strict と standard のそれぞれで、none・windows・email・ntfy を調べる
        期待：strict は email・ntfy が NotifyError（メッセージに「privacy: standard」と部品の名前）。ほかは通る
        根拠：個人情報が外に出ない設定を、使う人が選べるように（既定は strict）
        """
        for name in ("none", "windows"):
            notifier.check_privacy(name, "strict")
        for name in notifier.NOTIFIER_NAMES:
            notifier.check_privacy(name, "standard")
        for name in ("email", "ntfy"):
            with self.assertRaises(notifier.NotifyError, msg=name) as cm:
                notifier.check_privacy(name, "strict")
            self.assertIn("privacy: standard", str(cm.exception))
            self.assertIn(name, str(cm.exception))

    def test_36_external_parts_are_listed(self):
        """TC-NTF-36 | 正常系 | PCの外に出る部品の一覧（EXTERNAL_NOTIFIERS）は、email と ntfy だけ。すべて NOTIFIER_NAMES の中にある

        入力：一覧を調べる
        期待：{email, ntfy}。none・windows は入らない。部品を足したときに、分類を忘れていないこと
        根拠：新しい部品を足すとき、外に出るかどうかを決め忘れないため
        """
        self.assertEqual(set(notifier.EXTERNAL_NOTIFIERS), {"email", "ntfy"})
        self.assertTrue(set(notifier.EXTERNAL_NOTIFIERS) <= set(notifier.NOTIFIER_NAMES))


class PrivacyCliTest(CliBase):
    """notify.py を実際に起動して、privacy の効き方を確かめる。"""

    def test_37_strict_blocks_email_by_default(self):
        """TC-NTF-37 | 異常系 | privacy を書かない（既定は strict）まま notifier: email にすると、メールは送られず、理由つきのエラーになる

        入力：notifier: email だけの設定（privacy なし）、.env は正しい
        期待：終了コード1。標準エラーに「privacy」と「standard」。メールは1通も届かない。トレースバックは出ない
        根拠：うっかり外に出さないための既定。設定を足せば送れることも伝える
        """
        self.start_server()
        self.config.write_text("notifier: email\n", encoding="utf-8")
        p = self.run_notify()
        self.assertEqual(p.returncode, 1)
        self.assertIn("privacy", p.stderr)
        self.assertIn("standard", p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(self.server.mails, [])

    def test_38_strict_blocks_before_reading_env(self):
        """TC-NTF-38 | 異常系 | strict で外に出る部品を選んだときは、.env（パスワード）を読む前に止まる

        入力：notifier: ntfy（privacy なし）、.env は壊れた形（「名前=値」でない行）
        期待：エラーは privacy のもの（.env の形のエラーではない）
        根拠：外に出さない設定のときは、外に出すための情報を、そもそも読まない
        """
        self.config.write_text("notifier: ntfy\n", encoding="utf-8")
        self.env.write_text("this-is-not-a-pair\n", encoding="utf-8")
        p = self.run_notify()
        self.assertEqual(p.returncode, 1)
        self.assertIn("privacy", p.stderr)
        self.assertNotIn(".env", p.stderr)

    def test_39_standard_sends_only_the_fixed_sentence(self):
        """TC-NTF-39 | 結合 | privacy: standard でも、送る文章は決まった一文だけ。記録の中身（問題番号・言語・単元など）は含まれない

        入力：記録に、目印になる問題番号（SECRET-QID-777）と言語（zzlang）がある状態で、リマインドをメールで送る
        期待：届いた本文は、build_message が作る一文と同じ。目印の文字は含まれない
        根拠：個人情報（学習の中身）が、通知を通じて外に出ないこと
        """
        self.start_server()
        self.config.write_text("notifier: email\nprivacy: standard\n", encoding="utf-8")
        recorder.append_log(
            self.log,
            [recorder.make_row({"id": "SECRET-QID-777", "unit": "SECRET-UNIT", "level": 1}, True, "zzlang", today=date(2026, 10, 13))],
        )
        self.assertEqual(self.run_notify("remind").returncode, 0)
        body = parse_mail(self.server.mails[0]).get_content().strip()
        expected = notify.build_message("remind", {"days": ["mon", "tue", "wed", "thu", "fri", "sat"], "questions_per_day": 2}, [], WEDNESDAY)
        self.assertEqual(body, expected)
        for secret in ("SECRET-QID-777", "SECRET-UNIT", "zzlang"):
            self.assertNotIn(secret, body)

    def test_40_ntfy_end_to_end(self):
        """TC-NTF-40 | 結合 | notifier: ntfy ＋ privacy: standard で notify.py を実行すると、偽の ntfy サーバーに合図が届く

        入力：偽のサーバー（127.0.0.1）と topic を .env に書いて、水曜に --when start
        期待：終了コード0。サーバーが受けた本文に「今日の学習」
        根拠：設定の読み込み→privacy の確認→.env→ntfy の送信、が一続きで動くこと
        """
        import http.server

        received = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                received.append((self.path, self.rfile.read(length).decode("utf-8")))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close()))
        self.config.write_text("notifier: ntfy\nprivacy: standard\n", encoding="utf-8")
        self.env.write_text(
            f"DRILL_NTFY_TOPIC=drill-abc123xyz789\nDRILL_NTFY_SERVER=http://127.0.0.1:{server.server_address[1]}\n",
            encoding="utf-8",
        )
        p = self.run_notify("start")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0], "/drill-abc123xyz789")
        self.assertIn("今日の学習", received[0][1])

    @unittest.skipIf(sys.platform == "win32", "Windows では、実際に通知が出てしまうため行わない（privacy の判断は TC-NTF-35 で確認している）")
    def test_41_local_parts_work_in_strict(self):
        """TC-NTF-41 | 正常系 | strict のままで、windows は privacy に止められない（Windows 以外では、止まる理由が「Windows でだけ使える」になる）

        入力：notifier: windows（privacy なし）を Windows 以外で実行（Windows では行わない）
        期待：エラーの理由は Windows に関するもの。「privacy」は出ない
        根拠：PCの外に出ない部品は、strict でも使えること
        """
        self.config.write_text("notifier: windows\n", encoding="utf-8")
        p = self.run_notify()
        self.assertEqual(p.returncode, 1)
        self.assertIn("Windows", p.stderr)
        self.assertNotIn("privacy", p.stderr)


if __name__ == "__main__":
    unittest.main()
