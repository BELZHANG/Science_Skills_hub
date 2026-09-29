import json
from datetime import UTC, datetime, timedelta

from conftest import do_sync

from skill_hub.db import dump


async def test_incremental_and_preserves_human(sync):
    service, fake = sync
    first = await do_sync(service)
    assert first["status"] == "success"
    assert first["added"] == 1
    skill = service.db.skills()[0]
    old_date = skill["changed_at"]
    service.db.write(
        "UPDATE skills SET favorite=1,featured=1,notes='personal',user_overrides_json=?",
        (dump({"primary_category": "Write", "summary_zh": "我的简介", "tags": []}),),
    )
    fake.calls.clear()
    fake.stars = 20
    second = await do_sync(service)
    assert second["skipped"] == 1
    assert not any(r.url.host == "raw.githubusercontent.com" for r in fake.calls)
    skill = service.db.skills()[0]
    assert skill["favorite"] and skill["featured"]
    assert skill["notes"] == "personal"
    assert skill["primary_category"] == "Write"
    assert skill["tags"] == []
    assert skill["changed_at"] == old_date
    assert skill["stars"] == 20
    fake.blob = "e" * 40
    fake.document = fake.document.replace("Statistical analysis", "Citation management")
    third = await do_sync(service)
    assert third["updated"] == 1
    skill = service.db.skills()[0]
    assert skill["summary_zh"] == "我的简介"
    assert skill["primary_category"] == "Write"
    assert skill["changed_at"] != old_date


async def test_failed_same_sha_retries(sync):
    service, fake = sync
    await do_sync(service)
    fake.blob = "e" * 40
    fake.raw_status = 500
    run = await do_sync(service)
    assert run["status"] == "partial"
    assert service.db.skills()[0]["name"] == "fixture-statistics"
    fake.raw_status = 200
    run = await do_sync(service)
    assert run["status"] == "success"
    assert service.db.skills()[0]["parse_status"] == "success"


async def test_missing_only_after_complete_same_scope(sync):
    service, fake = sync
    await do_sync(service)
    fake.files = False
    fake.truncated = True
    assert (await do_sync(service))["status"] == "partial"
    assert not service.db.skills()[0]["missing"]
    fake.truncated = False
    await do_sync(service)
    assert service.db.skills()[0]["missing"]
    assert service.db.skills()[0]["name"]


async def test_changed_scope_no_missing(sync):
    service, fake = sync
    await do_sync(service)
    fake.files = False
    source = service.db.one("SELECT config_json FROM sources WHERE id=1")
    config = json.loads(source["config_json"])
    config["branch"] = "another-branch"
    service.db.write("UPDATE sources SET config_json=? WHERE id=1", (dump(config),))
    await do_sync(service)
    assert not service.db.skills()[0]["missing"]


async def test_schedule_dedupe_and_recovery(sync):
    service, _ = sync
    current = datetime(2026, 1, 1, tzinfo=UTC)
    service.clock = lambda: current
    service.schedule_due("startup")
    first = service.enqueue(1)
    service.schedule_due()
    assert len(service.db.read("SELECT * FROM sync_runs")) == 1
    assert first == service.enqueue(1)
    service.recover()
    assert service.db.one("SELECT status FROM sync_runs")["status"] == "interrupted"
    service.schedule_due("startup")
    assert len(service.db.read("SELECT * FROM sync_runs WHERE status='queued'")) == 1
    service.recover()
    service.db.write(
        "UPDATE sources SET retry_not_before=?", ((current + timedelta(hours=1)).isoformat(),)
    )
    service.schedule_due()
    assert not service.db.read("SELECT * FROM sync_runs WHERE status='queued'")
    service.db.write("UPDATE sources SET retry_not_before=NULL,enabled=0")
    service.schedule_due()
    assert not service.db.read("SELECT * FROM sync_runs WHERE status='queued'")
    service.db.write("UPDATE sources SET enabled=1,refresh_interval_hours=0")
    service.schedule_due()
    assert not service.db.read("SELECT * FROM sync_runs WHERE status='queued'")
    assert service.enqueue(1)


async def test_same_name_separate_sources(sync):
    service, _ = sync
    await do_sync(service)
    service.db.write(
        "INSERT INTO sources(id,name,repo,config_json) VALUES(2,'Other','other/repo','{}')"
    )
    service.db.write(
        "INSERT INTO skills(source_id,skill_path,auto_json,first_seen_at,last_seen_at,changed_at) SELECT 2,skill_path,auto_json,first_seen_at,last_seen_at,changed_at FROM skills WHERE source_id=1"
    )
    assert len(service.db.skills()) == 2


async def test_rule_upgrade_reuses_input(sync):
    service, fake = sync
    await do_sync(service)
    fake.calls.clear()
    service.classifier.version = "1:updated-rules"
    run = await do_sync(service)
    assert run["status"] == "success"
    assert not any(r.url.host == "raw.githubusercontent.com" for r in fake.calls)
    assert service.db.one("SELECT rule_version FROM skills")["rule_version"] == "1:updated-rules"


async def test_parser_upgrade_fetches_body(sync):
    service, fake = sync
    await do_sync(service)
    fake.calls.clear()
    service.classifier.version = "2:updated-parser"
    await do_sync(service)
    assert any(r.url.host == "raw.githubusercontent.com" for r in fake.calls)


async def test_version_only_not_content_change(sync):
    service, _ = sync
    await do_sync(service)
    before = service.db.skills()[0]["changed_at"]
    service.classifier.version = "1:new-fingerprint"
    await do_sync(service)
    assert service.db.skills()[0]["changed_at"] == before


async def test_branch_change_updates_link_without_body(sync):
    service, fake = sync
    await do_sync(service)
    fake.calls.clear()
    service.db.write(
        "UPDATE sources SET config_json=?",
        (dump({"scan_roots": ["skills"], "explicit_paths": [], "branch": "release/v1"}),),
    )
    await do_sync(service)
    assert "/blob/release%2Fv1/" in service.db.skills()[0]["skill_url"]
    assert not any(r.url.host == "raw.githubusercontent.com" for r in fake.calls)
