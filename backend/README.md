# OneMark Backend

Single-user MVP backend for auth, sync, diff, AI category assignment, and snapshot validation.

## Quick Start

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Smoke Test (No server process required)

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=$(pwd) python scripts/smoke_flow.py --platforms douyin
```

Read handover details in `TECH_HANDOVER.md`.

## Key Runtime Config

In `backend/.env`:

- `LLM_API_KEY=...`
- `LLM_BASE_URL=https://api.moonshot.cn/v1`
- `LLM_MODEL=kimi-coding/k2p5` (or your available Kimi model)
  - `SEMANTIC_SEARCH_CANDIDATES=160` controls semantic rerank candidate pool size
  - used for AI category assignment and natural-language bookmark search intent parsing

- `DOUYIN_HARD_RETRIES=3`
  - controls hard retry count for Douyin script actions
  - can be increased without code changes
- `DOUYIN_FAVORITES_URL=https://www.douyin.com/user/self?from_tab_name=main&showTab=favorite_collection` (optional)
  - explicit Douyin favorites URL used by script when current tab is not favorites

- `XHS_MAX_STEPS=2400`
- `XHS_SLEEP_MS=700`
- `XHS_HARD_RETRIES=2`
- `XHS_FAVORITES_URL=https://www.xiaohongshu.com/user/profile/<id>?tab=fav&subTab=note` (optional, recommended)
  - controls Xiaohongshu favorites scrolling depth/rhythm/retry

If Douyin cover images are blank in mobile, trigger one manual sync after backend restart so fixed cover URLs are written back.

## New APIs

- `GET /v1/bookmarks/search?q=...&limit=80`
  - natural-language search over collected bookmarks
- `POST /v1/bookmarks/reclassify?limit=500`
  - classify existing uncategorized bookmarks with AI
- `PATCH /v1/bookmarks/{bookmark_id}/category`
  - manual category override (`category_id` / `category_name` / `clear=true`)
