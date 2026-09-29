import asyncio
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from .classifier import Classifier
from .db import dump, now
from .github_source import FetchError
from .parser import parse


class SyncService:
    def __init__(self, db, github, clock=None):
        self.db, self.github = db, github
        self.clock = clock or (lambda: datetime.now(UTC))
        self.classifier = Classifier()
        self.queue = asyncio.Queue()

    def recover(self):
        self.db.write(
            "UPDATE sync_runs SET status='interrupted', ended_at=?, error='服务关闭或重启，任务未完成' WHERE status IN ('queued','running')",
            (now(),),
        )

    def enqueue(self, source_id, trigger="manual"):
        existing = self.db.one(
            "SELECT id FROM sync_runs WHERE source_id=? AND status IN ('queued','running')",
            (source_id,),
        )
        if existing:
            return existing["id"]
        source = self.db.one("SELECT * FROM sources WHERE id=?", (source_id,))
        if not source:
            raise ValueError("来源不存在")
        if source["retry_not_before"] and source["retry_not_before"] > self.clock().isoformat():
            raise ValueError("此来源正在退避等待，请在来源页显示的重试时间之后刷新")
        run = self.db.write(
            "INSERT INTO sync_runs(source_id,trigger,status) VALUES(?,?,'queued')",
            (source_id, trigger),
        )
        self.queue.put_nowait(run)
        return run

    def schedule_due(self, trigger="scheduled"):
        current = self.clock().isoformat()
        for source in self.db.read(
            "SELECT * FROM sources WHERE enabled=1 AND refresh_interval_hours>0"
        ):
            if (not source["next_due_at"] or source["next_due_at"] <= current) and (
                not source["retry_not_before"] or source["retry_not_before"] <= current
            ):
                self.enqueue(source["id"], trigger)

    async def worker(self):
        while True:
            run = await self.queue.get()
            try:
                await self.execute(run)
            finally:
                self.queue.task_done()

    async def execute(self, run_id):
        run = self.db.one("SELECT * FROM sync_runs WHERE id=?", (run_id,))
        if not run or run["status"] != "queued":
            return
        source = self.db.one("SELECT * FROM sources WHERE id=?", (run["source_id"],))
        if run["trigger"] != "manual" and (
            not source["enabled"] or not source["refresh_interval_hours"]
        ):
            self.db.write(
                "UPDATE sync_runs SET status='interrupted',ended_at=?,error='来源已停用自动刷新' WHERE id=?",
                (now(), run_id),
            )
            return
        config = json.loads(source["config_json"])
        scope = dump({"repo": source["repo"], **config})
        self.db.write(
            "UPDATE sync_runs SET status='running',started_at=? WHERE id=?", (now(), run_id)
        )
        self.db.write("UPDATE sources SET last_checked_at=? WHERE id=?", (now(), source["id"]))
        counts = dict(discovered=0, added=0, updated=0, skipped=0, failed=0)
        errors, retry_at, status = [], None, "success"
        try:
            meta, cache = await self.github.metadata(
                source["repo"], json.loads(source["cache_json"])
            )
            self.db.write(
                """UPDATE sources SET repository_id=?,stars=?,forks=?,archived=?,activity_at=?,
                metrics_at=?,repository_license=?,cache_json=? WHERE id=?""",
                (
                    meta["id"],
                    meta["stargazers_count"],
                    meta["forks_count"],
                    meta["archived"],
                    meta["pushed_at"],
                    now(),
                    (meta.get("license") or {}).get("spdx_id"),
                    dump(cache),
                    source["id"],
                ),
            )
            commit, tree = await self.github.snapshot(
                source["repo"], config.get("branch") or meta["default_branch"]
            )
            self.db.write("UPDATE sources SET target_commit=? WHERE id=?", (commit, source["id"]))
            files, discovery_errors = await self.github.discover(source["repo"], tree, config)
            errors.extend(discovery_errors)
            counts["discovered"] = len(files)
            if not files:
                errors.append("指定范围未发现 SKILL.md，请核对扫描路径；未扩大扫描范围")
            self.progress(run_id, counts)
            for path, sha in files.items():
                old = self.db.one(
                    "SELECT * FROM skills WHERE source_id=? AND skill_path=?", (source["id"], path)
                )
                seen = now()
                if old:
                    self.db.write(
                        "UPDATE skills SET last_seen_at=?, missing=0 WHERE id=?", (seen, old["id"])
                    )
                if (
                    old
                    and old["file_sha"] == sha
                    and old["rule_version"] == self.classifier.version
                    and json.loads(old["auto_json"]).get("skill_url")
                    == f"https://github.com/{source['repo']}/blob/{quote(config.get('branch') or meta['default_branch'], safe='')}/{quote(path, safe='/')}"
                    and old["parse_status"] == "success"
                ):
                    counts["skipped"] += 1
                    self.progress(run_id, counts)
                    continue
                try:
                    # Classifier upgrades can reuse retained name/description; parser upgrades fetch again.
                    if (
                        old
                        and old["file_sha"] == sha
                        and old["parse_status"] == "success"
                        and (old["rule_version"] or "").split(":")[0]
                        == self.classifier.version.split(":")[0]
                    ):
                        data = json.loads(old["auto_json"])
                        data["summary_zh"] = ""
                    else:
                        document = await self.github.document(source["repo"], commit, path)
                        data = parse(document, path)
                    data.update(self.classifier.classify(source["repo"], path, data))
                    data["skill_url"] = (
                        f"https://github.com/{source['repo']}/blob/{quote(config.get('branch') or meta['default_branch'], safe='')}/{quote(path, safe='/')}"
                    )
                    parse_status = "incomplete" if data["warnings"] else "success"
                    if parse_status != "success":
                        errors.append(f"{path}：元数据不完整")
                        counts["failed"] += 1

                    # A rule version alone is not a change to the navigation information.
                    def visible(value):
                        return {k: v for k, v in value.items() if k != "classification_version"}

                    changed = not old or visible(json.loads(old["auto_json"])) != visible(data)
                    self.db.write(
                        """INSERT INTO skills(source_id,skill_path,auto_json,file_sha,rule_version,parse_status,
                        first_seen_at,last_seen_at,changed_at) VALUES(?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(source_id,skill_path) DO UPDATE SET auto_json=excluded.auto_json,
                        file_sha=excluded.file_sha,rule_version=excluded.rule_version,parse_status=excluded.parse_status,
                        last_seen_at=excluded.last_seen_at,changed_at=excluded.changed_at,missing=0""",
                        (
                            source["id"],
                            path,
                            dump(data),
                            sha,
                            self.classifier.version,
                            parse_status,
                            seen,
                            seen,
                            seen if changed else old["changed_at"],
                        ),
                    )
                    counts["added" if not old else "updated" if changed else "skipped"] += 1
                except (FetchError, ValueError) as e:
                    counts["failed"] += 1
                    errors.append(f"{path}：{e}")
                    if not old:
                        data = parse("", path)
                        data.update(self.classifier.classify(source["repo"], path, data))
                        data["skill_url"] = (
                            f"https://github.com/{source['repo']}/blob/{commit}/{quote(path, safe='/')}"
                        )
                        self.db.write(
                            """INSERT INTO skills(source_id,skill_path,auto_json,parse_status,first_seen_at,last_seen_at,changed_at)
                            VALUES(?,?,?,'failed',?,?,?)""",
                            (source["id"], path, dump(data), seen, seen, seen),
                        )
                    else:
                        self.db.write(
                            "UPDATE skills SET parse_status='failed' WHERE id=?", (old["id"],)
                        )
                    if isinstance(e, FetchError) and e.retry_at:
                        retry_at = e.retry_at
                        break
                self.progress(run_id, counts)
            # Full enumeration + unchanged scope only. Missing data is never deleted.
            current = self.db.one(
                "SELECT config_json,repo FROM sources WHERE id=?", (source["id"],)
            )
            current_scope = dump({"repo": current["repo"], **json.loads(current["config_json"])})
            if not discovery_errors and source["last_scope"] == scope == current_scope:
                for old in self.db.read(
                    "SELECT id,skill_path FROM skills WHERE source_id=?", (source["id"],)
                ):
                    if old["skill_path"] not in files:
                        self.db.write("UPDATE skills SET missing=1 WHERE id=?", (old["id"],))
            if not discovery_errors and scope == current_scope:
                self.db.write("UPDATE sources SET last_scope=? WHERE id=?", (scope, source["id"]))
            status = "partial" if errors else "success"
        except FetchError as e:
            errors.append(str(e))
            retry_at = e.retry_at
            status = "failed"
        except asyncio.CancelledError:
            self.db.write(
                "UPDATE sync_runs SET status='interrupted',ended_at=?,error='服务停止，任务未完成' WHERE id=?",
                (now(), run_id),
            )
            raise
        except Exception:
            # Do not expose upstream bodies, tokens or request objects in logs/UI.
            errors.append("内部同步错误；已保留旧资料，请检查来源配置或运行测试")
            status = "failed"
        ended = self.clock()
        current = self.db.one(
            "SELECT refresh_interval_hours FROM sources WHERE id=?", (source["id"],)
        )
        interval = current["refresh_interval_hours"]
        due = (ended + timedelta(hours=interval)).isoformat() if interval else None
        if status != "success":
            retry_at = retry_at or (ended + timedelta(minutes=15)).isoformat()
            due = retry_at if interval else None
        error = "；".join(errors)[:2000] or None
        self.db.write(
            """UPDATE sources SET last_error=?,next_due_at=?,retry_not_before=?,
            last_success_at=CASE WHEN ?='success' THEN ? ELSE last_success_at END WHERE id=?""",
            (error, due, retry_at, status, ended.isoformat(), source["id"]),
        )
        self.progress(run_id, counts)
        self.db.write(
            "UPDATE sync_runs SET status=?,ended_at=?,error=? WHERE id=?",
            (status, ended.isoformat(), error, run_id),
        )
        self.db.write(
            "DELETE FROM sync_runs WHERE status NOT IN ('queued','running') AND id NOT IN (SELECT id FROM sync_runs ORDER BY id DESC LIMIT 200)"
        )

    def progress(self, run_id, counts):
        self.db.write(
            "UPDATE sync_runs SET discovered=?,added=?,updated=?,skipped=?,failed=? WHERE id=?",
            (*counts.values(), run_id),
        )
