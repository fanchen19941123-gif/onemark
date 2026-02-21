from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import SyncRun, SyncRunPlatformResult
from app.models.enums import PlatformResultStatus, SyncRunStatus, TriggerSource
from app.scrapers import build_scraper
from app.scrapers.base import ScrapeResult, ScrapeStatus
from app.services.alert_service import AlertService
from app.services.classify_service import AIClassifierService
from app.services.diff_service import DiffService
from app.services.snapshot_service import SnapshotService


class SyncService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.diff_service = DiffService(db)
        self.classifier = AIClassifierService(db)
        self.alert_service = AlertService(db)
        self.snapshot_service = SnapshotService()

    async def run_sync(
        self,
        *,
        user_id: str,
        trigger_source: str = TriggerSource.MANUAL.value,
        platforms: list[str] | None = None,
    ) -> SyncRun:
        selected_platforms = self._normalize_platforms(platforms)
        now = datetime.now(timezone.utc)
        sync_run = SyncRun(
            user_id=user_id,
            trigger_source=trigger_source,
            status=SyncRunStatus.RUNNING.value,
            started_at=now,
            added_count=0,
            updated_count=0,
            removed_count=0,
        )
        self.db.add(sync_run)
        await self.db.flush()

        added_bookmarks = []
        normalized_items = []
        raw_by_platform: dict[str, list[dict]] = {}
        platform_rows: list[SyncRunPlatformResult] = []
        errors: list[str] = []

        try:
            for platform in selected_platforms:
                scraper = build_scraper(platform)
                scrape_result = await scraper.collect(user_id)

                platform_row = SyncRunPlatformResult(
                    sync_run_id=sync_run.id,
                    platform=platform,
                    status=_map_platform_status(scrape_result.status),
                    items_count=len(scrape_result.items),
                    error_code=scrape_result.error_code,
                    error_message=scrape_result.error_message,
                )
                self.db.add(platform_row)
                await self.db.flush()
                platform_rows.append(platform_row)

                raw_by_platform[platform] = scrape_result.raw_items

                if scrape_result.status == ScrapeStatus.SUCCESS:
                    diff_result = await self.diff_service.apply_full_snapshot(
                        sync_run_id=sync_run.id,
                        user_id=user_id,
                        platform=platform,
                        items=scrape_result.items,
                        now=now,
                    )
                    sync_run.added_count += diff_result.added_count
                    sync_run.updated_count += diff_result.updated_count
                    sync_run.removed_count += diff_result.removed_count
                    added_bookmarks.extend(diff_result.added_bookmarks)
                    normalized_items.extend([_serialize_item(item) for item in scrape_result.items])
                else:
                    errors.append(
                        f"{platform}:{scrape_result.error_code or 'UNKNOWN'}:{scrape_result.error_message or ''}"
                    )

            await self.classifier.classify_new_bookmarks(user_id, added_bookmarks)

            statuses = [row.status for row in platform_rows]
            sync_run.status = _determine_final_status(statuses)
            sync_run.finished_at = datetime.now(timezone.utc)
            sync_run.error_summary = "\n".join(errors) if errors else None

            for row in platform_rows:
                if row.status in {
                    PlatformResultStatus.FAILED.value,
                    PlatformResultStatus.LOGIN_REQUIRED.value,
                }:
                    await self.alert_service.maybe_send_platform_alert(
                        user_id=user_id,
                        sync_run_id=sync_run.id,
                        platform_result=row,
                    )

            try:
                self.snapshot_service.write_sync_snapshot(
                    sync_run_id=sync_run.id,
                    user_namespace=settings.single_user_snapshot_namespace,
                    payload={
                        "sync_run": {
                            "id": sync_run.id,
                            "user_id": sync_run.user_id,
                            "status": sync_run.status,
                            "trigger_source": sync_run.trigger_source,
                            "started_at": sync_run.started_at.isoformat(),
                            "finished_at": sync_run.finished_at.isoformat() if sync_run.finished_at else None,
                            "added_count": sync_run.added_count,
                            "updated_count": sync_run.updated_count,
                            "removed_count": sync_run.removed_count,
                        },
                        "platform_results": [
                            {
                                "platform": row.platform,
                                "status": row.status,
                                "items_count": row.items_count,
                                "error_code": row.error_code,
                                "error_message": row.error_message,
                                "alert_sent": row.alert_sent,
                            }
                            for row in platform_rows
                        ],
                        "normalized_items": normalized_items,
                        "raw_by_platform": raw_by_platform,
                    },
                )
            except Exception:
                # Snapshot is debug-only and must not block online persistence.
                pass

            await self.db.commit()
            await self.db.refresh(sync_run)
            return sync_run
        except Exception as exc:
            await self.db.rollback()

            sync_run.status = SyncRunStatus.FAILED.value
            sync_run.finished_at = datetime.now(timezone.utc)
            sync_run.error_summary = str(exc)
            self.db.add(sync_run)
            await self.db.commit()
            await self.db.refresh(sync_run)
            return sync_run

    def _normalize_platforms(self, platforms: list[str] | None) -> list[str]:
        allowed = set(settings.default_sync_platforms)
        requested = platforms or settings.default_sync_platforms
        deduped = []
        for platform in requested:
            if platform not in allowed:
                continue
            if platform in deduped:
                continue
            deduped.append(platform)
        return deduped



def _serialize_item(item) -> dict:
    return {
        "platform": item.platform,
        "platform_item_id": item.platform_item_id,
        "title": item.title,
        "url": item.url,
        "cover_url": item.cover_url,
        "content_updated_at": item.content_updated_at,
    }



def _map_platform_status(status: ScrapeStatus) -> str:
    if status == ScrapeStatus.SUCCESS:
        return PlatformResultStatus.SUCCESS.value
    if status == ScrapeStatus.LOGIN_REQUIRED:
        return PlatformResultStatus.LOGIN_REQUIRED.value
    return PlatformResultStatus.FAILED.value



def _determine_final_status(statuses: list[str]) -> str:
    if not statuses:
        return SyncRunStatus.FAILED.value

    success_count = sum(1 for s in statuses if s == PlatformResultStatus.SUCCESS.value)
    login_required_count = sum(1 for s in statuses if s == PlatformResultStatus.LOGIN_REQUIRED.value)

    if success_count == len(statuses):
        return SyncRunStatus.SUCCESS.value
    if success_count > 0:
        return SyncRunStatus.PARTIAL_SUCCESS.value
    if login_required_count > 0:
        return SyncRunStatus.LOGIN_REQUIRED.value
    return SyncRunStatus.FAILED.value
