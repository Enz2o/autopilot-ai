"""Article cover images.

Default: a designed magazine-style cover (serif title, brand palette, unique geometric composition seeded
by the slug), rendered locally with Pillow: free, no account, never down, no "AI look".
Optional AI illustration if a working provider is configured (Cloudflare Workers AI, or a Pollinations token);
free Gemini keys have no image quota (HTTP 429) and anonymous Pollinations now answers 402.
"""
import base64
import io
import json
import os
import random
import sys
import time
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFont

from agent.common import CFG, DOCS, ROOT, STATE, site_url

W, H, S = 1200, 675, 2  # output size, supersampling factor for smooth edges
FONTS = ROOT / "fonts"
PALETTES = [  # background, text, accent 1, accent 2
    ("#F6F1E7", "#1E1B4B", "#F25F4C", "#4F46E5"),
    ("#1E1B4B", "#F6F1E7", "#F25F4C", "#FBBF77"),
    ("#FDE8E1", "#1E1B4B", "#4F46E5", "#F25F4C"),
    ("#E6ECF5", "#0F172A", "#F25F4C", "#1E1B4B"),
    ("#0F3D3E", "#F6F1E7", "#F2A65A", "#F6F1E7"),
]
STYLE = (" Art direction: flat editorial vector illustration for a modern magazine, minimal geometric shapes, "
         "limited palette of deep indigo, coral and warm cream, generous negative space. "
         "No text, no letters, no logos, no robots, no glowing brains, no 3D render.")


def _font(name, size, weight=None):
    try:
        font = ImageFont.truetype(str(FONTS / name), size)
        if weight:
            font.set_variation_by_axes([weight])
        return font
    except OSError:
        return ImageFont.load_default(size)


def _wrap(draw, text, font, max_width):
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return lines + [current] if current else lines


def cover(title, slug):
    """Designed 1200x675 JPEG cover. Same slug -> same composition."""
    rnd = random.Random(slug)
    bg, fg, a1, a2 = rnd.choice(PALETTES)
    img = Image.new("RGB", (W * S, H * S), bg)
    d = ImageDraw.Draw(img)

    # Right panel (x >= 700): big disc, offset half-disc, outline ring, dot grid. Shapes may bleed off the edges.
    def px(x, y):
        return (700 + x) * S, y * S
    cx, cy, r = rnd.randint(250, 330), rnd.randint(260, 420), rnd.randint(150, 200)
    x, y = px(cx, cy)
    d.ellipse((x - r * S, y - r * S, x + r * S, y + r * S), fill=a1)
    r2 = int(r * 0.7)
    ox, oy = px(cx + rnd.choice([-1, 1]) * r // 2, cy + rnd.choice([-1, 1]) * r // 2)
    start = rnd.choice([0, 90, 180, 270])
    d.pieslice((ox - r2 * S, oy - r2 * S, ox + r2 * S, oy + r2 * S), start, start + 180, fill=a2)
    rr = rnd.randint(45, 70)
    rx, ry = px(rnd.choice([90, 420]), rnd.choice([110, 560]))
    d.ellipse((rx - rr * S, ry - rr * S, rx + rr * S, ry + rr * S), outline=fg, width=5 * S)
    gx, gy = px(rnd.choice([40, 300]), rnd.choice([60, 520]))
    for i in range(6):
        for j in range(4):
            dx, dy = gx + i * 26 * S, gy + j * 26 * S
            d.ellipse((dx - 4 * S, dy - 4 * S, dx + 4 * S, dy + 4 * S), fill=fg)

    # Left column: label, accent bar, serif title (auto-fit to 4 lines max), domain.
    max_w = 600 * S
    for size in range(84, 40, -4):
        title_font = _font("DMSerifDisplay-Regular.ttf", size * S)
        lines = _wrap(d, title, title_font, max_w)
        if len(lines) <= 4:
            break
    label_font = _font("SpaceGrotesk.ttf", 22 * S, weight=700)
    small_font = _font("SpaceGrotesk.ttf", 20 * S, weight=500)
    line_h = int(size * 1.1) * S
    block_h = 70 * S + line_h * len(lines)
    top = (H * S - block_h) // 2
    d.text((72 * S, top), CFG["site_name"].upper(), font=label_font, fill=a1 if bg != a1 else fg)
    d.rectangle((72 * S, top + 42 * S, 128 * S, top + 48 * S), fill=a1)
    for i, line in enumerate(lines):
        d.text((72 * S, top + 70 * S + i * line_h), line, font=title_font, fill=fg)
    domain = site_url().removeprefix("https://") or CFG["site_name"]
    d.text((72 * S, (H - 56) * S), domain, font=small_font, fill=fg)

    out = io.BytesIO()
    img.resize((W, H), Image.LANCZOS).save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return out.getvalue()


def _pollinations(prompt):
    url = (f"https://image.pollinations.ai/prompt/{quote(prompt[:900])}"
           f"?width=1200&height=675&nologo=true&model=flux&seed={random.randint(1, 10**6)}")
    r = requests.get(url, headers={"Authorization": f"Bearer {os.environ['POLLINATIONS_TOKEN']}"}, timeout=240)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/"):
        raise ValueError(f"réponse non-image ({r.headers.get('content-type')})")
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


def to_jpeg(data, width=W):
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


def generate(prompt, slug, title, out_dir):
    """Return (path, source). Never raises: the designed cover is the default and the fallback."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slug}.jpg"
    providers = []
    if os.getenv("CF_ACCOUNT_ID") and os.getenv("CF_API_TOKEN"):
        providers.append(("cloudflare", _cloudflare))
    if os.getenv("POLLINATIONS_TOKEN"):
        providers.append(("pollinations", _pollinations))
    errors = []
    for name, call in providers:
        try:
            path.write_bytes(to_jpeg(call(prompt.strip() + STYLE)))
            return path, name
        except Exception as e:
            errors.append(f"{name}: {str(e)[:150]}")
            time.sleep(5)
    path.write_bytes(cover(title, slug))
    return path, "cover" + (f" ({'; '.join(errors)})" if errors else "")


if __name__ == "__main__":
    # python -m agent.image regen : redraw every existing article image in the current style
    if sys.argv[1:] == ["regen"]:
        posts = json.loads((STATE / "posts.json").read_text(encoding="utf-8"))
        for post in posts:
            path, source = generate(f"Cover for an article titled: {post['title']}.", post["slug"], post["title"],
                                    DOCS / "img")
            post["image"] = path.name
            print(f"{post['slug']}: {source}")
        for orphan in (DOCS / "img").glob("*.svg"):
            orphan.unlink()
        (STATE / "posts.json").write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")
