from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from app.api import auth, bookmarks, sync
from app.config import settings
from app.database import async_session, init_models
from app.models import User
from app.scheduler import start_scheduler, stop_scheduler
from app.security import get_password_hash


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    await _ensure_default_user()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(auth.router, prefix="/v1")
app.include_router(sync.router, prefix="/v1")
app.include_router(bookmarks.router, prefix="/v1")


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


async def _ensure_default_user() -> None:
    if not settings.auto_create_default_user:
        return

    async with async_session() as db:
        row = await db.execute(select(User).where(User.email == settings.default_user_email))
        existing = row.scalar_one_or_none()
        if existing is not None:
            return

        user = User(
            email=settings.default_user_email,
            password_hash=get_password_hash(settings.default_user_password),
        )
        db.add(user)
        await db.commit()
