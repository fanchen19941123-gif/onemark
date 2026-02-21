from app.scrapers.base import ScrapeResult, ScrapeStatus


class BilibiliScraper:
    platform = "bilibili"

    async def collect(self, user_id: str) -> ScrapeResult:
        return ScrapeResult(
            platform=self.platform,
            status=ScrapeStatus.LOGIN_REQUIRED,
            error_code="SCRAPER_NOT_READY",
            error_message="Bilibili scraper not implemented yet for this MVP.",
        )
