"""Free LLM brains with automatic failover: Gemini (Google AI Studio) -> Groq."""
import json
import os
import re
import time

import requests


def _gemini(prompt):
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
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


def _groq(prompt):
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
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
                errors.append(f"{name}#{attempt + 1}: {str(e)[:200]}")
                time.sleep(3 * 2 ** attempt)
    raise RuntimeError("LLM_UNAVAILABLE: " + " | ".join(errors))
