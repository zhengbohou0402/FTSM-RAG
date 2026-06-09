# FTSM Official Website Scraper
# Crawl all pages from https://ftsm.ukm.my/v6/, save to txt, train to Chroma vector store.
#
# Usage:
#   python scripts/scrape_ftsm_website.py
#   python scripts/scrape_ftsm_website.py --max-pages 80
#   python scripts/scrape_ftsm_website.py --no-train

import asyncio
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from playwright.async_api import async_playwright
except ImportError as exc:
    async_playwright = None
    _PLAYWRIGHT_IMPORT_ERROR = exc
else:
    _PLAYWRIGHT_IMPORT_ERROR = None

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as exc:
    requests = None
    BeautifulSoup = None
    _STATIC_IMPORT_ERROR = exc
else:
    _STATIC_IMPORT_ERROR = None

OUTPUT_DIR = PROJECT_ROOT / "data" / "ukm_ftsm"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://www.ftsm.ukm.my/v6/"
ALLOWED_DOMAIN = "ftsm.ukm.my"
ALLOWED_URL_PREFIXES = [
    "https://www.ftsm.ukm.my/",
    "https://ftsm.ukm.my/",
]

# Complete list of sub-pages extracted from navigation
SEED_URLS = [
    # Home & About
    "https://www.ftsm.ukm.my/v6",
    "https://www.ftsm.ukm.my/v6/background",
    "https://www.ftsm.ukm.my/v6/mission-faculty",
    "https://www.ftsm.ukm.my/v6/quality-statement",
    "https://www.ftsm.ukm.my/v6/chart",
    "https://www.ftsm.ukm.my/v6/faculty-map",
    "https://www.ftsm.ukm.my/v6/faculty-management",
    "https://www.ftsm.ukm.my/v6/why-choose-us",
    # Academic Programs
    "https://www.ftsm.ukm.my/v6/undergraduate",
    "https://www.ftsm.ukm.my/v6/master-program",
    "https://www.ftsm.ukm.my/v6/doctoral-programme",
    "https://www.ftsm.ukm.my/v6/entrepreneurship-programme",
    # Academic Staff
    "https://www.ftsm.ukm.my/v6/staff-academic",
    "https://www.ftsm.ukm.my/v6/staff-admin",
    "https://www.ftsm.ukm.my/v6/staff-ictsupport",
    "https://www.ftsm.ukm.my/v6/adjunct-professor",
    "https://www.ftsm.ukm.my/v6/emeritus-professor",
    "https://www.ftsm.ukm.my/v6/honorary-professor",
    "https://www.ftsm.ukm.my/v6/advisory-board",
    "https://www.ftsm.ukm.my/v6/external-examiner",
    "https://www.ftsm.ukm.my/v6/expertise",
    # Research
    "https://www.ftsm.ukm.my/v6/research-center",
    "https://www.ftsm.ukm.my/v6/research-university",
    "https://www.ftsm.ukm.my/v6/research-conference",
    "https://www.ftsm.ukm.my/v6/research-guidelineform",
    "https://www.ftsm.ukm.my/v6/publication",
    "https://www.ftsm.ukm.my/v6/technical-report",
    "https://www.ftsm.ukm.my/v6/editing-book",
    # Student Affairs
    "https://www.ftsm.ukm.my/v6/student-affair",
    "https://www.ftsm.ukm.my/v6/industrial-training",
    "https://www.ftsm.ukm.my/v6/fyp",
    "https://www.ftsm.ukm.my/v6/mobility-exchange",
    "https://www.ftsm.ukm.my/v6/hejim",
    # Units
    "https://www.ftsm.ukm.my/v6/unit-postgraduate",
    "https://www.ftsm.ukm.my/v6/unit-undergraduate",
    "https://www.ftsm.ukm.my/v6/unit-cait",
    "https://www.ftsm.ukm.my/v6/unit-cyber",
    "https://www.ftsm.ukm.my/v6/unit-softam",
    # Facilities & Others
    "https://www.ftsm.ukm.my/v6/facility",
    "https://www.ftsm.ukm.my/v6/download",
    "https://www.ftsm.ukm.my/v6/news-event",
    "https://www.ftsm.ukm.my/v6/alumni",
    "https://www.ftsm.ukm.my/v6/sustainability",
    "https://www.ftsm.ukm.my/v6/agreement",
    "https://www.ftsm.ukm.my/v6/online-survey",
]

