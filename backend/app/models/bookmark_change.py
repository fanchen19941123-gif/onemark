from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BookmarkChange(Base):
    __tablename__ = "bookmark_changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sync_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sync_runs.id", ondelete="CASCADE"), index=True
    )
    bookmark_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bookmarks.id", ondelete="CASCADE"), index=True
    )
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    diff_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sync_run = relationship("SyncRun", back_populates="changes")
    bookmark = relationship("Bookmark", back_populates="changes")
