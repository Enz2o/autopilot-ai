"""Free LLM brains with automatic failover: Gemini (Google AI Studio) -> Groq."""
import json
import os
import re
import time

import requests


_SKIP = re.compile(r"lite|image|tts|live|audio|embed|exp|thinking|vision|guard|whisper|robotics|computer|native", re.I)
_GROQ_PREF = [r"gpt-oss-120b", r"llama-4-maverick", r"llama-3\.3-70b", r"kimi", r"qwen", r"gpt-oss-20b"]
_cache = {}


def pick_gemini(models):
    """Newest stable 'flash' text model from the models.list payload (models retire, names change)."""
    def version(name):
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
        return float(m.group(1)) if m else 0.0
    names = [m["name"].removeprefix("models/") for m in models
             if "generateContent" in m.get("supportedGenerationMethods", [])
             and re.fullmatch(r"gemini-[\d.]+-flash(-preview.*|-latest|-\d+)?", m["name"].removeprefix("models/"))
             and not _SKIP.search(m["name"])]
    return sorted(names, key=lambda n: (version(n), "preview" not in n), reverse=True)


def pick_groq(ids):
    chat = [i for i in ids if not _SKIP.search(i)]
    ordered = [i for p in _GROQ_PREF for i in chat if re.search(p, i)]
    return list(dict.fromkeys(ordered + chat))


def _models(provider):
    if provider not in _cache:
        if provider == "gemini":
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 200},
                             headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, timeout=60)
            r.raise_for_status()
            found = pick_gemini(r.json().get("models", []))
        else:
            r = requests.get("https://api.groq.com/openai/v1/models",
                             headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}, timeout=60)
            r.raise_for_status()
            found = pick_groq([m["id"] for m in r.json().get("data", []) if m.get("active", True)])
        env = os.getenv(f"{provider.upper()}_MODEL")
        _cache[provider] = ([env] if env else []) + found[:3]
        print(f"[llm] {provider} modèles: {_cache[provider]}")
    return _cache[provider]


def _try_models(provider, call):
    """Call with each discovered model; a 404 (retired model) moves to the next one."""
    last = None
    for model in _models(provider):
        try:
            return call(model)
        except requests.HTTPError as e:
            last = e
            if e.response is None or e.response.status_code not in (400, 404, 429, 500, 503):
                raise
    raise last or RuntimeError(f"{provider}: aucun modèle disponible")


def _gemini(prompt):
    return _try_models("gemini", lambda model: _gemini_call(prompt, model))


def _groq(prompt):
    return _try_models("groq", lambda model: _groq_call(prompt, model))


def _gemini_call(prompt, model):
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},  # header, not URL: keeps key out of errors
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
        },
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _groq_call(prompt, model):
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.9,
        },
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


PROVIDERS = [("gemini", "GEMINI_API_KEY", _gemini), ("groq", "GROQ_API_KEY", _groq)]


def parse_json(text):
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    return json.loads(text)


def ask_json(prompt, required=()):
    """Return (dict, provider). Tries every provider 3x before raising LLM_UNAVAILABLE."""
    errors = []
    for name, env, call in PROVIDERS:
        if not os.getenv(env):
            errors.append(f"{name}: pas de clé {env}")
            continue
        for attempt in range(3):
            try:
                data = parse_json(call(prompt))
                missing = [k for k in required if not data.get(k)]
                if missing:
                    raise ValueError(f"champs manquants {missing}")
                return data, name
            except Exception as e:  # network, quota, bad JSON: retry then fail over
                detail = getattr(getattr(e, "response", None), "text", "")[:200]
                errors.append(f"{name}#{attempt + 1}: {str(e)[:200]} {detail}")
                print(f"[llm] échec {errors[-1]}")
                time.sleep(3 * 2 ** attempt)
    raise RuntimeError("LLM_UNAVAILABLE: " + " | ".join(errors))
