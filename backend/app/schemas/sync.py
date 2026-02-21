from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TriggerSyncRequest(BaseModel):
    platforms: Optional[list[str]] = None


class SyncPlatformResultResponse(BaseModel):
    platform: str
    status: str
    items_count: int
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    alert_sent: bool = False


class SyncRunResponse(BaseModel):
    id: str
    user_id: str
    trigger_source: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    added_count: int = 0
    updated_count: int = 0
    removed_count: int = 0
    error_summary: Optional[str] = None
    platform_results: list[SyncPlatformResultResponse] = Field(default_factory=list)
