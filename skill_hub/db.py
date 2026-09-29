import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime

import yaml

from .config import CONFIG_DIR


def now():
    return datetime.now(UTC).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class Database:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=5)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            yield c
        finally:
            c.close()

    def read(self, sql, args=()):
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def one(self, sql, args=()):
        rows = self.read(sql, args)
        return rows[0] if rows else None

    def write(self, sql, args=()):
        with self.connect() as c:
            cur = c.execute(sql, args)
            c.commit()
            return cur.lastrowid

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.execute("PRAGMA journal_mode=WAL")
            version = c.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("数据库版本较新，请使用匹配的应用版本")
            c.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
              id INTEGER PRIMARY KEY, name TEXT NOT NULL, repo TEXT UNIQUE COLLATE NOCASE NOT NULL,
              config_json TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
              refresh_interval_hours INTEGER NOT NULL DEFAULT 24,
              repository_id INTEGER, stars INTEGER, forks INTEGER, archived INTEGER,
              activity_at TEXT, metrics_at TEXT, repository_license TEXT,
              last_checked_at TEXT, last_success_at TEXT, next_due_at TEXT,
              retry_not_before TEXT, last_error TEXT, target_commit TEXT,
              cache_json TEXT NOT NULL DEFAULT '{}', last_scope TEXT,
              notes TEXT NOT NULL DEFAULT '', evidence_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS skills (
              id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
              skill_path TEXT NOT NULL, auto_json TEXT NOT NULL DEFAULT '{}',
              file_sha TEXT, rule_version TEXT, parse_status TEXT NOT NULL DEFAULT 'pending',
              first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, changed_at TEXT NOT NULL,
              missing INTEGER NOT NULL DEFAULT 0, favorite INTEGER NOT NULL DEFAULT 0,
              featured INTEGER NOT NULL DEFAULT 0, user_overrides_json TEXT NOT NULL DEFAULT '{}',
              notes TEXT NOT NULL DEFAULT '', evidence_json TEXT NOT NULL DEFAULT '[]',
              UNIQUE(source_id, skill_path)
            );
            CREATE TABLE IF NOT EXISTS sync_runs (
              id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
              trigger TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT, ended_at TEXT,
              discovered INTEGER NOT NULL DEFAULT 0, added INTEGER NOT NULL DEFAULT 0,
              updated INTEGER NOT NULL DEFAULT 0, skipped INTEGER NOT NULL DEFAULT 0,
              failed INTEGER NOT NULL DEFAULT 0, error TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON sync_runs(source_id)
              WHERE status IN ('queued', 'running');
            CREATE INDEX IF NOT EXISTS source_skills ON skills(source_id);
            """)
            if version == 0:
                for s in yaml.safe_load((CONFIG_DIR / "seed_sources.yaml").read_text())["sources"]:
                    c.execute(
                        "INSERT OR IGNORE INTO sources(name,repo,config_json) VALUES(?,?,?)",
                        (
                            s["name"],
                            s["repo"].lower(),
                            dump(
                                {
                                    "scan_roots": s["scan_roots"],
                                    "explicit_paths": s["explicit_paths"],
                                    "branch": "",
                                }
                            ),
                        ),
                    )
                c.execute("PRAGMA user_version=1")
            c.commit()

    def sources(self):
        return self.read("""SELECT s.*, (SELECT count(*) FROM skills k WHERE k.source_id=s.id) AS count,
          (SELECT status FROM sync_runs r WHERE r.source_id=s.id ORDER BY r.id DESC LIMIT 1) AS status
          FROM sources s ORDER BY s.id""")

    def skills(self):
        rows = self.read("""SELECT k.*, s.name AS source_name, s.repo, s.stars, s.forks,
          s.enabled AS source_enabled, s.repository_license FROM skills k
          JOIN sources s ON s.id=k.source_id""")
        return [present(r) for r in rows]


def present(row):
    item = json.loads(row["auto_json"])
    item.update(json.loads(row["user_overrides_json"]))
    for k, v in row.items():
        if not k.endswith("_json"):
            item[k] = v
    item["overrides"] = json.loads(row["user_overrides_json"])
    item["automatic"] = json.loads(row["auto_json"])
    item["evidence"] = json.loads(row["evidence_json"])
    return item
