from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from app.config import settings
from app.scrapers.base import ScrapeItem, ScrapeResult
from app.scrapers.script_runner import run_script_scraper


class DouyinScraper:
    platform = "douyin"

    async def collect(self, user_id: str) -> ScrapeResult:
        script_args = ["--hard-retries", str(settings.douyin_hard_retries)]
        favorites_url = (settings.douyin_favorites_url or "").strip()
        if favorites_url:
            script_args.extend(["--favorites-url", favorites_url])
        return await run_script_scraper(
            platform=self.platform,
            script_path=settings.douyin_script_path,
            normalize_item=_normalize_douyin_item,
            script_args=script_args,
        )


def _normalize_douyin_item(raw: dict) -> ScrapeItem | None:
    item_id = str(raw.get("video_id") or "").strip()
    url = str(raw.get("url") or "").strip()
    title = str(raw.get("title") or "").strip()

    if not item_id and url:
        item_id = url.rstrip("/").split("/")[-1]

    if not item_id or not url:
        return None

    cover_url = _normalize_url(str(raw.get("cover") or "")) or None

    return ScrapeItem(
        platform="douyin",
        platform_item_id=item_id,
        title=title or "(无标题)",
        url=url,
        cover_url=cover_url,
        raw_payload=raw,
    )


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        raw = url.strip()
        if raw.startswith("//"):
            raw = f"https:{raw}"
        parsed = urlsplit(raw)
        scheme = parsed.scheme or "https"
        # Keep original host + query; Douyin covers rely on specific subdomain/signature.
        return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, ""))
    except Exception:
        return url.strip()
