from __future__ import annotations

import argparse
import asyncio

from httpx import ASGITransport, AsyncClient

from app.database import init_models
from app.main import app


async def run_smoke(email: str, password: str, platforms: list[str]) -> None:
    await init_models()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        auth_resp = await client.post("/v1/auth/register", json={"email": email, "password": password})
        if auth_resp.status_code == 400:
            auth_resp = await client.post("/v1/auth/login", json={"email": email, "password": password})
        auth_resp.raise_for_status()

        token = auth_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        sync_resp = await client.post("/v1/sync/runs", json={"platforms": platforms}, headers=headers)
        sync_resp.raise_for_status()
        sync_data = sync_resp.json()

        bookmarks_resp = await client.get("/v1/bookmarks", headers=headers)
        bookmarks_resp.raise_for_status()

        categories_resp = await client.get("/v1/categories", headers=headers)
        categories_resp.raise_for_status()

        print("=== Smoke Result ===")
        print("sync_id:", sync_data["id"])
        print("sync_status:", sync_data["status"])
        print("platform_results:", sync_data["platform_results"])
        print("added/updated/removed:", sync_data["added_count"], sync_data["updated_count"], sync_data["removed_count"])
        print("bookmark_count:", len(bookmarks_resp.json()))
        print("category_count:", len(categories_resp.json()))


def main() -> None:
    parser = argparse.ArgumentParser(description="OneMark single-user MVP smoke flow")
    parser.add_argument("--email", default="singleuser@onemark.com")
    parser.add_argument("--password", default="StrongPass123!")
    parser.add_argument("--platforms", default="douyin", help="comma-separated platforms")
    args = parser.parse_args()

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    asyncio.run(run_smoke(args.email, args.password, platforms))


if __name__ == "__main__":
    main()
