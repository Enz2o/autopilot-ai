"""Self-healing: read the crash log, ask the LLM for a fixed file, keep it only if the self-test passes."""
import html
import py_compile
import re
import subprocess
import sys

from agent import llm, notify
from agent.common import AGENT, ROOT, log_event, redact

# Files the healer may rewrite. Its own dependencies (llm, notify, common, heal, selftest) stay
# untouchable so a bad patch can never break the healer itself.
PATCHABLE = {"main.py", "site.py", "image.py", "report.py"}
TRANSIENT = re.compile(r"LLM_UNAVAILABLE|requests\.exceptions|HTTPError|Timeout|ConnectionError|"
                       r"\b(429|500|502|503|504)\b|quota|rate.?limit", re.I)

HEAL_PROMPT = """Tu es ingénieur Python senior. Un script de production a planté.
Corrige la CAUSE du bug dans le fichier {name} sans changer son comportement ni son API publique.

Traceback :
{tb}

Contenu actuel de agent/{name} :
```python
{code}
```

Réponds UNIQUEMENT en JSON : {{"explanation": "cause + correctif en une phrase", "fixed_file": "contenu COMPLET du fichier corrigé"}}"""


def last_traceback(log):
    i = log.rfind("Traceback (most recent call last)")
    return log[i:][-6000:] if i >= 0 else log[-3000:]


def is_transient(tb):
    return bool(TRANSIENT.search(tb))


def culprit(tb):
    """Deepest patchable agent file in the traceback, or None."""
    for name in reversed(re.findall(r'File "[^"]*[\\/]agent[\\/](\w+\.py)", line \d+', tb)):
        if name in PATCHABLE:
            return name
    return None


def verify():
    for f in AGENT.glob("*.py"):
        py_compile.compile(str(f), doraise=True)
    r = subprocess.run([sys.executable, "-m", "agent.selftest"], cwd=ROOT, capture_output=True, text=True, timeout=300)
    return r.returncode == 0, (r.stdout + r.stderr)[-1500:]


def heal(log_path):
    tb = redact(last_traceback(open(log_path, encoding="utf-8", errors="replace").read()))
    last_line = tb.strip().splitlines()[-1] if tb.strip() else "?"

    if is_transient(tb):
        log_event("heal", status="transient", error=last_line[:300])
        notify.alert(f"⚠️ <b>Panne externe</b> (API/réseau), pas de bug de code. Nouvelle tentative auto.\n"
                     f"<code>{html.escape(last_line[:300])}</code>")
        return "transient"

    name = culprit(tb)
    if not name:
        log_event("heal", status="no-target", error=last_line[:300])
        notify.alert(f"🛑 <b>Crash hors zone réparable</b>\n<code>{html.escape(last_line[:300])}</code>")
        return "no-target"

    path = AGENT / name
    backup = path.read_bytes()  # byte-exact rollback
    old = backup.decode("utf-8")
    try:
        data, provider = llm.ask_json(HEAL_PROMPT.format(name=name, tb=tb, code=old), required=("fixed_file",))
        new = data["fixed_file"]
        if len(new) < 0.5 * len(old):
            raise ValueError("patch suspect (fichier tronqué)")
        path.write_bytes(new.encode("utf-8"))
        ok, out = verify()
    except Exception as e:
        ok, out, provider, data = False, str(e), "?", {}
    if not ok:
        path.write_bytes(backup)  # rollback

    status = "patched" if ok else "rejected"
    explanation = data.get("explanation", "")[:400]
    log_event("heal", status=status, file=name, error=last_line[:300], explanation=explanation)
    icon = "🩹 <b>Auto-réparé</b>" if ok else "❌ <b>Patch rejeté (rollback)</b>"
    notify.alert(f"{icon} <code>agent/{name}</code> via {provider}\nErreur : <code>{html.escape(last_line[:300])}</code>\n"
                 f"{html.escape(explanation or out[-500:])}")
    return status


if __name__ == "__main__":
    print(heal(sys.argv[1]))
