"""Offline self-test. The healer only keeps a patch when this passes."""
import pathlib
import tempfile

from agent.heal import culprit, is_transient
import io

from PIL import Image

from agent.image import fallback_svg, to_jpeg
from agent.llm import pick_gemini, pick_groq
from agent.promote import pending_urls
from agent.site import build_index, link_placeholders, render_markdown, slugify, write_post


def main():
    assert slugify("Éléphant & Co !") == "elephant-co"
    assert slugify("!!!") == "article"
    assert slugify("mot " * 30).endswith("mot") and len(slugify("mot " * 30)) <= 70

    md = link_placeholders("Voir [[offer:x]] et [[amazon:clavier sans fil]]",
                           {"x": {"name": "X", "url": "https://x.io"}}, "tag-21")
    assert "[X](https://x.io)" in md and "tag=tag-21" in md, md
    assert link_placeholders("[[amazon:clavier]] [[offer:nope]]", {}, "") == "clavier nope"
    assert 'rel="sponsored' in render_markdown("## T\n\n[a](https://e.com)")

    assert "&lt;Titre&gt;" in fallback_svg("<Titre>")
    buf = io.BytesIO()
    Image.new("RGB", (1024, 1024), "red").save(buf, "PNG")
    jpg = Image.open(io.BytesIO(to_jpeg(buf.getvalue())))
    assert jpg.format == "JPEG" and jpg.size == (1024, 576), jpg.size

    gen = ["generateContent"]
    picked = pick_gemini([{"name": f"models/{n}", "supportedGenerationMethods": gen} for n in
                          ("gemini-2.0-flash", "gemini-3-flash-preview", "gemini-3-flash", "gemini-3-flash-lite",
                           "gemini-3-pro", "gemini-3-flash-image")]
                         + [{"name": "models/gemini-9-flash", "supportedGenerationMethods": ["embedContent"]}])
    assert picked == ["gemini-3-flash", "gemini-3-flash-preview", "gemini-2.0-flash"], picked
    assert pick_groq(["whisper-large-v3", "qwen3-32b", "openai/gpt-oss-120b"])[:2] == ["openai/gpt-oss-120b", "qwen3-32b"]

    assert is_transient("requests.exceptions.ReadTimeout: boom")
    assert is_transient("RuntimeError: LLM_UNAVAILABLE: gemini#1: 429")
    assert not is_transient("KeyError: 'title'")
    assert culprit('File "/r/agent/main.py", line 9\nFile "/r/agent/site.py", line 3, in f') == "site.py"
    assert culprit('File "C:\\r\\agent\\llm.py", line 3') is None

    assert pending_urls([{"slug": "a"}], "https://h/r", set()) == ["https://h/r/p/a.html", "https://h/r/"]
    assert pending_urls([{"slug": "a"}], "https://h/r", {"https://h/r/p/a.html"}) == []

    cfg = {"site_name": "T", "site_tagline": "t", "indexnow_key": "abc123"}
    post = {"slug": "a-b", "title": "A <b>", "description": "d", "image": "a-b.jpg", "date": "2026-01-01"}
    with tempfile.TemporaryDirectory() as d:
        docs = pathlib.Path(d)
        write_post(docs, post, "## Hello\n\ntext", cfg, "https://x.github.io/r")
        build_index(docs, [post], cfg, "https://x.github.io/r")
        page = (docs / "p" / "a-b.html").read_text(encoding="utf-8")
        assert "A &lt;b&gt;" in page and "<h2>Hello</h2>" in page
        assert "https://x.github.io/r/p/a-b.html" in (docs / "sitemap.xml").read_text(encoding="utf-8")
        assert "<item><title>A &lt;b&gt;</title>" in (docs / "feed.xml").read_text(encoding="utf-8")
        assert (docs / "abc123.txt").read_text(encoding="utf-8") == "abc123"
    print("selftest OK")


if __name__ == "__main__":
    main()
