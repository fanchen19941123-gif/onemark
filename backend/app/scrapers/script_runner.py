from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from tempfile import mkdtemp

from app.scrapers.base import ScrapeItem, ScrapeResult, ScrapeStatus


_LOGIN_HINTS = (
    "cannot find chrome tab",
    "open",
    "favorites",
    "please switch",
    "login",
    "未登录",
)

_EXPECTED_DOMAIN = {
    "xiaohongshu": "xiaohongshu.com",
    "douyin": "douyin.com",
    "bilibili": "bilibili.com",
}


def _is_login_required(output: str) -> bool:
    lower = output.lower()
    return any(token in lower for token in _LOGIN_HINTS)


def _parse_reported_url(stdout: str) -> str | None:
    matches = re.findall(r"^URL:\s*(.+)$", stdout, flags=re.MULTILINE)
    if matches:
        return matches[-1].strip()
    return None


def _parse_json_output_path(stdout: str) -> str | None:
    match = re.search(r"^json=(.+)$", stdout, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def _load_json_items(path_str: str) -> list[dict]:
    path = Path(path_str)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if isinstance(data, list):
        return data
    return []


async def run_script_scraper(
    platform: str,
    script_path: str,
    normalize_item,
    script_args: list[str] | None = None,
) -> ScrapeResult:
    script = Path(script_path).expanduser()
    if not script.exists():
        return ScrapeResult(
            platform=platform,
            status=ScrapeStatus.LOGIN_REQUIRED,
            error_code="SCRIPT_MISSING",
            error_message=f"Script not found: {script}",
        )

    out_dir = Path(mkdtemp(prefix=f"onemark_{platform}_"))
    cmd = [str(script), "--out-dir", str(out_dir)]
    if script_args:
        cmd.extend(script_args)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await process.communicate()

    stdout = stdout_bytes.decode("utf-8", errors="ignore")
    stderr = stderr_bytes.decode("utf-8", errors="ignore")
    merged_output = f"{stdout}\n{stderr}".strip()

    if process.returncode != 0:
        status = ScrapeStatus.LOGIN_REQUIRED if _is_login_required(merged_output) else ScrapeStatus.FAILED
        return ScrapeResult(
            platform=platform,
            status=status,
            error_code="SCRAPE_COMMAND_FAILED",
            error_message=merged_output[-1200:] if merged_output else "Unknown scrape error",
        )

    json_path = _parse_json_output_path(stdout)
    if not json_path:
        return ScrapeResult(
            platform=platform,
            status=ScrapeStatus.FAILED,
            error_code="OUTPUT_PARSE_FAILED",
            error_message="Script succeeded but no json output path found",
        )

    raw_items = _load_json_items(json_path)

    reported_url = _parse_reported_url(stdout)
    expected_domain = _EXPECTED_DOMAIN.get(platform)
    if expected_domain and reported_url and expected_domain not in reported_url and not raw_items:
        return ScrapeResult(
            platform=platform,
            status=ScrapeStatus.LOGIN_REQUIRED,
            error_code="WRONG_BROWSER_TAB",
            error_message=f"Detected tab URL '{reported_url}' is not {expected_domain}",
        )

    items: list[ScrapeItem] = []
    for raw in raw_items:
        normalized = normalize_item(raw)
        if normalized is not None:
            items.append(normalized)

    return ScrapeResult(
        platform=platform,
        status=ScrapeStatus.SUCCESS,
        items=items,
        raw_items=raw_items,
    )
