"""Pipeline: LLM writes article + image prompt -> AI image -> static site -> Telegram channel -> log."""
import json
import os
import sys
import traceback

from agent import image, llm, notify, site
from agent.common import CFG, DOCS, STATE, log_event, now, site_url

POSTS = STATE / "posts.json"

PROMPT = """Tu es rédacteur web SEO expert. Écris en {language} un article UTILE et HONNÊTE pour un blog.
Niche : {niche}
Audience : {audience}
Offres partenaires disponibles (id: nom — description) :
{offers}

Titres déjà publiés (ne les répète pas, trouve un angle nouveau) :
{published}

Règles :
- 900 à 1300 mots, structure avec des titres ## et des listes, conseils concrets et actionnables.
- N'invente aucun prix, chiffre, témoignage ou fonctionnalité dont tu n'es pas sûr.
- Pour citer une offre partenaire pertinente, écris exactement [[offer:ID]] (3 fois maximum, seulement si pertinent).
- Pour recommander un produit physique, écris [[amazon:mots clés produit]] (2 fois maximum).
- image_prompt : en anglais, illustration éditoriale percutante, couleurs vives, AUCUN texte ni logo dans l'image.
- telegram_caption : accroche de 300 caractères max avec 1 ou 2 emojis, sans lien.

Réponds UNIQUEMENT en JSON avec les clés :
{{"title": "...", "description": "meta description 150 caractères", "body_markdown": "...",
"image_prompt": "...", "telegram_caption": "..."}}"""


def load_posts():
    return json.loads(POSTS.read_text(encoding="utf-8")) if POSTS.exists() else []


def save_posts(posts):
    STATE.mkdir(exist_ok=True)
    POSTS.write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")


def create_post(posts):
    offers = {o["id"]: o for o in CFG.get("offers", [])}
    amazon_tag = os.getenv("AMAZON_TAG") or CFG.get("amazon_tag", "")
    prompt = PROMPT.format(
        language=CFG.get("language", "français"), niche=CFG["niche"], audience=CFG["audience"],
        offers="\n".join(f"- {o['id']}: {o['name']} — {o.get('pitch', '')}" for o in offers.values()) or "(aucune)",
        published="\n".join(f"- {p['title']}" for p in posts[:60]) or "(aucun)",
    )
    data, provider = llm.ask_json(prompt, required=("title", "body_markdown", "image_prompt", "telegram_caption"))

    taken = {p["slug"] for p in posts}
    slug = base = site.slugify(data["title"])
    n = 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1

    img_path, img_source = image.generate(data["image_prompt"], slug, data["title"], DOCS / "img")
    base_url = site_url()
    post = {"slug": slug, "title": data["title"].strip(), "description": (data.get("description") or "")[:160],
            "image": img_path.name, "date": now().strftime("%Y-%m-%d")}
    site.write_post(DOCS, post, site.link_placeholders(data["body_markdown"], offers, amazon_tag), CFG, base_url)
    posts.insert(0, post)
    save_posts(posts)
    site.build_index(DOCS, posts, CFG, base_url)

    url = f"{base_url}/p/{slug}.html"
    on_telegram = notify.publish_channel(img_path, f"{data['telegram_caption'].strip()}\n\n👉 {url}")
    log_event("post", title=post["title"], url=url, image=f"{base_url}/img/{img_path.name}",
              llm=provider, image_source=img_source, telegram=on_telegram)
    print(f"publié: {post['title']} -> {url} [llm={provider}, image={img_source}, telegram={on_telegram}]")


def run():
    posts = load_posts()
    for _ in range(int(CFG.get("posts_per_run", 1))):
        create_post(posts)


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        log_event("error", error=f"{type(e).__name__}: {e}"[:500])
        traceback.print_exc()
        sys.exit(1)
