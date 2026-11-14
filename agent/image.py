"""Free AI image generation: Pollinations (no key) -> Cloudflare Workers AI (free) -> SVG card."""
import base64
import html
import os
import random
import textwrap
import time
from urllib.parse import quote

import requests


def _pollinations(prompt):
    headers = {"Authorization": f"Bearer {os.environ['POLLINATIONS_TOKEN']}"} if os.getenv("POLLINATIONS_TOKEN") else {}
    url = (f"https://image.pollinations.ai/prompt/{quote(prompt[:800])}"
           f"?width=1200&height=630&nologo=true&model=flux&seed={random.randint(1, 10**6)}")
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
    providers = [("pollinations", _pollinations)]
    if os.getenv("CF_ACCOUNT_ID") and os.getenv("CF_API_TOKEN"):
        providers.append(("cloudflare", _cloudflare))
    errors = []
    for name, call in providers:
        for attempt in range(2):
            try:
                path = out_dir / f"{slug}.jpg"
                path.write_bytes(call(prompt))
                return path, name
            except Exception as e:
                errors.append(f"{name}#{attempt + 1}: {str(e)[:150]}")
                time.sleep(8 * (attempt + 1))
    path = out_dir / f"{slug}.svg"
    path.write_text(fallback_svg(title), encoding="utf-8")
    return path, "svg-fallback (" + "; ".join(errors) + ")"
