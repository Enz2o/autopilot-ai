"""Shared paths, config, event log and secret redaction."""
import datetime
import json
import os
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # emojis on Windows consoles (cp1252)
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
AGENT = ROOT / "agent"
DOCS = ROOT / "docs"
STATE = ROOT / "state"
LOG = STATE / "log.jsonl"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

SECRET_ENVS = ("GEMINI_API_KEY", "GROQ_API_KEY", "TELEGRAM_BOT_TOKEN", "CF_API_TOKEN", "POLLINATIONS_TOKEN")


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def redact(text):
    """Remove secret values so logs, alerts and LLM prompts never leak them."""
    text = str(text)
    for name in SECRET_ENVS:
        value = os.getenv(name)
        if value and len(value) > 6:
            text = text.replace(value, f"<{name}>")
    return text


def log_event(kind, **data):
    STATE.mkdir(exist_ok=True)
    clean = {k: redact(v) if isinstance(v, str) else v for k, v in data.items()}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now().isoformat(timespec="seconds"), "kind": kind, **clean}, ensure_ascii=False) + "\n")


def read_log(hours=None):
    if not LOG.exists():
        return []
    events = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    if hours is None:
        return events
    cutoff = now() - datetime.timedelta(hours=hours)
    return [e for e in events if datetime.datetime.fromisoformat(e["ts"]) >= cutoff]


def site_url():
    return (os.getenv("SITE_URL") or CFG.get("site_url") or "").rstrip("/")
