from collections.abc import AsyncGenerator

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def init_models() -> None:
    # Import models before create_all so metadata is populated.
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_lightweight_migrations)


def _run_lightweight_migrations(conn) -> None:
    # Lightweight migration to keep local/prototype DB schemas usable without Alembic.
    inspector = inspect(conn)
    table_names = set(inspector.get_table_names())

    if "users" in table_names:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "phone" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(32)"))
        if "display_name" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN display_name VARCHAR(80)"))
        if "avatar_url" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url VARCHAR(512)"))
        if "feishu_open_id" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN feishu_open_id VARCHAR(128)"))
        if "feishu_union_id" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN feishu_union_id VARCHAR(128)"))
        if "feishu_tenant_key" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN feishu_tenant_key VARCHAR(128)"))
        if "phone_verified_at" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN phone_verified_at TIMESTAMP"))
        if "last_login_at" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone ON users (phone)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_feishu_open_id ON users (feishu_open_id)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_feishu_union_id ON users (feishu_union_id)"))

    if "sms_login_codes" in table_names:
        sms_columns = {column["name"] for column in inspector.get_columns("sms_login_codes")}
        if "failed_attempts" not in sms_columns:
            conn.execute(text("ALTER TABLE sms_login_codes ADD COLUMN failed_attempts INTEGER DEFAULT 0 NOT NULL"))
        if "purpose" not in sms_columns:
            conn.execute(text("ALTER TABLE sms_login_codes ADD COLUMN purpose VARCHAR(32) DEFAULT 'register' NOT NULL"))
        if "last_attempt_at" not in sms_columns:
            conn.execute(text("ALTER TABLE sms_login_codes ADD COLUMN last_attempt_at TIMESTAMP"))
