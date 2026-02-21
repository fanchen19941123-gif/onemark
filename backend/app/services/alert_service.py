from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import SyncRun, SyncRunPlatformResult, User


class AlertService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def maybe_send_platform_alert(
        self,
        *,
        user_id: str,
        sync_run_id: str,
        platform_result: SyncRunPlatformResult,
    ) -> bool:
        if not settings.feishu_webhook_url:
            return False

        if platform_result.status not in {"FAILED", "LOGIN_REQUIRED"}:
            return False

        dedupe_until = datetime.now(timezone.utc) - timedelta(hours=settings.alert_dedupe_hours)
        recent_row = await self.db.execute(
            select(SyncRunPlatformResult)
            .join(SyncRun, SyncRun.id == SyncRunPlatformResult.sync_run_id)
            .where(
                SyncRun.user_id == user_id,
                SyncRunPlatformResult.platform == platform_result.platform,
                SyncRunPlatformResult.error_code == platform_result.error_code,
                SyncRunPlatformResult.alert_sent.is_(True),
                SyncRunPlatformResult.alerted_at.is_not(None),
                SyncRunPlatformResult.alerted_at >= dedupe_until,
            )
            .order_by(desc(SyncRunPlatformResult.alerted_at))
            .limit(1)
        )
        if recent_row.scalar_one_or_none() is not None:
            return False

        user_row = await self.db.execute(select(User).where(User.id == user_id))
        user = user_row.scalar_one_or_none()
        user_email = user.email if user else user_id

        message = {
            "msg_type": "text",
            "content": {
                "text": (
                    f"OneMark 同步告警\n"
                    f"用户: {user_email}\n"
                    f"同步任务: {sync_run_id}\n"
                    f"平台: {platform_result.platform}\n"
                    f"状态: {platform_result.status}\n"
                    f"错误码: {platform_result.error_code or 'UNKNOWN'}\n"
                    f"原因: {platform_result.error_message or '无'}\n"
                    f"建议: 请检查登录状态后重试同步。"
                )
            },
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(settings.feishu_webhook_url, json=message)
            response.raise_for_status()
            platform_result.alert_sent = True
            platform_result.alerted_at = datetime.now(timezone.utc)
            return True
        except Exception:
            return False