SKIP_EXTENSIONS = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar', '.jpg', '.jpeg', '.png', '.gif']
MIN_SUCCESS_PAGES = 1


def _normalize_url(url: str) -> str:
    return str(url).strip().split("#")[0].rstrip("/")


def _load_crawler_config() -> None:
    global BASE_URL, SEED_URLS, SKIP_EXTENSIONS, ALLOWED_URL_PREFIXES

    config_path = PROJECT_ROOT / "config" / "crawler.yml"
    if not config_path.exists():
        return

    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"[WARN] Failed to read crawler config {config_path}: {exc}")
        return

    BASE_URL = _normalize_url(config.get("base_url") or BASE_URL) + "/"
    configured_prefixes = config.get("allowed_url_prefixes") or []
    if configured_prefixes:
        ALLOWED_URL_PREFIXES = [
            _normalize_url(prefix) + "/"
            for prefix in configured_prefixes
            if str(prefix).strip()
        ]

    configured_seeds = config.get("seed_urls") or []
    if configured_seeds:
        seen: set[str] = set()
        SEED_URLS = []
        for url in configured_seeds:
            normalized = _normalize_url(url)
            if normalized and normalized not in seen:
                seen.add(normalized)
                SEED_URLS.append(normalized)

    configured_skips = config.get("skip_extensions") or []
    if configured_skips:
        SKIP_EXTENSIONS = [
            ext.lower() if str(ext).startswith(".") else f".{str(ext).lower()}"
            for ext in configured_skips
        ]


_load_crawler_config()


@dataclass
class CrawlResult:
    output_file: Path
    pages_crawled: int
    pages_visited: int
    skipped_pages: int


def is_ftsm_url(url: str) -> bool:
    normalized = _normalize_url(url) + "/"
    if ALLOWED_URL_PREFIXES:
        return any(normalized.startswith(prefix) for prefix in ALLOWED_URL_PREFIXES)

    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain == ALLOWED_DOMAIN


def should_skip_url(url: str) -> bool:
    for ext in SKIP_EXTENSIONS:
        if url.lower().endswith(ext):
            return True
    skip_patterns = [
        r'\.pdf$',
        r'login',
        r'register',
        r'wp-admin',
        r'wp-login',
    ]
    for pattern in skip_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    return False


def clean_text(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if len(line) > 2:
            lines.append(line)
    return '\n'.join(lines)


async def extract_page(page, url: str) -> dict | None:
    """Visit single page, extract content and sub-links"""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)

        # Wait for body text length > 500
        for _ in range(30):
            body_len = await page.evaluate("document.body ? document.body.innerText.length : 0")
            if body_len > 500:
                break
            await asyncio.sleep(0.5)

        # Scroll to load lazy content
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)

        title = await page.title()
        body_len = await page.evaluate("document.body ? document.body.innerText.length : 0")
        print(f"  body={body_len}chars  title={title[:50]}")

        # Extract content from priority selectors
        raw_text = ""
        for selector in ["main", "article", "#app", "#content", ".content", "body"]:
            el = await page.query_selector(selector)
            if el:
                text = await el.inner_text()
                if text and len(text.strip()) > 300:
                    raw_text = text.strip()
                    break

        if not raw_text:
            print(f"  [skip] no content")
            return None

        content = clean_text(raw_text)
        if len(content) < 200:
            print(f"  [skip] too short after clean: {len(content)}")
            return None

        # Collect sub-links
        links = []
        elements = await page.query_selector_all("a[href]")
        for el in elements:
            href = await el.get_attribute("href")
            if href:
                full = urljoin(url, href).split("#")[0].rstrip("/")
                if full and is_ftsm_url(full) and not should_skip_url(full):
                    links.append(full)

        print(f"  OK  [{len(content)} chars]  {title[:60]}")
        return {"url": url, "title": title, "content": content, "links": links}

    except Exception as e:
        print(f"  ERR {url}: {e}")
        return None


