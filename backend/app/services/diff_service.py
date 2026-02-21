from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bookmark, BookmarkChange
from app.models.enums import ChangeType
from app.scrapers.base import ScrapeItem


@dataclass
class DiffApplyResult:
    added_count: int = 0
    updated_count: int = 0
    removed_count: int = 0
    added_bookmarks: list[Bookmark] = field(default_factory=list)


class DiffService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def apply_full_snapshot(
        self,
        *,
        sync_run_id: str,
        user_id: str,
        platform: str,
        items: list[ScrapeItem],
        now: datetime | None = None,
    ) -> DiffApplyResult:
        now = now or datetime.now(timezone.utc)
        result = DiffApplyResult()

        rows = await self.db.execute(
            select(Bookmark).where(
                Bookmark.user_id == user_id,
                Bookmark.platform == platform,
            )
        )
        existing = {item.platform_item_id: item for item in rows.scalars().all()}

        seen_ids: set[str] = set()
        for item in items:
            seen_ids.add(item.platform_item_id)
            fp = build_fingerprint(item)
            current = existing.get(item.platform_item_id)

            if current is None:
                bookmark = Bookmark(
                    user_id=user_id,
                    platform=platform,
                    platform_item_id=item.platform_item_id,
                    title=item.title,
                    url=item.url,
                    cover_url=item.cover_url,
                    content_updated_at=_parse_datetime(item.content_updated_at),
                    first_collected_at=now,
                    last_collected_at=now,
                    removed_at=None,
                    content_fingerprint=fp,
                    category_source="ai",
                )
                self.db.add(bookmark)
                await self.db.flush()

                await self._append_change(
                    sync_run_id=sync_run_id,
                    bookmark_id=bookmark.id,
                    change_type=ChangeType.ADDED,
                    diff={"title": bookmark.title, "url": bookmark.url},
                )
                result.added_count += 1
                result.added_bookmarks.append(bookmark)
                continue

            diff_payload: dict[str, dict[str, str | None]] = {}
            if current.content_fingerprint != fp:
                if current.title != item.title:
                    diff_payload["title"] = {"before": current.title, "after": item.title}
                    current.title = item.title
                if current.url != item.url:
                    diff_payload["url"] = {"before": current.url, "after": item.url}
                    current.url = item.url
                if current.cover_url != item.cover_url:
                    diff_payload["cover_url"] = {"before": current.cover_url, "after": item.cover_url}
                    current.cover_url = item.cover_url
                parsed_updated_at = _parse_datetime(item.content_updated_at)
                if current.content_updated_at != parsed_updated_at:
                    diff_payload["content_updated_at"] = {
                        "before": current.content_updated_at.isoformat() if current.content_updated_at else None,
                        "after": parsed_updated_at.isoformat() if parsed_updated_at else None,
                    }
                    current.content_updated_at = parsed_updated_at
                current.content_fingerprint = fp

            # Restore if previously removed.
            if current.removed_at is not None:
                diff_payload["removed_at"] = {
                    "before": current.removed_at.isoformat(),
                    "after": None,
                }
                current.removed_at = None

            current.last_collected_at = now

            if diff_payload:
                await self._append_change(
                    sync_run_id=sync_run_id,
                    bookmark_id=current.id,
                    change_type=ChangeType.UPDATED,
                    diff=diff_payload,
                )
                result.updated_count += 1

        for platform_item_id, current in existing.items():
            if platform_item_id in seen_ids:
                continue
            if current.removed_at is not None:
                continue

            current.removed_at = now
            await self._append_change(
                sync_run_id=sync_run_id,
                bookmark_id=current.id,
                change_type=ChangeType.REMOVED,
                diff={"removed_at": now.isoformat()},
            )
            result.removed_count += 1

        await self.db.flush()
        return result

    async def _append_change(
        self,
        *,
        sync_run_id: str,
        bookmark_id: str,
        change_type: ChangeType,
        diff: dict,
    ) -> None:
        change = BookmarkChange(
            sync_run_id=sync_run_id,
            bookmark_id=bookmark_id,
            change_type=change_type.value,
            diff_json=json.dumps(diff, ensure_ascii=False),
        )
        self.db.add(change)


def build_fingerprint(item: ScrapeItem) -> str:
    payload = "|".join(
        [
            item.title.strip(),
            item.url.strip(),
            (item.cover_url or "").strip(),
            (item.content_updated_at or "").strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
