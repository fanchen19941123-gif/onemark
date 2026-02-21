# OneMark Backend Handover (Single-User MVP)

## 1. Current Goal

This backend implements a single-user MVP for bookmark sync:

1. Auth (register/login/refresh)
2. Manual or scheduled sync runs
3. Full snapshot sync + diff (added/updated/removed)
4. AI-only category assignment for newly added bookmarks
5. Feishu alerting on login-required or failed platform sync
6. Cloud DB as source of truth + local snapshot files for verification

## 2. Architecture

- `FastAPI` app: `app/main.py`
- `SQLAlchemy async`: `app/database.py`, models in `app/models/`
- `Sync orchestration`: `app/services/sync_service.py`
- `Platform scraping adapter`: `app/scrapers/`
- `Diff logic`: `app/services/diff_service.py`
- `AI category routing`: `app/services/classify_service.py`
- `Feishu alerts`: `app/services/alert_service.py`
- `Snapshot writer`: `app/services/snapshot_service.py`
- `Daily scheduler`: `app/scheduler.py`

## 3. Data Model Summary

Tables are created with `Base.metadata.create_all()` at startup.

- `users`
- `categories`
- `bookmarks`
- `sync_runs`
- `sync_run_platform_results`
- `bookmark_changes`

Key fields:

- `bookmarks.first_collected_at`: timeline baseline for early/late favorites
- `bookmarks.removed_at`: soft-delete marker
- `bookmarks.content_fingerprint`: snapshot diff comparison key
- `bookmarks.category_source`: currently `ai`

## 4. Sync Flow

1. Create `sync_run` with `RUNNING`
2. For each platform scraper:
   - collect items
   - persist platform result status
   - if success -> apply full diff to DB
3. Classify only newly added bookmarks
4. Send Feishu alerts for failed/login-required platform results (deduped)
5. Persist local snapshot under `output/snapshots/default/{sync_run_id}/summary.json`
6. Mark `sync_run` final status

## 5. API Endpoints

- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `POST /v1/auth/refresh`
- `POST /v1/sync/runs`
- `GET /v1/sync/runs`
- `GET /v1/sync/runs/{sync_run_id}`
- `GET /v1/bookmarks`
- `GET /v1/categories`
- `GET /healthz`

## 6. Environment Variables

Use `backend/.env.example` as baseline.

Important variables:

- `DATABASE_URL`
- `SECRET_KEY`
- `DEEPSEEK_API_KEY`
- `FEISHU_WEBHOOK_URL`
- `XHS_SCRIPT_PATH`
- `DOUYIN_SCRIPT_PATH`
- `BILIBILI_SCRIPT_PATH`

## 7. Local Run Steps

1. Install dependencies:

```bash
cd backend
pip install -r requirements.txt
```

2. Configure `.env` (copy from `.env.example`)
3. Start API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Smoke flow (without starting uvicorn separately):

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=$(pwd) python scripts/smoke_flow.py --platforms douyin
```

## 8. Known Gaps / Next Tasks

1. Bilibili scraper currently returns `LOGIN_REQUIRED` placeholder.
2. No Alembic migrations yet; startup uses `create_all`.
3. Scheduler currently runs for all users in DB; still fine for single-user MVP.
4. AI category embedding-based similarity is not implemented yet (name/title routing for now).
5. No automated tests added yet.
6. XHS/Douyin scripts depend on Chrome tab context; wrong active tab can produce `LOGIN_REQUIRED`.

## 9. Recommended Next Iteration

1. Add Bilibili scraper script integration
2. Add Alembic migration baseline
3. Add pytest for auth, sync state machine, and diff correctness
4. Add Docker and deployment config
5. Add structured logs and tracing


## 10. Latest Validation Result (2026-02-13)

Validated end-to-end with local smoke flow:

1. Register/Login works
2. Manual sync trigger works
3. Sync status, runs list, bookmark list, category list endpoints work
4. Local snapshot written under `output/snapshots/default/{sync_run_id}/summary.json`

Observed statuses:

- If browser tab is wrong or not logged in: platform returns `LOGIN_REQUIRED`
- If Douyin favorites tab is open and logged in: sync can return `SUCCESS` with items persisted

## 11. Practical Notes for Handover

1. Python 3.9 is currently used in this environment.
2. Type hints were adjusted for Python 3.9 compatibility (`Optional[...]` where needed in models/schemas).
3. Requirements pin includes `greenlet` and `bcrypt==4.0.1` for compatibility with SQLAlchemy async + passlib.
4. Config reads env from `backend/.env` regardless of current working directory.

## 12. Recent Changes (2026-02-14)

### 12.1 Douyin scraper reliability

File: `scripts/export_douyin_favorites.sh`

1. Added random rhythm for crawl actions:
   - randomized sleep jitter
   - randomized scroll step ratio
2. Added auto-open favorites behavior:
   - if current tab is not Douyin favorites, script navigates to favorites URL automatically
3. Added hard retry mechanism for key actions (open tab, navigate, reload, step scrape, finalize payload):
   - CLI flag: `--hard-retries N`
   - env default: `HARD_RETRIES` (fallback `3`)

### 12.2 Hard retries became backend-configurable

Files:

- `backend/app/config.py`
- `backend/app/scrapers/douyin.py`
- `backend/app/scrapers/script_runner.py`
- `backend/.env.example`

Details:

1. New backend env config: `DOUYIN_HARD_RETRIES` (default `3`)
2. Backend passes retry count to script via:
   - `script_args=["--hard-retries", str(settings.douyin_hard_retries)]`
3. Script runner supports generic extra args for script-based scrapers.

### 12.3 Douyin cover image fix (important)

File: `backend/app/scrapers/douyin.py`

Problem:

- Cover images not rendered in mobile app.
- Root cause was incorrect cover URL normalization:
  - host was flattened to `douyinpic.com`
  - query string signature was dropped

Fix:

1. Keep original host (e.g. `p3-pc-sign.douyinpic.com`)
2. Keep query params/signature unchanged
3. Only normalize protocol when needed

Impact:

- Existing broken cover URLs in DB are corrected after next Douyin sync run.
- User should trigger one manual sync after deployment to backfill cover URLs.

### 12.4 Mobile app UI upgrade

File: `mobile/App.tsx`

1. New tabs:
   - `首页`
   - `搜索`
   - `同步`
   - `我`
2. Home/Search:
   - dual-column masonry feed
   - cover, platform badge, category, collected time
   - local search filter
3. Added detail modal:
   - larger cover
   - metadata and origin link open
4. Style aligned to product direction:
   - dark theme base `#141414`
   - card background `#1C1C1E`
   - accent `#FF2442`

## 13. Operator Runbook (Current)

1. Start backend:

```bash
cd /Users/bytedance/Desktop/收藏夹管理助手/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

2. Configure mobile API endpoint (real device):

```bash
cd /Users/bytedance/Desktop/收藏夹管理助手/mobile
export EXPO_PUBLIC_API_BASE_URL=http://<LAN_IP>:8000
npm run start -- --clear
```

3. If cover images are blank:
   - confirm backend already includes cover URL fix
   - trigger one manual Douyin sync in app
   - tap `刷新` in app home

4. Adjust retry count without code changes:
   - set `DOUYIN_HARD_RETRIES` in `backend/.env`
   - restart backend
