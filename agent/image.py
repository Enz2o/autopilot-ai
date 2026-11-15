"""AI images: Gemini image model (existing key) -> Pollinations (no key) -> Cloudflare (optional) -> SVG card.

Every image gets the same art direction so the site looks like one magazine, not random AI renders,
and is re-encoded as a ~150 KB JPEG so the repo and GitHub Pages stay small.
"""
import base64
import html
import io
import json
import os
import random
import re
import sys
import textwrap
import time
from urllib.parse import quote

import requests
from PIL import Image

STYLE = (" Art direction: flat editorial vector illustration for a modern magazine, minimal clean geometric shapes, "
         "subtle paper grain texture, limited palette of deep indigo, coral and warm cream, generous negative space, "
         "one clear central metaphor, soft shadows. No text, no letters, no logos, no robots, no glowing brains, "
         "no holograms, no 3D render.")
GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"


def _gemini(prompt):
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
    r = requests.get(GEMINI, params={"pageSize": 200}, headers=headers, timeout=60)
    r.raise_for_status()
    models = sorted((m["name"].removeprefix("models/") for m in r.json().get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])
                     and re.search(r"gemini.*image", m["name"])), reverse=True)
    last = "aucun modèle image Gemini"
    for model in models[:3]:
        r = requests.post(f"{GEMINI}/{model}:generateContent", headers=headers, timeout=180, json={
            "contents": [{"parts": [{"text": "Generate one wide 16:9 image. " + prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"aspectRatio": "16:9"}}})
        if not r.ok:
            last = f"{model}: HTTP {r.status_code} {r.text[:150]}"
            continue
        for part in r.json().get("candidates", [{}])[0].get("content", {}).get("parts", []):
            if "inlineData" in part:
                return base64.b64decode(part["inlineData"]["data"])
        last = f"{model}: pas d'image dans la réponse"
    raise RuntimeError(last)


def _pollinations(prompt):
    headers = {"Authorization": f"Bearer {os.environ['POLLINATIONS_TOKEN']}"} if os.getenv("POLLINATIONS_TOKEN") else {}
    url = (f"https://image.pollinations.ai/prompt/{quote(prompt[:900])}"
           f"?width=1200&height=675&nologo=true&model=flux&seed={random.randint(1, 10**6)}")
    r = requests.get(url, headers=headers, timeout=240)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/") or len(r.content) < 10_000:
        raise ValueError(f"réponse non-image ({r.headers.get('content-type')}, {len(r.content)} o)")
    return r.content


def _cloudflare(prompt):
    account, token = os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"]
    r = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/black-forest-labs/flux-1-schnell",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": prompt[:2000], "steps": 6},
        timeout=180,
    )
    r.raise_for_status()
    return base64.b64decode(r.json()["result"]["image"])


def to_jpeg(data, width=1200):
    """Any image bytes -> compact 16:9 JPEG (center crop)."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    target_h = round(w * 9 / 16)
    if h > target_h:
        top = (h - target_h) // 2
        img = img.crop((0, top, w, top + target_h))
    img.thumbnail((width, width))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    return out.getvalue()


def fallback_svg(title):
    lines = textwrap.wrap(title, 32)[:4]
    tspans = "".join(f'<tspan x="80" dy="{0 if i == 0 else 78}">{html.escape(l)}</tspan>' for i, l in enumerate(lines))
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#4f46e5"/><stop offset="1" stop-color="#db2777"/></linearGradient></defs>'
        '<rect width="1200" height="630" fill="url(#g)"/>'
        f'<text y="{300 - 39 * (len(lines) - 1)}" fill="#fff" font-family="Arial,sans-serif" font-size="64" '
        f'font-weight="700">{tspans}</text></svg>'
    )


def generate(prompt, slug, title, out_dir):
    """Return (path, source). Never raises: worst case is an SVG title card."""
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = prompt.strip() + STYLE
    providers = []
    if os.getenv("GEMINI_API_KEY"):
        providers.append(("gemini", _gemini))
    providers.append(("pollinations", _pollinations))
    if os.getenv("CF_ACCOUNT_ID") and os.getenv("CF_API_TOKEN"):
        providers.append(("cloudflare", _cloudflare))
    errors = []
    for name, call in providers:
        for attempt in range(2):
            try:
                path = out_dir / f"{slug}.jpg"
                path.write_bytes(to_jpeg(call(prompt)))
                if errors:
                    print(f"[image] échecs avant {name}: {errors}")
                return path, name
            except Exception as e:
                errors.append(f"{name}#{attempt + 1}: {str(e)[:150]}")
                time.sleep(8 * (attempt + 1))
    path = out_dir / f"{slug}.svg"
    path.write_text(fallback_svg(title), encoding="utf-8")
    return path, "svg-fallback (" + "; ".join(errors) + ")"


if __name__ == "__main__":
    # python -m agent.image regen : redraw every existing article image in the current style
    if sys.argv[1:] == ["regen"]:
        from agent.common import DOCS, STATE
        for post in json.loads((STATE / "posts.json").read_text(encoding="utf-8")):
            if post["image"].endswith(".jpg"):
                path, source = generate(f"Cover illustration for an article titled: {post['title']}.",
                                        post["slug"], post["title"], DOCS / "img")
                print(f"{post['slug']}: {source}")
