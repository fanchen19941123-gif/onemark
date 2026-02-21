from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CategoryResponse(BaseModel):
    id: str
    name: str
    source: str
    created_at: datetime


class BookmarkResponse(BaseModel):
    id: str
    platform: str
    platform_item_id: str
    title: str
    url: str
    cover_url: Optional[str] = None
    content_updated_at: Optional[datetime] = None
    first_collected_at: datetime
    last_collected_at: datetime
    removed_at: Optional[datetime] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    category_confidence: Optional[float] = None
    category_source: str


class UpdateBookmarkCategoryRequest(BaseModel):
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    clear: bool = False