def extract_page_static(session, url: str) -> dict | None:
    """Fetch a page with plain HTTP and extract readable text plus sub-links."""
    if requests is None or BeautifulSoup is None:
        raise RuntimeError(
            "Static crawler dependencies are missing. Install them with: "
            "pip install requests beautifulsoup4"
        ) from _STATIC_IMPORT_ERROR

    try:
        try:
            resp = session.get(url, timeout=25)
        except requests.exceptions.SSLError:
            print("  [warn] SSL verification failed; retrying without certificate verification")
            requests.packages.urllib3.disable_warnings()
            resp = session.get(url, timeout=25, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "noscript", "svg", "form", "iframe"]):
            tag.decompose()

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        raw_text = ""
        for selector in ["main", "article", "#content", ".content", ".entry-content", "body"]:
            el = soup.select_one(selector)
            if not el:
                continue
            text = el.get_text("\n", strip=True)
            if text and len(text) > 200:
                raw_text = text
                break

        content = clean_text(raw_text)
        if len(content) < 160:
            print(f"  [skip] static content too short: {len(content)}")
            return None

        links = []
        for el in soup.select("a[href]"):
            href = el.get("href")
            if not href:
                continue
            full = urljoin(url, href).split("#")[0].rstrip("/")
            if full and is_ftsm_url(full) and not should_skip_url(full):
                links.append(full)

        print(f"  OK  [{len(content)} chars]  {title[:60]}")
        return {"url": url, "title": title or url, "content": content, "links": links}
    except Exception as e:
        print(f"  ERR {url}: {e}")
        return None


def _write_pages_file(out_file: Path, all_pages: list[dict]) -> None:
    tmp_file = out_file.with_suffix(out_file.suffix + ".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        f.write("FTSM UKM Official Website Content\n")
        f.write(f"Source: {BASE_URL}\n")
        f.write(f"Crawled at: {datetime.now().isoformat()}\n")
        f.write(f"Total pages: {len(all_pages)}\n")
        f.write("=" * 80 + "\n\n")

        for i, p in enumerate(all_pages, 1):
            f.write(f"[Page {i}]\n")
            f.write(f"URL: {p['url']}\n")
            f.write(f"Title: {p['title']}\n")
            f.write(f"\n{p['content']}\n")
            f.write("\n" + "-" * 60 + "\n\n")

    if len(all_pages) < MIN_SUCCESS_PAGES or tmp_file.stat().st_size == 0:
        try:
            tmp_file.unlink()
        except OSError:
            pass
        raise RuntimeError(
            f"Scrape produced only {len(all_pages)} page(s); keeping existing file."
        )

    os.replace(tmp_file, out_file)


def crawl_static(max_pages: int = 80) -> CrawlResult | None:
    if requests is None or BeautifulSoup is None:
        raise RuntimeError(
            "Static crawler dependencies are missing. Install them with: "
            "pip install requests beautifulsoup4"
        ) from _STATIC_IMPORT_ERROR

    visited: set[str] = set()
    queue = [u.rstrip("/") for u in SEED_URLS]
    all_pages: list[dict] = []
    skipped_pages = 0

    print(f"\n{'='*60}")
    print(f"FTSM Static Website Scraper  |  Target: {BASE_URL}")
    print(f"Max pages: {max_pages}")
    print(f"{'='*60}\n")

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })

    count = 0
    while queue and count < max_pages:
        url = queue.pop(0).rstrip("/")
        if url in visited:
            skipped_pages += 1
            continue
        if should_skip_url(url):
            skipped_pages += 1
            continue

        visited.add(url)
        count += 1
        print(f"[{count}/{max_pages}] {url}")
        result = extract_page_static(session, url)
        if result:
            all_pages.append(result)
            for link in result["links"]:
                link = link.rstrip("/")
                if link not in visited and link not in queue:
                    queue.append(link)

    if not all_pages:
        print("\n[WARN] No static content scraped; existing file was preserved.")
        return None

    out_file = OUTPUT_DIR / "ftsm_official_website.txt"
    _write_pages_file(out_file, all_pages)

    print(f"\n[DONE] Total {len(all_pages)} pages crawled")
    print(f"[SAVE] {out_file}")
    return CrawlResult(
        output_file=out_file,
        pages_crawled=len(all_pages),
        pages_visited=len(visited),
        skipped_pages=skipped_pages,
    )


