from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings


class SnapshotService:
    def __init__(self) -> None:
        self.root = Path(settings.snapshot_root).expanduser()

    def write_sync_snapshot(
        self,
        *,
        sync_run_id: str,
        user_namespace: str,
        payload: dict[str, Any],
    ) -> Path:
        target = self.root / user_namespace / sync_run_id
        target.mkdir(parents=True, exist_ok=True)

        path = target / "summary.json"
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

        return path
