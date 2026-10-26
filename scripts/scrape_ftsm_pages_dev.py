"""
Browser-rendered crawler for the Chinese student FTSM portal.

The site is a client-side SPA. Useful data is spread across routes, buttons,
modals, SVG map overlays, image assets, and minified JavaScript bundles. This
script intentionally captures more than visible body text so the local RAG
knowledge base does not miss interactive modules.

Run without indexing:
    python scripts/scrape_ftsm_pages_dev.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

BASE_URL = "https://ftsm.pages.dev"
ROUTES = ["/", "/research", "/systems", "/guide", "/certification", "/about"]
OUTPUT_FILE = PROJECT_ROOT / "data" / "ukm_ftsm" / "chinese_student_ftsm_pages_dev_browser_crawl.txt"

SKIP_BUTTON_LABELS = {
    "",
    "×",
    "收起",
    "展开",
    "搜索",
    "全局搜索",
    "常用检索语",
    "更新日志",
    "我知道了",
    "返回顶部",
}

TEXT_ASSET_EXTENSIONS = (".js", ".css")
MEDIA_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".pdf")


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


def section(title: str, text: str) -> tuple[str, str]:
    return title, clean_text(text)


def snapshot_page(page) -> str:
    return clean_text(page.locator("body").inner_text(timeout=10000))


def current_assets(page) -> dict[str, Any]:
    return page.evaluate(
        """
        () => {
          const imageUrls = new Set();
          const assetUrls = new Set();
          const backgroundUrls = new Set();

          for (const img of document.querySelectorAll('img')) {
            if (img.currentSrc || img.src) imageUrls.add(img.currentSrc || img.src);
          }

          for (const node of document.querySelectorAll('script[src], link[href], source[src], a[href]')) {
            const url = node.src || node.href;
            if (url) assetUrls.add(url);
          }

          for (const el of document.querySelectorAll('*')) {
            const bg = getComputedStyle(el).backgroundImage || '';
            for (const match of bg.matchAll(/url\\(["']?([^"')]+)["']?\\)/g)) {
              backgroundUrls.add(new URL(match[1], location.href).href);
            }
          }

          const images = [...document.querySelectorAll('img')].map((img) => ({
            alt: img.alt || '',
            src: img.currentSrc || img.src || '',
            width: img.naturalWidth || 0,
            height: img.naturalHeight || 0,
          }));

          return {
            url: location.href,
            title: document.title,
            images,
            imageUrls: [...imageUrls],
            backgroundUrls: [...backgroundUrls],
            assetUrls: [...assetUrls],
          };
        }
        """
    )


def dismiss_welcome(page) -> None:
    try:
        confirm = page.get_by_role("button", name="我知道了", exact=True)
        if confirm.count():
            confirm.click(timeout=2000, force=True)
            page.wait_for_timeout(300)
    except Exception:
        pass


def button_targets(page) -> list[dict[str, Any]]:
    targets = page.evaluate(
        """
        () => [...document.querySelectorAll('button')]
          .map((button, index) => {
            const label = button.innerText.trim().replace(/\\s+/g, ' ');
            const container = button.closest('article, .card, .service-card, .system-card, .guide-card, .research-card');
            const context = container ? container.innerText.trim().replace(/\\s+/g, ' ').slice(0, 120) : '';
            return { index, label, context };
          })
          .filter((item) => item.label)
        """
    )
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for target in targets:
        label = target["label"]
        if label in SKIP_BUTTON_LABELS or label in seen:
            continue
        seen.add(f"{target['index']}:{label}")
        unique.append(target)
    return unique


def click_button_and_snapshot(page, url: str, target: dict[str, Any]) -> str:
    page.goto(url, wait_until="load", timeout=60000)
    page.wait_for_timeout(600)
    dismiss_welcome(page)
    page.locator("button").nth(target["index"]).click(timeout=5000, force=True)
    page.wait_for_timeout(900)
    return snapshot_page(page)


def collect_map_blocks(page, url: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    page.goto(url, wait_until="load", timeout=60000)
    page.wait_for_timeout(600)

    try:
        dismiss_welcome(page)
        page.get_by_role("button", name="查看学院地图", exact=True).click(timeout=5000, force=True)
        page.wait_for_timeout(900)
    except Exception as exc:
        return [section("FTSM map interaction failed", str(exc))]

    sections.append(section("FTSM map modal visible text", snapshot_page(page)))
    map_assets = current_assets(page)
    media_lines = []
    for image in map_assets.get("images", []):
        media_lines.append(
            f"Image: alt={image.get('alt')!r}; size={image.get('width')}x{image.get('height')}; src={image.get('src')}"
        )
    for key in ("imageUrls", "backgroundUrls", "assetUrls"):
        for asset_url in map_assets.get(key, []):
            normalized = asset_url.lower().split("?", 1)[0]
            if normalized.endswith(MEDIA_EXTENSIONS):
                media_lines.append(f"{key}: {asset_url}")
    sections.append(section("FTSM map media assets", "\n".join(sorted(set(media_lines)))))

    block_info = page.evaluate(
        """
        () => [...document.querySelectorAll('.overlay .b-poly')].map((poly, index) => {
          const rect = poly.getBoundingClientRect();
          const textNode = poly.nextElementSibling;
          return {
            index,
            label: textNode ? textNode.textContent.trim() : `Block polygon ${index + 1}`,
            x: Math.round(rect.left + rect.width / 2),
            y: Math.round(rect.top + rect.height / 2),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
          };
        })
        """
    )

    for item in block_info:
        try:
            page.mouse.click(item["x"], item["y"])
            page.wait_for_timeout(500)
            text = snapshot_page(page)
        except Exception as exc:
            text = f"Failed to click {item['label']}: {exc}"
        title = f"FTSM map block {item['label']} at ({item['x']}, {item['y']})"
        sections.append(section(title, text))

    return sections


def collect_route(page, route: str) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    url = f"{BASE_URL}{route}"
    page.goto(url, wait_until="load", timeout=60000)
    page.wait_for_timeout(800)
    dismiss_welcome(page)

    sections: list[tuple[str, str]] = [section(f"Route {route}", snapshot_page(page))]
    assets = current_assets(page)

    for target in button_targets(page):
        label = target["label"]
        try:
            text = click_button_and_snapshot(page, url, target)
        except Exception as exc:
            text = f"Failed to open module {label}: {exc}"
        context = f" / {target['context']}" if target.get("context") else ""
        title = f"Route {route} / Button {target['index']} {label}{context}"
        sections.append(section(title, text))

    if route == "/":
        sections.extend(collect_map_blocks(page, url))

    return sections, assets


def fetch_url_text(url: str, timeout: int = 20) -> str:
    request = Request(url, headers={"User-Agent": "FTSM-RAG crawler"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def readable_asset_strings(text: str) -> list[str]:
    candidates: list[str] = []

    for match in re.finditer(r'"((?:\\.|[^"\\]){3,})"|\'((?:\\.|[^\'\\]){3,})\'', text):
        raw = match.group(1) if match.group(1) is not None else match.group(2)
        try:
            decoded = json.loads(f'"{raw}"')
        except Exception:
            decoded = (
                raw.replace("\\n", "\n")
                .replace("\\r", "\n")
                .replace("\\t", " ")
                .replace('\\"', '"')
                .replace("\\'", "'")
            )
        decoded = clean_text(decoded)
        if not decoded:
            continue
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", decoded))
        has_ftsm = bool(re.search(r"\b(FTSM|UKM|EMGS|SMP|FOLIO|JoinUKM|BK\d+|Block|TC\d+)\b", decoded))
        if has_cjk or has_ftsm or any(ext in decoded.lower() for ext in MEDIA_EXTENSIONS):
            candidates.append(decoded)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item in seen or len(item) > 2000:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def collect_bundled_assets(asset_urls: set[str]) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    for url in sorted(asset_urls):
        normalized = url.split("?", 1)[0].lower()
        if not normalized.endswith(TEXT_ASSET_EXTENSIONS):
            continue
        if not url.startswith(BASE_URL):
            continue
        try:
            text = fetch_url_text(url)
        except Exception as exc:
            sections.append(section(f"Asset fetch failed {url}", str(exc)))
            continue

        strings = readable_asset_strings(text)
        if strings:
            sections.append(section(f"Readable strings from asset {url}", "\n".join(strings)))

    return sections


def collect_asset_inventory(route_assets: list[dict[str, Any]]) -> tuple[list[tuple[str, str]], set[str]]:
    all_asset_urls: set[str] = set()
    lines: list[str] = []
    media_lines: list[str] = []

    for asset in route_assets:
        lines.append(f"Page: {asset.get('url')}")
        lines.append(f"Title: {asset.get('title')}")
        for image in asset.get("images", []):
            media_lines.append(
                f"Image: alt={image.get('alt')!r}; size={image.get('width')}x{image.get('height')}; src={image.get('src')}"
            )
        for key in ("imageUrls", "backgroundUrls", "assetUrls"):
            for url in asset.get(key, []):
                all_asset_urls.add(urljoin(BASE_URL, url))
                if url.lower().split("?", 1)[0].endswith(MEDIA_EXTENSIONS):
                    media_lines.append(f"{key}: {url}")

    sections = [
        section("Portal asset inventory", "\n".join(lines)),
        section("Portal media and visual assets", "\n".join(sorted(set(media_lines)))),
    ]
    return sections, all_asset_urls


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
        "It captures route text, button-triggered modules, map interactions, media "
        "asset references, and readable strings from bundled JavaScript. It is useful "
        "for practical onboarding and navigation, but it is not an official UKM or "
        "FTSM policy document. Verify formal requirements against official UKM, FTSM, "
        "UKMShape, EMGS, JoinUKM, or faculty sources.",
        "",
        "=" * 80,
        "",
    ]

    seen: set[str] = set()
    for title, text in sections:
        fingerprint = f"{title}\n{text}"
        if fingerprint in seen or not text:
            continue
        seen.add(fingerprint)
        lines.extend([f"[{title}]", "", text, "", "-" * 60, ""])

    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    sections: list[tuple[str, str]] = []
    route_assets: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        for route in ROUTES:
            route_sections, assets = collect_route(page, route)
            sections.extend(route_sections)
            route_assets.append(assets)
        browser.close()

    inventory_sections, asset_urls = collect_asset_inventory(route_assets)
    sections.extend(inventory_sections)
    sections.extend(collect_bundled_assets(asset_urls))

    write_output(sections)
    print(f"Wrote {OUTPUT_FILE}")
    print(f"Sections: {len(sections)}")
    print(f"Size: {OUTPUT_FILE.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