async def crawl_playwright(max_pages: int = 80, headless: bool = True) -> CrawlResult | None:
    if async_playwright is None:
        raise RuntimeError(
            "Playwright is not installed or Chromium is missing. "
            "Install it with: python -m playwright install chromium"
        ) from _PLAYWRIGHT_IMPORT_ERROR

    visited: set[str] = set()
    queue: list[str] = []

    # Add seed URLs to queue
    for u in SEED_URLS:
        u = u.rstrip("/")
        if u not in visited:
            queue.append(u)

    all_pages: list[dict] = []
    skipped_pages = 0

    print(f"\n{'='*60}")
    print(f"FTSM Official Website Scraper  |  Target: {BASE_URL}")
    print(f"Max pages: {max_pages}  |  Headless: {headless}")
    print(f"{'='*60}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Asia/Kuala_Lumpur",
        )
        page = await context.new_page()

        count = 0
        while queue and count < max_pages:
            url = queue.pop(0).rstrip("/")
            if url in visited:
                skipped_pages += 1
                continue
            if should_skip_url(url):
                skipped_pages += 1
                continue
            visited.add(url)
            count += 1

            print(f"[{count}/{max_pages}] {url}")
            result = await extract_page(page, url)
            if result:
                all_pages.append(result)
                for link in result["links"]:
                    link = link.rstrip("/")
                    if link not in visited and link not in queue:
                        queue.append(link)

            await asyncio.sleep(1.5)

        await browser.close()

    if not all_pages:
        print("\n[WARN] No content scraped, check network or try --no-headless")
        return None

    # Save to fixed filename
    out_file = OUTPUT_DIR / "ftsm_official_website.txt"
    _write_pages_file(out_file, all_pages)

    print(f"\n[DONE] Total {len(all_pages)} pages crawled")
    print(f"[SAVE] {out_file}")
    return CrawlResult(
        output_file=out_file,
        pages_crawled=len(all_pages),
        pages_visited=len(visited),
        skipped_pages=skipped_pages,
    )


async def crawl(max_pages: int = 80, headless: bool = True, allow_static_fallback: bool = True) -> CrawlResult | None:
    if async_playwright is None:
        if allow_static_fallback:
            print("[WARN] Playwright unavailable; falling back to static HTTP crawler.")
            return crawl_static(max_pages=max_pages)
        raise RuntimeError(
            "Playwright is not installed or Chromium is missing. "
            "Install it with: python -m playwright install chromium"
        ) from _PLAYWRIGHT_IMPORT_ERROR

    try:
        result = await crawl_playwright(max_pages=max_pages, headless=headless)
    except Exception as exc:
        if not allow_static_fallback:
            raise
        print(f"[WARN] Playwright crawl failed: {exc}")
        print("[WARN] Falling back to static HTTP crawler.")
        return crawl_static(max_pages=max_pages)

    if result is None and allow_static_fallback:
        print("[WARN] Playwright returned no content; falling back to static HTTP crawler.")
        return crawl_static(max_pages=max_pages)
    return result


def retrain_chroma():
    """Retrain Chroma vector store"""
    print(f"\n{'='*60}")
    print("Retraining Chroma vector store...")
    print(f"{'='*60}")
    from rag.vector_store import VectorStoreService
    from utils.indexing_lock import indexing_lock

    with indexing_lock:
        vs = VectorStoreService()
        result = vs.load_document()
    if not result["success"]:
        raise RuntimeError(result["error_summary"] or "Chroma training failed")
    print("[DONE] Chroma training complete!")


async def main(max_pages: int = 80, headless: bool = True, auto_train: bool = True):
    result = await crawl(max_pages=max_pages, headless=headless)
    if result and auto_train:
        retrain_chroma()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FTSM Official Website Scraper")
    parser.add_argument("--max-pages", "-p", type=int, default=80, help="Max pages to crawl (default 80)")
    parser.add_argument("--no-headless", action="store_true", help="Show browser window (for debugging)")
    parser.add_argument("--no-train", action="store_true", help="Skip Chroma training after crawling")
    args = parser.parse_args()

    asyncio.run(main(
        max_pages=args.max_pages,
        headless=not args.no_headless,
        auto_train=not args.no_train,
    ))
