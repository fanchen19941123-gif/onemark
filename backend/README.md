# OneMark Backend

Single-user MVP backend for auth, sync, diff, AI category assignment, and snapshot validation.

## Quick Start

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# local DB (recommended for current stage)
# DATABASE_URL=sqlite+aiosqlite:///./onemark_dev.db
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
- `POST /v1/auth/sms/send-code`
  - send phone verification code (`purpose=register/login`, local debug mode can return `debug_code`)
- `POST /v1/auth/sms/register`
  - register by `phone + sms code`, and set initial `password/username/avatar_url`
- `POST /v1/auth/phone/login`
  - login by `phone + password`
- `POST /v1/auth/sms/login`
  - optional passwordless login by `phone + code` (requires `purpose=login`)
- `GET /v1/auth/me`
  - get current user profile (`phone/username/avatar_url/...`)
- `PATCH /v1/auth/me`
  - update profile (`username` / `avatar_url`)
- `POST /v1/auth/feishu/start`
  - start Feishu OAuth login, returns authorize URL + session id
- `GET /v1/auth/feishu/callback`
  - Feishu OAuth callback endpoint
- `GET /v1/auth/feishu/session/{session_id}`
  - poll Feishu login session result and consume token once success

## Local User-Agent Smoke Test

Run one command from project root:

```bash
./scripts/test_local_user_agent.sh
```

What it does:

1. Uses your local machine as the collector agent.
2. Tries Douyin + Xiaohongshu favorites collection via logged-in Chrome.
3. Writes sync results into backend DB through backend sync flow.
4. Prints a final summary (`sync_status`, per-platform result, added/updated/removed).

Optional overrides:

```bash
PLATFORMS=douyin ./scripts/test_local_user_agent.sh
DOUYIN_FAVORITES_URL='https://www.douyin.com/user/self?from_tab_name=main&showTab=favorite_collection' ./scripts/test_local_user_agent.sh
XHS_FAVORITES_URL='https://www.xiaohongshu.com/user/profile/<your_id>?tab=fav&subTab=note' ./scripts/test_local_user_agent.sh
```

## Run Without Same Wi-Fi

开发调试默认建议局域网（更快），外网联调再开 tunnel。

统一启动入口：

```bash
cd /Users/bytedance/Desktop/收藏夹管理助手
./scripts/start_dev.sh          # 局域网开发
./scripts/start_dev.sh --tunnel # 外网模式
```

手动方式（仅外网）：

```bash
brew install cloudflared
cd /Users/bytedance/Desktop/收藏夹管理助手
./scripts/start_backend_tunnel.sh
```

After it prints `backend public: https://...trycloudflare.com`, use that URL for mobile:

```bash
export EXPO_PUBLIC_API_BASE_URL=https://<your-tunnel>.trycloudflare.com
cd /Users/bytedance/Desktop/收藏夹管理助手/mobile
npm run start -- --tunnel --clear
```

## Feishu Login Setup

在 `backend/.env` 设置：

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_REDIRECT_URI=http://<你的后端地址>/v1/auth/feishu/callback
FEISHU_OAUTH_SCOPE=contact:user.base:readonly
```

注意：

1. `FEISHU_REDIRECT_URI` 必须和飞书开放平台应用配置一致。
2. 本地局域网调试建议固定本机 LAN IP（例如 `http://192.168.x.x:8000/v1/auth/feishu/callback`）。
3. `trycloudflare.com` 临时域名每次会变化，不适合作为长期回调地址。
