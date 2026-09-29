import re

import httpx
from conftest import do_sync
from fastapi.testclient import TestClient

from skill_hub.config import Settings
from skill_hub.main import create_app


def client_for(tmp_path):
    return TestClient(
        create_app(
            Settings(data_dir=tmp_path, auto_start=False),
            transport=httpx.MockTransport(lambda r: httpx.Response(500)),
        ),
        base_url="http://localhost",
    )


def headers(client):
    page = client.get("/")
    csrf = re.search(r'name="csrf-token" content="([^"]+)"', page.text).group(1)
    return {"origin": "http://localhost", "x-csrf-token": csrf}


def test_empty_start_seed_once_security(tmp_path):
    with client_for(tmp_path) as client:
        h = headers(client)
        assert len(client.get("/api/sources").json()) == 4
        assert client.get("/sources").status_code == 200
        assert client.get("/health").json()["status"] == "ok"
        assert client.patch("/api/sources/1", json={"enabled": False}, headers=h).status_code == 200
        assert client.post("/api/refresh", json={}).status_code == 403
        assert (
            client.post(
                "/api/refresh", json={}, headers=h | {"origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert client.get("/", headers={"host": "evil.example"}).status_code == 400
    with client_for(tmp_path) as client:
        assert not client.get("/api/sources").json()[0]["enabled"]
        assert len(client.get("/api/sources").json()) == 4


def test_source_validation(tmp_path):
    with client_for(tmp_path) as client:
        h = headers(client)
        body = {
            "name": "fixture",
            "repo": "https://github.com/Test/Research",
            "scan_roots": ["skills"],
        }
        response = client.post("/api/sources", json=body, headers=h)
        assert response.status_code == 201
        assert (
            client.post(
                "/api/sources", json=body | {"repo": "test/research"}, headers=h
            ).status_code
            == 409
        )
        for repo in [
            "https://localhost/a/b",
            "https://github.com/a/b/extra",
            "https://u:p@github.com/a/b",
            "a/..",
        ]:
            assert (
                client.post("/api/sources", json=body | {"repo": repo}, headers=h).status_code
                == 422
            )
        assert (
            client.post(
                "/api/sources", json=body | {"scan_roots": ["../secret"]}, headers=h
            ).status_code
            == 422
        )


async def test_end_to_end_offline(tmp_path, sync):
    service, _ = sync
    await do_sync(service)
    # The UI opens the same fixture-populated SQLite file, with network blocked.
    with client_for(service.db.path.parent) as client:
        h = headers(client)
        item = client.get("/api/skills").json()["items"][0]
        sid = item["id"]
        assert "fixture-statistics" in client.get("/").text
        patch = {
            "favorite": True,
            "overrides": {
                "primary_category": "Write",
                "summary_zh": "中文测试简介",
                "tags": ["中文标签"],
            },
            "notes": "保留备注",
        }
        assert client.patch(f"/api/skills/{sid}", json=patch, headers=h).status_code == 200
        await do_sync(service)
        result = client.get(
            "/api/skills", params={"q": "中文测试", "favorite": "true", "category": "Write"}
        ).json()
        assert result["total"] == 1
        assert result["items"][0]["notes"] == "保留备注"
        assert (
            client.patch(
                f"/api/skills/{sid}", json={"clear_overrides": ["primary_category"]}, headers=h
            ).json()["primary_category"]
            == "Experiment"
        )
        assert (
            client.patch(
                f"/api/skills/{sid}", json={"overrides": {"summary_zh": ""}}, headers=h
            ).json()["summary_zh"]
            == ""
        )
        assert (
            client.patch(f"/api/skills/{sid}", json={"auto_json": "bad"}, headers=h).status_code
            == 422
        )
        assert (
            client.patch(
                f"/api/skills/{sid}", json={"overrides": {"file_sha": "bad"}}, headers=h
            ).status_code
            == 422
        )
        assert (
            client.patch(
                f"/api/skills/{sid}",
                json={"overrides": {"summary_zh": "<script>alert(1)</script>"}},
                headers=h,
            ).status_code
            == 200
        )
        page = client.get("/").text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
        assert "<script>alert(1)</script>" not in page
        assert "frame-ancestors" in client.get("/").headers["content-security-policy"]
        assert client.patch("/api/sources/1", json={"enabled": False}, headers=h).status_code == 200
        assert client.get("/api/skills").json()["total"] == 0
        assert client.get("/api/skills?show_disabled=true").json()["total"] == 1


def test_source_partial_edit_and_disabled_refresh(tmp_path):
    with client_for(tmp_path) as client:
        h = headers(client)
        assert (
            client.patch(
                "/api/sources/1",
                json={"name": "Updated name", "refresh_interval_hours": 0},
                headers=h,
            ).status_code
            == 200
        )
        source = client.get("/api/sources").json()[0]
        assert source["name"] == "Updated name"
        assert source["refresh_interval_hours"] == 0
        assert client.patch("/api/sources/1", json={"enabled": False}, headers=h).status_code == 200
        result = client.post("/api/refresh", json={}, headers=h).json()
        ids = result["task_ids"]
        runs = client.get("/api/sync-runs").json()
        assert all(r["source_id"] != 1 for r in runs if r["id"] in ids)


async def test_pagination_unknown_stars_and_empty_favorites(sync):
    from skill_hub.db import dump
    from skill_hub.routes import listing

    service, _ = sync
    await do_sync(service)
    db = service.db
    original = db.one("SELECT * FROM skills")
    for i in range(30):
        db.write(
            "INSERT INTO skills(source_id,skill_path,auto_json,first_seen_at,last_seen_at,changed_at) VALUES(1,?,?,?,?,?)",
            (
                f"skills/item-{i}/SKILL.md",
                original["auto_json"],
                original["first_seen_at"],
                original["last_seen_at"],
                original["changed_at"],
            ),
        )
    db.write(
        "INSERT INTO sources(id,name,repo,config_json,stars) VALUES(2,'Unknown','unknown/repo','{}',NULL)"
    )
    db.write(
        "INSERT INTO skills(source_id,skill_path,auto_json,first_seen_at,last_seen_at,changed_at) VALUES(2,?,?,?,?,?)",
        (
            "a/SKILL.md",
            dump({"name": "A unknown"}),
            original["first_seen_at"],
            original["last_seen_at"],
            original["changed_at"],
        ),
    )
    page = listing(db, sort="stars", page=2)
    assert page["total"] == 32
    assert page["pages"] == 2
    assert len(page["items"]) == 8
    assert page["items"][-1]["stars"] is None
    assert listing(db, favorite=True)["total"] == 0
