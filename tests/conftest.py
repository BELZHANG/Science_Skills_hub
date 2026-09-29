from pathlib import Path

import httpx
import pytest

from skill_hub.db import Database, dump
from skill_hub.github_source import GitHub
from skill_hub.sync_service import SyncService

COMMIT = "a" * 40
TREE = "b" * 40
SUBTREE = "c" * 40
BLOB = "d" * 40
DOCUMENT = (Path(__file__).parent / "fixtures" / "SKILL.md").read_text()


class FakeGitHub:
    def __init__(self):
        self.calls = []
        self.document = DOCUMENT
        self.blob = BLOB
        self.stars = 10
        self.raw_status = 200
        self.files = True
        self.truncated = False

    def __call__(self, request):
        self.calls.append(request)
        p = request.url.path
        if request.url.host == "raw.githubusercontent.com":
            return httpx.Response(self.raw_status, text=self.document)
        if p.endswith("/repos/test/research"):
            return httpx.Response(
                200,
                json={
                    "id": 123,
                    "private": False,
                    "default_branch": "trunk",
                    "stargazers_count": self.stars,
                    "forks_count": 2,
                    "archived": False,
                    "pushed_at": "2026-01-01T00:00:00Z",
                    "license": {"spdx_id": "MIT"},
                },
                headers={"etag": '"one"'},
            )
        if "/commits/" in p:
            return httpx.Response(200, json={"sha": COMMIT, "commit": {"tree": {"sha": TREE}}})
        if p.endswith("/" + TREE):
            return httpx.Response(
                200,
                json={
                    "tree": [{"path": "skills", "type": "tree", "sha": SUBTREE, "mode": "040000"}],
                    "truncated": False,
                },
            )
        if p.endswith("/" + SUBTREE):
            entries = (
                [{"path": "analysis/SKILL.md", "type": "blob", "sha": self.blob, "mode": "100644"}]
                if self.files
                else []
            )
            return httpx.Response(200, json={"tree": entries, "truncated": self.truncated})
        return httpx.Response(404)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "hub.sqlite3")
    database.initialize()
    database.write("DELETE FROM sources")
    database.write(
        "INSERT INTO sources(id,name,repo,config_json) VALUES(1,'Test fixture only','test/research',?)",
        (dump({"scan_roots": ["skills"], "explicit_paths": [], "branch": ""}),),
    )
    return database


@pytest.fixture
async def sync(db):
    fake = FakeGitHub()
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as client:
        service = SyncService(db, GitHub(client, sleep=no_wait))
        yield service, fake


async def no_wait(seconds):
    pass


async def do_sync(service):
    service.db.write("UPDATE sources SET retry_not_before=NULL")
    run_id = service.enqueue(1)
    await service.execute(run_id)
    return service.db.one("SELECT * FROM sync_runs WHERE id=?", (run_id,))
