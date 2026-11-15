"""Morning report (GitHub Issue comment): last 24h of posts, images, errors and self-heals."""
import html
import sys

from agent import notify
from agent.common import CFG, now, read_log


def build(hours=24):
    events = read_log(hours)
    posts = [e for e in events if e["kind"] == "post"]
    errors = [e for e in events if e["kind"] == "error"]
    heals = [e for e in events if e["kind"] == "heal"]
    total = sum(1 for e in read_log() if e["kind"] == "post")

    lines = [f"☀️ <b>Rapport {html.escape(CFG['site_name'])} — {now():%d/%m/%Y}</b>",
             f"📝 Articles publiés (24 h) : <b>{len(posts)}</b> · total : {total}",
             f"🖼 Images IA : {sum(1 for p in posts if not str(p.get('image_source', '')).startswith('svg'))}"
             f"/{len(posts)}",
             f"📣 URLs signalées aux moteurs (IndexNow) : "
             f"{sum(e.get('urls', 0) for e in events if e['kind'] == 'promote' and e.get('status') in (200, 202))}",
             f"🧯 Erreurs : {len(errors)} · 🩹 Réparations : {sum(1 for h in heals if h.get('status') == 'patched')}"]
    if posts:
        lines.append("\n<b>Publications</b>")
        lines += [f'• <a href="{html.escape(p["url"])}">{html.escape(p["title"])}</a> '
                  f'(<a href="{html.escape(p["image"])}">image</a>, {html.escape(p.get("llm", "?"))})' for p in posts]
    if heals:
        lines.append("\n<b>Auto-guérison</b>")
        lines += [f"• {h['status']} {html.escape(h.get('file', ''))} — {html.escape(h.get('explanation') or h.get('error', ''))[:200]}"
                  for h in heals[-5:]]
    if errors:
        lines.append("\n<b>Erreurs</b>")
        lines += [f"• {e['ts'][11:16]} UTC <code>{html.escape(e['error'][:200])}</code>" for e in errors[-5:]]
    if not events:
        lines.append("\n😴 Aucune activité : vérifie l'onglet Actions du repo.")
    return "\n".join(lines)


if __name__ == "__main__":
    print("rapport envoyé" if notify.alert(build()) else "hors GitHub Actions : rapport affiché ci-dessus")
    sys.exit(0)
