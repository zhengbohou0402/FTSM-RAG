"""
Browser-rendered crawler for the Chinese student FTSM portal.

This site is a client-side SPA. Many details are inside button-triggered
modules/modals, so a plain HTTP crawler misses useful content.

Run without indexing:
    python scripts/scrape_ftsm_pages_dev.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

BASE_URL = "https://ftsm.pages.dev"
ROUTES = ["/", "/research", "/systems", "/guide", "/certification", "/about"]
OUTPUT_FILE = PROJECT_ROOT / "data" / "ukm_ftsm" / "chinese_student_ftsm_pages_dev_browser_crawl.txt"

SKIP_BUTTON_LABELS = {
    "",
    "收起",
    "展开",
    "搜索",
    "常用检索语",
    "更新日志",
    "我知道了",
}


def clean_text(text: str) -> str:
    lines: list[str] = []
    previous_blank = False
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = " ".join(raw_line.strip().split())
        if not line:
            if not previous_blank:
                lines.append("")
            previous_blank = True
            continue
        lines.append(line)
        previous_blank = False
    return "\n".join(lines).strip()


def snapshot_page(page) -> str:
    return clean_text(page.locator("body").inner_text(timeout=10000))


def button_labels(page) -> list[tuple[int, str]]:
    labels: list[tuple[int, str]] = []
    buttons = page.locator("button").all()
    for index, button in enumerate(buttons):
        try:
            label = " ".join(button.inner_text(timeout=1000).split())
        except PlaywrightTimeoutError:
            continue
        if label and label not in SKIP_BUTTON_LABELS:
            labels.append((index, label))
    return labels


def collect_route(page, route: str) -> list[tuple[str, str]]:
    url = f"{BASE_URL}{route}"
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(500)

    sections: list[tuple[str, str]] = [(f"Route {route}", snapshot_page(page))]
    labels = button_labels(page)

    for index, label in labels:
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(300)
        try:
            page.locator("button").nth(index).click(timeout=5000)
            page.wait_for_timeout(700)
            text = snapshot_page(page)
        except Exception as exc:
            text = f"Failed to open module {label}: {exc}"
        sections.append((f"Route {route} / Module {label}", text))

    return sections


def write_output(sections: list[tuple[str, str]]) -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "FTSM Chinese Student Portal Browser Crawl",
        "Source type: Student community guide",
        f"Primary source: {BASE_URL}/",
        f"Crawled at: {datetime.now().isoformat()}",
        "",
        "Important note:",
        "This document is browser-rendered content from a student-maintained portal. "
        "It is useful for practical onboarding and navigation, but it is not an "
        "official UKM or FTSM policy document. Verify formal requirements against "
        "official UKM, FTSM, UKMShape, EMGS, JoinUKM, or faculty sources.",
        "",
        "=" * 80,
        "",
    ]

    seen: set[str] = set()
    for title, text in sections:
        fingerprint = f"{title}\n{text}"
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        lines.extend([f"[{title}]", "", text, "", "-" * 60, ""])

    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    sections: list[tuple[str, str]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        for route in ROUTES:
            sections.extend(collect_route(page, route))
        browser.close()

    write_output(sections)
    print(f"Wrote {OUTPUT_FILE}")
    print(f"Sections: {len(sections)}")
    print(f"Size: {OUTPUT_FILE.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
