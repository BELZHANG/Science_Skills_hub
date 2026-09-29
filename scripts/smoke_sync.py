"""Opt-in real network acceptance. Never called by pytest. Uses normal local data."""

import asyncio
import fcntl
import json
from datetime import UTC, datetime

import httpx
from dotenv import load_dotenv

from skill_hub.config import Settings
from skill_hub.db import Database
from skill_hub.github_source import GitHub
from skill_hub.sync_service import SyncService


async def main():
    load_dotenv()
    settings = Settings()
    db = Database(settings.data_dir / "hub.sqlite3")
    db.initialize()
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=8)) as client:
        service = SyncService(db, GitHub(client, settings.token))
        results = []
        for repo in ["docling-project/docling", "google-deepmind/science-skills"]:
            source = db.one("SELECT * FROM sources WHERE repo=?", (repo,))
            try:
                run_id = service.enqueue(source["id"], "manual")
                await service.execute(run_id)
                run = db.one("SELECT * FROM sync_runs WHERE id=?", (run_id,))
                results.append({"repo": repo, "at": datetime.now(UTC).isoformat(), **run})
            except ValueError as e:
                results.append({"repo": repo, "status": "deferred", "error": str(e)})
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    load_dotenv()
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with (settings.data_dir / "instance.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("请先停止正在使用该数据目录的应用") from None
        asyncio.run(main())
