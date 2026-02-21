from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import User
from app.services.sync_service import SyncService


scheduler = AsyncIOScheduler(timezone=settings.sync_timezone)


async def sync_all_users_job() -> None:
    async with async_session() as db:
        rows = await db.execute(select(User.id))
        user_ids = [row[0] for row in rows.all()]

        for user_id in user_ids:
            service = SyncService(db)
            await service.run_sync(
                user_id=user_id,
                trigger_source="scheduled",
                platforms=settings.default_sync_platforms,
            )


def start_scheduler() -> None:
    if scheduler.running:
        return

    scheduler.add_job(
        sync_all_users_job,
        trigger="cron",
        hour=settings.sync_daily_hour,
        minute=settings.sync_daily_minute,
        id="daily_sync",
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
