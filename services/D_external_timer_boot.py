# %%
import importlib.util
import os
import smtplib
import ssl
import sys
from email.mime.text import MIMEText
from email.utils import formatdate
from typing import Any

# data/smtp_account/my_gmail_account.py を型安全にインポート
my_gmail_account: Any
try:
    spec = importlib.util.spec_from_file_location(
        "my_gmail_account",
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'smtp_account', 'my_gmail_account.py'))
    )
    if spec and spec.loader:
        my_gmail_account = importlib.util.module_from_spec(spec)
        sys.modules["my_gmail_account"] = my_gmail_account
        spec.loader.exec_module(my_gmail_account)
    else:
        raise ImportError("Could not load my_gmail_account module")
except Exception as e:
    raise ImportError(f"my_gmail_accountのインポートに失敗しました: {e}")


# -------------------------------------------------------------
# wordの各項と対応する関数
# -------------------------------------------------------------


def send_timer_boot_email(timer_minute: int) -> None:
    """外部タイマーを起動するためのメールを送信する

    Args:
        timer_minute (int): タイマーの分数
    """

    from_addr = my_gmail_account.from_account
    to_addr = my_gmail_account.to_account
    subject = "Timer_boot"
    body = str(timer_minute)

    msg = _crateMIMEtext(from_addr, to_addr, subject, body)

    smtp_server = "smtp.gmail.com"
    smtp_port = 465

    _send_email(
        smtp_server, smtp_port, my_gmail_account.from_account, my_gmail_account.password, msg)
    return


# -------------------------------------------------------------
# 上記の関数で使用する補助関数群
# -------------------------------------------------------------


def _crateMIMEtext(from_addr, to_addr, subject, body):
    # MIMETextオブジェクトを使ってメール本文を作成
    msg = MIMEText(body, _subtype='plain', _charset='utf-8')
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg['Date'] = formatdate(localtime=True)
    msg['Reply-To'] = from_addr
    return msg

def _send_email(smtp_server, smtp_port, account, password, msg):
    # SMTPサーバーに接続してメールを送信
    server = smtplib.SMTP_SSL(
        smtp_server,
        smtp_port,
        context=ssl.create_default_context()
    )
    server.set_debuglevel(False)  # デバッグ情報を表示しない

    # ログインしてメールを送信
    server.login(account, password)
    server.send_message(msg)

    server.quit()
    return True

if __name__ == "__main__":
    send_timer_boot_email(5)

# %%
