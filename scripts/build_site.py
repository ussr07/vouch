"""Build the static GitHub Pages demo into _site/ (standard library only).

Run from the project folder:  python scripts/build_site.py
The page is the real app/static page. Two things differ from the local app: asset paths are
relative (Pages serves the site under /vouch/), and window.VOUCH_DEMO lists the saved briefs in
demo/briefs/, which the page loads as files instead of asking the server.
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
BRIEFS = ROOT / "demo" / "briefs"
OUT = ROOT / "_site"


def replace_all(text: str, old: str, new: str, expected_min: int = 1) -> str:
    """Replace, and fail loudly if the page no longer contains what this build expects."""
    count = text.count(old)
    if count < expected_min:
        raise SystemExit(f"build_site: expected {old!r} in the page, found it {count} times")
    return text.replace(old, new)


def build() -> None:
    index = json.loads((BRIEFS / "index.json").read_text(encoding="utf-8"))
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(STATIC, OUT / "static")
    shutil.copytree(BRIEFS, OUT / "briefs")

    page = (STATIC / "index.html").read_text(encoding="utf-8")
    page = replace_all(page, '"/static/', '"static/', expected_min=4)
    page = replace_all(page, 'href="/"', 'href="./"')
    demo = json.dumps(index, ensure_ascii=False).replace("</", "<\\/")
    page = replace_all(page, '<script src="static/stats.js',
                       f'<script>window.VOUCH_DEMO = {demo};</script>\n<script src="static/stats.js')
    (OUT / "index.html").write_text(page, encoding="utf-8")

    app = (OUT / "static" / "app.js").read_text(encoding="utf-8")
    app = replace_all(app, 'src: "/static/', 'src: "static/')
    (OUT / "static" / "app.js").write_text(app, encoding="utf-8")

    (OUT / ".nojekyll").write_text("", encoding="utf-8")   # serve files as they are
    print(f"built {OUT} with {len(index)} demo briefs")


if __name__ == "__main__":
    build()
