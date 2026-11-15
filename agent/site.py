"""Static SEO site written to docs/ (served free by GitHub Pages)."""
import html
import re
import unicodedata
from urllib.parse import quote_plus

import markdown

CSS = """
:root{--bg:#fafaf9;--fg:#1c1917;--mut:#57534e;--acc:#4f46e5;--card:#fff;--bd:#e7e5e4}
@media(prefers-color-scheme:dark){:root{--bg:#0c0a09;--fg:#f5f5f4;--mut:#a8a29e;--acc:#818cf8;--card:#1c1917;--bd:#292524}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.7 system-ui,sans-serif}
.w{max-width:760px;margin:auto;padding:24px 16px}a{color:var(--acc)}img{max-width:100%;height:auto;border-radius:12px}
header a{text-decoration:none;color:var(--fg);font-weight:800;font-size:1.3rem}.mut{color:var(--mut);font-size:.9rem}
.note{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 14px;font-size:.85rem;color:var(--mut)}
.grid{display:grid;gap:20px}.card{background:var(--card);border:1px solid var(--bd);border-radius:14px;overflow:hidden}
.card div{padding:12px 16px}.card h2{font-size:1.15rem;margin:0 0 6px;line-height:1.35}.card a{text-decoration:none;color:inherit}
"""


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(slug) > 70:
        slug = slug[:71].rsplit("-", 1)[0]  # cut on a word boundary
    return slug or "article"


def link_placeholders(md, offers, amazon_tag):
    """[[offer:id]] -> affiliate link, [[amazon:keywords]] -> tagged Amazon search (or plain text)."""
    def repl(m):
        kind, value = m.group(1), m.group(2).strip()
        if kind == "offer":
            offer = offers.get(value)
            return f"[{offer['name']}]({offer['url']})" if offer else value
        if not amazon_tag:
            return value
        return f"[{value}](https://www.amazon.fr/s?k={quote_plus(value)}&tag={quote_plus(amazon_tag)})"
    return re.sub(r"\[\[(offer|amazon):([^\]]+)\]\]", repl, md)


def render_markdown(md):
    body = markdown.markdown(md, extensions=["extra"])
    return body.replace('<a href="http', '<a rel="sponsored nofollow noopener" target="_blank" href="http')


def _page(title, description, body, cfg, canonical="", image="", prefix=""):
    t, d = html.escape(title), html.escape(description)
    og = f'<meta property="og:image" content="{html.escape(image)}">' if image else ""
    can = f'<link rel="canonical" href="{html.escape(canonical)}">' if canonical else ""
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{t}</title>
<meta name="description" content="{d}"><meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">{og}{can}
<link rel="alternate" type="application/rss+xml" title="RSS" href="{prefix}feed.xml"><style>{CSS}</style></head>
<body><div class="w"><header><a href="{prefix}index.html">{html.escape(cfg['site_name'])}</a>
<div class="mut">{html.escape(cfg.get('site_tagline', ''))}</div></header><main>{body}</main>
<footer class="mut"><p>Certains liens sont affiliés : si tu achètes via ces liens, le site peut toucher une commission,
sans surcoût pour toi. Contenu rédigé avec l'aide d'une IA.</p></footer></div></body></html>"""


def write_post(docs, post, body_md, cfg, base_url):
    (docs / "p").mkdir(parents=True, exist_ok=True)
    body = (f'<article><h1>{html.escape(post["title"])}</h1><p class="mut">{post["date"]}</p>'
            f'<p class="note">Article contenant des liens affiliés.</p>'
            f'<img src="../img/{post["image"]}" alt="{html.escape(post["title"])}" width="1200" height="630">'
            f"{render_markdown(body_md)}</article>")
    page = _page(post["title"], post["description"], body, cfg,
                 canonical=f"{base_url}/p/{post['slug']}.html" if base_url else "",
                 image=f"{base_url}/img/{post['image']}" if base_url else "", prefix="../")
    (docs / "p" / f"{post['slug']}.html").write_text(page, encoding="utf-8")


def build_index(docs, posts, cfg, base_url):
    docs.mkdir(parents=True, exist_ok=True)
    cards = "".join(
        f'<a class="card" href="p/{p["slug"]}.html"><img src="img/{p["image"]}" alt="" loading="lazy" '
        f'width="1200" height="630"><div><h2>{html.escape(p["title"])}</h2>'
        f'<div class="mut">{p["date"]} · {html.escape(p["description"])}</div></div></a>'
        for p in posts)
    (docs / "index.html").write_text(
        _page(cfg["site_name"], cfg.get("site_tagline", ""), f'<div class="grid">{cards}</div>', cfg,
              canonical=f"{base_url}/" if base_url else ""), encoding="utf-8")
    urls = [f"{base_url}/"] + [f"{base_url}/p/{p['slug']}.html" for p in posts]
    (docs / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{html.escape(u)}</loc></url>" for u in urls) + "</urlset>", encoding="utf-8")
    (docs / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n", encoding="utf-8")
    items = "".join(
        f"<item><title>{html.escape(p['title'])}</title><link>{base_url}/p/{p['slug']}.html</link>"
        f"<guid>{base_url}/p/{p['slug']}.html</guid><description>{html.escape(p['description'])}</description>"
        f"<pubDate>{p['date']}</pubDate></item>" for p in posts[:30])
    (docs / "feed.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{html.escape(cfg["site_name"])}'
        f"</title><link>{base_url}/</link><description>{html.escape(cfg.get('site_tagline', ''))}</description>"
        f"{items}</channel></rss>", encoding="utf-8")
    if cfg.get("indexnow_key"):  # IndexNow ownership proof
        (docs / f"{cfg['indexnow_key']}.txt").write_text(cfg["indexnow_key"], encoding="utf-8")
    (docs / ".nojekyll").write_text("", encoding="utf-8")
