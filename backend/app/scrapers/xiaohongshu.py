from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from app.config import settings
from app.scrapers.base import ScrapeItem, ScrapeResult, ScrapeStatus
from app.scrapers.script_runner import run_script_scraper


class XiaohongshuScraper:
    platform = "xiaohongshu"

    async def collect(self, user_id: str) -> ScrapeResult:
        last_result: ScrapeResult | None = None
        retries = max(1, settings.xhs_hard_retries)
        script_args = [
            "--max-steps",
            str(settings.xhs_max_steps),
            "--sleep-ms",
            str(settings.xhs_sleep_ms),
        ]
        favorites_url = (settings.xhs_favorites_url or "").strip()
        if favorites_url:
            script_args.extend(["--favorites-url", favorites_url])

        for _ in range(retries):
            result = await run_script_scraper(
                platform=self.platform,
                script_path=settings.xhs_script_path,
                normalize_item=_normalize_xhs_item,
                script_args=script_args,
            )
            last_result = result
            if result.status == ScrapeStatus.SUCCESS:
                return result
            if result.status == ScrapeStatus.LOGIN_REQUIRED:
                return result
        return last_result or ScrapeResult(platform=self.platform, status=ScrapeStatus.FAILED)


def _normalize_xhs_item(raw: dict) -> ScrapeItem | None:
    item_id = str(raw.get("note_id") or "").strip()
    url = str(raw.get("url") or "").strip()
    title = str(raw.get("title") or "").strip()
    if not item_id and url:
        item_id = url.rstrip("/").split("/")[-1]

    if not item_id or not url:
        return None

    cover_url = _normalize_url(str(raw.get("cover") or "")) or None

    return ScrapeItem(
        platform="xiaohongshu",
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
        return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, ""))
    except Exception:
        return url.strip()
