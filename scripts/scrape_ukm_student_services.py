# UKM Student Services Scraper (targeted)
# Crawls curated pages from UKM Akademik (academic services) and HEPUKM
# (Centre for Student Affairs) into two separate corpus files, so retraining
# only embeds these NEW files (VectorStoreService.load_document is incremental
# by content hash).
#
# Usage:
#   python scripts/scrape_ukm_student_services.py            # scrape only
#   python scripts/scrape_ukm_student_services.py --train    # scrape + reindex
#
# Note: hepukm/en is JS-rendered (empty via static fetch); use the Malay site.

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "data" / "ukm_ftsm"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MIN_TEXT_CHARS = 400  # pages with less real text are skipped (nav-only shells)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ms;q=0.8",
}

# Curated UKM Akademik pages (static-fetchable, content-rich, student-relevant)
AKADEMIK_URLS = [
    ("https://www.ukm.my/akademik/soalan_lazim", "Soalan Lazim / Academic FAQ"),
    ("https://www.ukm.my/akademik/international-student-visa", "International Student Visa"),
    ("https://www.ukm.my/akademik/kalendar", "Kalendar Akademik / Academic Calendar"),
    ("https://www.ukm.my/akademik/kemasukan-pelajar", "Kemasukan Pelajar / Student Admission"),
    ("https://www.ukm.my/akademik/kemasukan-pelajar-antarabangsa-2", "International Student Admission"),
    ("https://www.ukm.my/akademik/kemasukan-pascasiswazah", "Postgraduate Admission"),
    ("https://www.ukm.my/akademik/pelajar-prasiswazah", "Undergraduate Information"),
    ("https://www.ukm.my/akademik/pekeliling-akademik-ukm", "Pekeliling Akademik / Academic Circulars"),
    ("https://www.ukm.my/akademik/muat-turun", "Muat Turun / Downloads"),
]

HEP_ROOT = "https://www.ukm.my/hepukm/"
HEP_MAX_PAGES = 15
HEP_EXCLUDE_PARTS = ("/3d-flip-book", "/ats-2025", "/news")  # flipbook viewers & news noise


def _clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        tag.decompose()
    main = (soup.find("main") or soup.find("article")
            or soup.find(class_="entry-content") or soup.find(id="content")
            or soup.body or soup)
    lines = [ln.strip() for ln in main.get_text("\n").splitlines()]
    lines = [ln for ln in lines if ln]
    # collapse consecutive duplicates (WP themes repeat menu items)
    out: list[str] = []
    for ln in lines:
        if not out or out[-1] != ln:
            out.append(ln)
    return "\n".join(out)


def fetch_page(session: requests.Session, url: str) -> tuple[str, str] | None:
    """Return (title, text) or None if not worth indexing."""
    try:
        r = session.get(url, timeout=25, headers=HEADERS, allow_redirects=True)
    except Exception as exc:
        print(f"[SKIP] {url} -> {exc}")
        return None
    if r.status_code != 200:
        print(f"[SKIP] {url} -> HTTP {r.status_code}")
        return None
    if "text/html" not in r.headers.get("content-type", ""):
        print(f"[SKIP] {url} -> not html")
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else url)
    text = _clean_text(soup)
    if len(text) < MIN_TEXT_CHARS:
        print(f"[SKIP] {url} -> only {len(text)} chars (likely JS-rendered)")
        return None
    return title[:150], text


def write_corpus(out_file: Path, source_label: str, source_url: str, pages: list[dict]) -> None:
    tmp = out_file.with_suffix(out_file.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(f"{source_label}\n")
        f.write(f"Source URL: {source_url}\n")
        f.write(f"Crawled at: {datetime.now().isoformat()}\n")
        f.write(f"Total pages: {len(pages)}\n")
        f.write("=" * 80 + "\n\n")
        for i, p in enumerate(pages, 1):
            f.write(f"[Page {i}]\n")
            f.write(f"URL: {p['url']}\n")
            f.write(f"Title: {p['title']}\n")
            f.write(f"\n{p['text']}\n")
            f.write("\n" + "-" * 60 + "\n\n")
    os.replace(tmp, out_file)
    print(f"[SAVE] {out_file} ({len(pages)} pages, {out_file.stat().st_size} bytes)")


def crawl_akademik(session: requests.Session) -> list[dict]:
    pages: list[dict] = []
    for url, label in AKADEMIK_URLS:
        got = fetch_page(session, url)
        if got:
            title, text = got
            pages.append({"url": url, "title": f"{label} — {title}", "text": text})
            print(f"[OK]   {url} ({len(text)} chars)")
        time.sleep(0.5)
    return pages


def crawl_hepukm(session: requests.Session) -> list[dict]:
    visited: set[str] = set()
    queue = [HEP_ROOT]
    pages: list[dict] = []
    while queue and len(pages) < HEP_MAX_PAGES:
        url = queue.pop(0).rstrip("/")
        if url in visited:
            continue
        visited.add(url)
        got = fetch_page(session, url)
        if not got:
            continue
        title, text = got
        pages.append({"url": url, "title": title, "text": text})
        print(f"[OK]   {url} ({len(text)} chars)")
        # follow internal hepukm links one level deep
        r = session.get(url, timeout=25, headers=HEADERS)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            link = urljoin(r.url, a["href"]).split("#")[0].rstrip("/")
            parsed = urlparse(link)
            if "ukm.my" not in parsed.netloc or "/hepukm" not in parsed.path:
                continue
            if any(part in link for part in HEP_EXCLUDE_PARTS):
                continue
            if link not in visited and link not in queue and len(queue) < 25:
                queue.append(link)
        time.sleep(0.5)
    return pages


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="UKM student-services scraper")
    parser.add_argument("--train", action="store_true", help="Reindex vector store after scraping")
    args = parser.parse_args()

    session = requests.Session()

    ak = crawl_akademik(session)
    if ak:
        write_corpus(OUTPUT_DIR / "ukm_akademik_services.txt",
                     "UKM Akademik (Academic Services) Official Pages",
                     "https://www.ukm.my/akademik/", ak)

    hep = crawl_hepukm(session)
    if hep:
        write_corpus(OUTPUT_DIR / "ukm_hepukm_student_affairs.txt",
                     "UKM HEPUKM (Centre for Student Affairs) Official Pages (Bahasa Melayu)",
                     HEP_ROOT, hep)

    total = len(ak) + len(hep)
    print(f"\n[DONE] {total} pages scraped ({len(ak)} akademik + {len(hep)} hepukm)")
    if total == 0:
        print("[WARN] nothing scraped; existing files preserved")
        return 1

    if args.train:
        from rag.vector_store import VectorStoreService
        from utils.indexing_lock import indexing_lock
        with indexing_lock:
            vs = VectorStoreService()
            result = vs.load_document()
        # Per-file failures (e.g. a textless PDF) do NOT abort the batch; only
        # complain if NOTHING was indexed at all.
        if not result.get("modified"):
            raise RuntimeError(result.get("error_summary") or "Nothing indexed")
        if result.get("errors"):
            print(f"[WARN] {len(result['errors'])} file(s) skipped: {result['errors']}")
        print("[DONE] vector store reindexed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
