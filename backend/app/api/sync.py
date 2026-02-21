from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import SyncRun, SyncRunPlatformResult, User
from app.schemas.sync import SyncPlatformResultResponse, SyncRunResponse, TriggerSyncRequest
from app.services.sync_service import SyncService


router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/runs", response_model=SyncRunResponse)
async def trigger_sync(
    payload: TriggerSyncRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SyncRunResponse:
    service = SyncService(db)
    sync_run = await service.run_sync(
        user_id=user.id,
        trigger_source="manual",
        platforms=payload.platforms,
    )
    return await _build_sync_response(db, sync_run)


@router.get("/runs", response_model=list[SyncRunResponse])
async def list_sync_runs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SyncRunResponse]:
    rows = await db.execute(
        select(SyncRun)
        .where(SyncRun.user_id == user.id)
        .order_by(desc(SyncRun.started_at))
        .limit(max(1, min(limit, 100)))
    )

    response = []
    for sync_run in rows.scalars().all():
        response.append(await _build_sync_response(db, sync_run))
    return response


@router.get("/runs/{sync_run_id}", response_model=SyncRunResponse)
async def get_sync_run(
    sync_run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SyncRunResponse:
    row = await db.execute(
        select(SyncRun).where(
            SyncRun.id == sync_run_id,
            SyncRun.user_id == user.id,
        )
    )
    sync_run = row.scalar_one_or_none()
    if sync_run is None:
        raise HTTPException(status_code=404, detail="Sync run not found")

    return await _build_sync_response(db, sync_run)


async def _build_sync_response(db: AsyncSession, sync_run: SyncRun) -> SyncRunResponse:
    rows = await db.execute(
        select(SyncRunPlatformResult).where(SyncRunPlatformResult.sync_run_id == sync_run.id)
    )
    platform_results = [
        SyncPlatformResultResponse(
            platform=row.platform,
            status=row.status,
            items_count=row.items_count,
            error_code=row.error_code,
            error_message=row.error_message,
            alert_sent=row.alert_sent,
        )
        for row in rows.scalars().all()
    ]

    return SyncRunResponse(
        id=sync_run.id,
        user_id=sync_run.user_id,
        trigger_source=sync_run.trigger_source,
        status=sync_run.status,
        started_at=sync_run.started_at,
        finished_at=sync_run.finished_at,
        added_count=sync_run.added_count,
        updated_count=sync_run.updated_count,
        removed_count=sync_run.removed_count,
        error_summary=sync_run.error_summary,
        platform_results=platform_results,
    )
