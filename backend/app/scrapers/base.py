from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class ScrapeStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"


@dataclass
class ScrapeItem:
    platform: str
    platform_item_id: str
    title: str
    url: str
    cover_url: str | None = None
    content_updated_at: str | None = None
    raw_payload: dict = field(default_factory=dict)


@dataclass
class ScrapeResult:
    platform: str
    status: ScrapeStatus
    items: list[ScrapeItem] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    raw_items: list[dict] = field(default_factory=list)


class Scraper(Protocol):
    async def collect(self, user_id: str) -> ScrapeResult:
        ...
