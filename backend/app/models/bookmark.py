from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Bookmark(Base):
    __tablename__ = "bookmarks"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "platform",
            "platform_item_id",
            name="uq_bookmarks_user_platform_item",
        ),
        Index("ix_bookmarks_user_removed", "user_id", "removed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )

    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    platform_item_id: Mapped[str] = mapped_column(String(128), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    cover_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    first_collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    category_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    category_source: Mapped[str] = mapped_column(String(20), nullable=False, default="ai")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="bookmarks")
    category = relationship("Category", back_populates="bookmarks")
    changes = relationship("BookmarkChange", back_populates="bookmark", cascade="all, delete-orphan")
