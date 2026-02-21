from app.scrapers.bilibili import BilibiliScraper
from app.scrapers.douyin import DouyinScraper
from app.scrapers.xiaohongshu import XiaohongshuScraper


def build_scraper(platform: str):
    mapping = {
        "xiaohongshu": XiaohongshuScraper,
        "douyin": DouyinScraper,
        "bilibili": BilibiliScraper,
    }
    if platform not in mapping:
        raise ValueError(f"Unsupported platform: {platform}")
    return mapping[platform]()
