"""Alerts and morning reports as comments on one GitHub Issue: GitHub emails the repo owner, no extra account."""
import html
import os
import sys

import requests

from agent.common import redact

API = "https://api.github.com"
TITLE = "📊 Autopilot : rapports et alertes"


def _issue_number(headers, repo):
    r = requests.get(f"{API}/repos/{repo}/issues", headers=headers,
                     params={"labels": "autopilot", "state": "open"}, timeout=30)
    r.raise_for_status()
    if r.json():
        return r.json()[0]["number"]
    r = requests.post(f"{API}/repos/{repo}/issues", headers=headers, timeout=30, json={
        "title": TITLE, "labels": ["autopilot"],
        "body": "Le bot poste ici son rapport du matin et ses alertes. GitHub t'envoie un e-mail à chaque message."})
    r.raise_for_status()
    return r.json()["number"]


def alert(text):
    text = redact(text)
    token, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    if not (token and repo):  # local run: just print
        print(text)
        return False
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        n = _issue_number(headers, repo)
        r = requests.post(f"{API}/repos/{repo}/issues/{n}/comments", headers=headers,
                          json={"body": text[:60000]}, timeout=30)
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"[github] alerte non envoyée: {redact(e)}\n{text}")
        return False


if __name__ == "__main__":
    # usage: python -m agent.notify "message" [logfile]
    msg = html.escape(sys.argv[1])
    if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
        tail = open(sys.argv[2], encoding="utf-8", errors="replace").read()[-2500:]
        msg += f"\n<pre>{html.escape(redact(tail))}</pre>"
    alert(msg)
