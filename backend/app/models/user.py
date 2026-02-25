import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), unique=True, nullable=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    feishu_open_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)
    feishu_union_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)
    feishu_tenant_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    phone_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    bookmarks = relationship("Bookmark", back_populates="user", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    sync_runs = relationship("SyncRun", back_populates="user", cascade="all, delete-orphan")
