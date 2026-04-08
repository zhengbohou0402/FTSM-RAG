# FTSM Official Website Scraper
# Crawl all pages from https://ftsm.ukm.my/v6/, save to txt, train to Chroma vector store.
#
# Usage:
#   python scripts/scrape_ftsm_website.py
#   python scripts/scrape_ftsm_website.py --max-pages 80
#   python scripts/scrape_ftsm_website.py --no-train

import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Installing playwright...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    from playwright.async_api import async_playwright

OUTPUT_DIR = PROJECT_ROOT / "data" / "ukm_ftsm"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://www.ftsm.ukm.my/v6/"
ALLOWED_DOMAIN = "ftsm.ukm.my"

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


def is_ftsm_url(url: str) -> bool:
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


async def crawl(max_pages: int = 80, headless: bool = True) -> Path | None:
    visited: set[str] = set()
    queue: list[str] = []

    # Add seed URLs to queue
    for u in SEED_URLS:
        u = u.rstrip("/")
        if u not in visited:
            queue.append(u)

    all_pages: list[dict] = []

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
                continue
            if should_skip_url(url):
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

    with open(out_file, "w", encoding="utf-8") as f:
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

    print(f"\n[DONE] Total {len(all_pages)} pages crawled")
    print(f"[SAVE] {out_file}")
    return out_file


def retrain_chroma():
    """Retrain Chroma vector store"""
    print(f"\n{'='*60}")
    print("Retraining Chroma vector store...")
    print(f"{'='*60}")
    from rag.vector_store import VectorStoreService
    vs = VectorStoreService()
    vs.load_document()
    print("[DONE] Chroma training complete!")


async def main(max_pages: int = 80, headless: bool = True, auto_train: bool = True):
    out_file = await crawl(max_pages=max_pages, headless=headless)
    if out_file and auto_train:
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
