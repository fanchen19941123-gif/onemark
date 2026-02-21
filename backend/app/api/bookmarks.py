from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Bookmark, Category, User
from app.schemas.bookmark import BookmarkResponse, CategoryResponse, UpdateBookmarkCategoryRequest
from app.services.classify_service import AIClassifierService
from app.services.search_service import SearchService


router = APIRouter(prefix="", tags=["bookmarks"])


@router.get("/bookmarks", response_model=list[BookmarkResponse])
async def list_bookmarks(
    platform: Optional[str] = None,
    include_removed: bool = False,
    sort_order: str = "desc",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[BookmarkResponse]:
    query = (
        select(Bookmark, Category)
        .outerjoin(Category, Bookmark.category_id == Category.id)
        .where(Bookmark.user_id == user.id)
    )
    if platform:
        query = query.where(Bookmark.platform == platform)
    if not include_removed:
        query = query.where(Bookmark.removed_at.is_(None))

    order_column = Bookmark.first_collected_at
    query = query.order_by(asc(order_column) if sort_order == "asc" else desc(order_column))

    rows = await db.execute(query)
    result = []
    for bookmark, category in rows.all():
        result.append(_build_bookmark_response(bookmark, category))
    return result


@router.get("/bookmarks/search", response_model=list[BookmarkResponse])
async def search_bookmarks(
    q: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[BookmarkResponse]:
    service = SearchService(db)
    rows = await service.search_bookmarks(
        user_id=user.id,
        query_text=q,
        limit=limit,
    )

    result = []
    for bookmark, category in rows:
        result.append(_build_bookmark_response(bookmark, category))
    return result


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CategoryResponse]:
    rows = await db.execute(
        select(Category)
        .where(Category.user_id == user.id)
        .order_by(asc(Category.name))
    )
    return [
        CategoryResponse(
            id=category.id,
            name=category.name,
            source=category.source,
            created_at=category.created_at,
        )
        for category in rows.scalars().all()
    ]


@router.post("/bookmarks/reclassify")
async def reclassify_uncategorized(
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    service = AIClassifierService(db)
    classified_count = await service.classify_uncategorized_bookmarks(user.id, limit=limit)
    await db.commit()
    return {"classified_count": classified_count}


@router.patch("/bookmarks/{bookmark_id}/category", response_model=BookmarkResponse)
async def update_bookmark_category(
    bookmark_id: str,
    payload: UpdateBookmarkCategoryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> BookmarkResponse:
    row = await db.execute(
        select(Bookmark).where(
            Bookmark.id == bookmark_id,
            Bookmark.user_id == user.id,
            Bookmark.removed_at.is_(None),
        )
    )
    bookmark = row.scalar_one_or_none()
    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    if payload.clear:
        bookmark.category_id = None
        bookmark.category_confidence = None
        bookmark.category_source = "manual"
        await db.commit()
        await db.refresh(bookmark)
        return _build_bookmark_response(bookmark, None)

    category: Category | None = None
    category_id = (payload.category_id or "").strip()
    category_name = (payload.category_name or "").strip()

    if category_id:
        category_row = await db.execute(
            select(Category).where(
                Category.id == category_id,
                Category.user_id == user.id,
            )
        )
        category = category_row.scalar_one_or_none()
        if category is None:
            raise HTTPException(status_code=404, detail="Category not found")
    elif category_name:
        category_row = await db.execute(
            select(Category).where(
                Category.user_id == user.id,
                Category.name == category_name,
            )
        )
        category = category_row.scalar_one_or_none()
        if category is None:
            category = Category(user_id=user.id, name=category_name, source="manual")
            db.add(category)
            await db.flush()
    else:
        raise HTTPException(status_code=400, detail="Provide category_id or category_name, or set clear=true")

    bookmark.category_id = category.id if category else None
    bookmark.category_confidence = 1.0 if category else None
    bookmark.category_source = "manual"

    await db.commit()
    await db.refresh(bookmark)
    return _build_bookmark_response(bookmark, category)


def _build_bookmark_response(bookmark: Bookmark, category: Category | None) -> BookmarkResponse:
    return BookmarkResponse(
        id=bookmark.id,
        platform=bookmark.platform,
        platform_item_id=bookmark.platform_item_id,
        title=bookmark.title,
        url=bookmark.url,
        cover_url=bookmark.cover_url,
        content_updated_at=bookmark.content_updated_at,
        first_collected_at=bookmark.first_collected_at,
        last_collected_at=bookmark.last_collected_at,
        removed_at=bookmark.removed_at,
        category_id=bookmark.category_id,
        category_name=category.name if category else None,
        category_confidence=bookmark.category_confidence,
        category_source=bookmark.category_source,
    )
