"""Telegram: private alerts/reports (TELEGRAM_CHAT_ID) and public channel posts (TELEGRAM_CHANNEL_ID)."""
import html
import os
import sys

import requests

from agent.common import redact


def _call(method, data, files=None):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print(f"[telegram] pas de token, {method} ignoré")
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", data=data, files=files, timeout=90)
    except requests.RequestException as e:  # the URL holds the token: redact before printing
        print(f"[telegram] {method} erreur réseau: {redact(e)}")
        return False
    if not r.ok:
        print(f"[telegram] {method} échec {r.status_code}: {redact(r.text[:300])}")
    return r.ok


def alert(text):
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not chat:
        print(redact(text))
        return False
    return _call("sendMessage", {"chat_id": chat, "text": redact(text)[:4000], "parse_mode": "HTML",
                                 "disable_web_page_preview": "true"})


def publish_channel(image_path, caption):
    chat = os.getenv("TELEGRAM_CHANNEL_ID")
    if not chat:
        return False
    if image_path.suffix != ".jpg":
        return _call("sendMessage", {"chat_id": chat, "text": caption[:4000]})
    with image_path.open("rb") as f:
        return _call("sendPhoto", {"chat_id": chat, "caption": caption[:1024]}, files={"photo": f})


if __name__ == "__main__":
    # usage: python -m agent.notify "message" [logfile]
    msg = html.escape(sys.argv[1])
    if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
        tail = open(sys.argv[2], encoding="utf-8", errors="replace").read()[-2500:]
        msg += f"\n<pre>{html.escape(redact(tail))}</pre>"
    alert(msg)
