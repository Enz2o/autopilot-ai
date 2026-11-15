"""Free auto-promotion without any account: IndexNow pings Bing, Yandex, Naver, Seznam for each new article.

Called at the start of each run, so articles from the previous run are already live on GitHub Pages
(the key file must be reachable when the search engines verify it).
"""
import json
from urllib.parse import urlparse

import requests

from agent.common import CFG, STATE, log_event, site_url

DONE = STATE / "indexnow.json"


def pending_urls(posts, base, done):
    urls = [f"{base}/p/{p['slug']}.html" for p in posts]
    pending = [u for u in urls if u not in done]
    if pending and not done:  # first submission: include the home page too
        pending.append(f"{base}/")
    return pending


def submit_pending(posts):
    base, key = site_url(), CFG.get("indexnow_key")
    if not (base and key):
        return 0
    done = set(json.loads(DONE.read_text(encoding="utf-8"))) if DONE.exists() else set()
    pending = pending_urls(posts, base, done)
    if not pending:
        return 0
    r = requests.post("https://api.indexnow.org/indexnow", timeout=30, json={
        "host": urlparse(base).netloc, "key": key, "keyLocation": f"{base}/{key}.txt", "urlList": pending[:10000]})
    ok = r.status_code in (200, 202)
    log_event("promote", channel="indexnow", urls=len(pending), status=r.status_code)
    if ok:
        DONE.write_text(json.dumps(sorted(done | set(pending)), indent=0), encoding="utf-8")
    print(f"[indexnow] {len(pending)} URL(s) -> HTTP {r.status_code}")
    return len(pending) if ok else 0
